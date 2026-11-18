"""Version-pinned Codex app-server discovery and restricted text generation.

Discovery returns ProviderManager-style records with status unverified. Catalog
listing does not establish execution access or provider-observed model identity.
Existing owner-configured lifecycle and managed policies remain in effect.
"""
import json
import copy
import re
from contextlib import suppress
import os
import queue
import subprocess
import threading
import time
import tempfile
from pathlib import Path

from .providers import ProviderError, _system_tool

_MAX_LINE = 2 * 1024 * 1024
_MAX_PAGES = 100


def _stop(proc):
    """Bound cleanup even when the operating system fails to terminate a child."""
    if proc.poll() is None:
        if os.name == 'nt':
            with suppress(OSError, subprocess.TimeoutExpired):
                subprocess.run([_system_tool('taskkill.exe'), '/PID', str(proc.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL, timeout=2,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
        else:
            import signal
            with suppress(OSError):
                os.killpg(proc.pid, signal.SIGKILL)
        if proc.poll() is None:
            with suppress(OSError):
                proc.kill()
    with suppress(OSError, subprocess.TimeoutExpired):
        proc.wait(timeout=2)


def discover_models(executable, timeout=8):
    """Read the installed app-server catalog for a ChatGPT-signed-in account.

    Returns list of {provider,id,name,modality,status}; IDs are request model
    strings, not provider-observed identities. Never starts an inference turn.
    """
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 300:
        raise ProviderError('Invalid discovery timeout')
    env = os.environ.copy()
    env.pop('OPENAI_API_KEY', None)
    env.pop('CODEX_API_KEY', None)
    try:
        proc = subprocess.Popen([executable, 'app-server', '--listen', 'stdio://'],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                start_new_session=(os.name != 'nt'))
    except (OSError, TypeError, ValueError):
        raise ProviderError('Codex executable unavailable') from None
    messages = queue.Queue(maxsize=1000)

    def reader():
        try:
            while True:
                line = proc.stdout.readline(_MAX_LINE + 1)
                if not line or len(line) > _MAX_LINE:
                    messages.put_nowait(None)
                    return
                messages.put_nowait(line)
        except (OSError, ValueError, queue.Full):
            try:
                messages.put_nowait(None)
            except queue.Full:
                pass

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()
    deadline = time.monotonic() + timeout

    def send(message):
        try:
            proc.stdin.write((json.dumps(message, separators=(',', ':')) + '\n').encode('utf-8'))
            proc.stdin.flush()
        except (OSError, ValueError):
            raise ProviderError('Codex discovery failed') from None

    def receive(request_id):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderError('Codex discovery timed out')
            try:
                line = messages.get(timeout=remaining)
            except queue.Empty:
                raise ProviderError('Codex discovery timed out') from None
            if line is None:
                raise ProviderError('Codex discovery failed')
            try:
                item = json.loads(line)
            except (ValueError, UnicodeError):
                raise ProviderError('Invalid Codex discovery response') from None
            if not isinstance(item, dict):
                raise ProviderError('Invalid Codex discovery response')
            if item.get('id') == request_id:
                if 'error' in item or not isinstance(item.get('result'), dict):
                    raise ProviderError('Codex discovery failed')
                return item['result']

    try:
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'local_agent_orchestrator', 'version': '1'}}})
        receive(1)
        send({'method': 'initialized'})
        send({'id': 2, 'method': 'account/read', 'params': {'refreshToken': False}})
        account = receive(2).get('account')
        if not isinstance(account, dict) or account.get('type') != 'chatgpt':
            raise ProviderError('Codex ChatGPT sign-in unavailable')
        records, seen = [], set()
        cursor = None
        for page in range(_MAX_PAGES):
            send({'id': page + 3, 'method': 'model/list', 'params': {'modelProvider': 'openai', 'cursor': cursor, 'includeHidden': False}})
            result = receive(page + 3)
            data = result.get('data')
            if not isinstance(data, list):
                raise ProviderError('Invalid Codex discovery response')
            for model in data:
                if not isinstance(model, dict):
                    raise ProviderError('Invalid Codex discovery response')
                mid, name = model.get('model'), model.get('displayName')
                if not isinstance(mid, str) or not mid or not isinstance(name, str):
                    raise ProviderError('Invalid Codex discovery response')
                if mid not in seen and not model.get('hidden', False):
                    seen.add(mid)
                    records.append({'provider': 'codex', 'id': mid, 'name': name or mid,
                                    'modality': 'text', 'status': 'unverified'})
            cursor = result.get('nextCursor')
            if cursor is None:
                return records
            if not isinstance(cursor, str) or not cursor:
                raise ProviderError('Invalid Codex discovery response')
        raise ProviderError('Codex discovery page limit exceeded')
    finally:
        _stop(proc)
        reader_thread.join(timeout=1)
        with suppress(OSError, ValueError):
            proc.stdin.close()
        if not reader_thread.is_alive():
            with suppress(OSError, ValueError):
                proc.stdout.close()


# Startup-only capability narrowing for the installed app-server version.
# These helpers do not enable execution: effective runtime gates and canaries
# must be reviewed before generate() can use them.
_NARROW_FEATURES = (
    'plugins', 'apps', 'computer_use', 'browser_use', 'browser_use_external',
    'in_app_browser', 'multi_agent', 'multi_agent_v2', 'shell_tool',
    'unified_exec', 'view_image', 'image_generation', 'skill_search',
    'memories', 'standalone_web_search', 'request_permissions_tool', 'goals',
    'token_budget', 'agent_message_board', 'agent_message_board_mcp',
    'executor_capability_discovery', 'executor_capability_discovery_v2',
    'multi_env_copy_file', 'skill_mcp_dependency_install',
)


def narrowed_catalog(models, model):
    """Return a startup catalog with a single exact model and fewer capabilities.

    Input must be an already-authorized model array, not an auth/cache object.
    Model metadata is copied without changes except the enumerated tool fields.
    """
    if not isinstance(models, list) or not isinstance(model, str) or not model:
        raise ProviderError('Invalid Codex model catalog')
    matches = [item for item in models if isinstance(item, dict) and item.get('slug') == model]
    if len(matches) != 1:
        raise ProviderError('Codex model not present in catalog')
    item = copy.deepcopy(matches[0])
    item.update(tool_mode='direct', shell_type='disabled', apply_patch_tool_type=None,
                experimental_supported_tools=[], supports_search_tool=False)
    return {'models': [item]}


def restricted_server_args(executable, catalog_path, server_names):
    """Construct per-process restrictions; never alters the user's config.

    Every supplied server is disabled; callers must inspect and verify the
    effective thread inventory, including newly appearing servers, before use.
    """
    if not isinstance(server_names, (list, tuple)) or any(
        not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', name)
        for name in server_names
    ):
        raise ProviderError('Invalid Codex server names')
    args = [executable, 'app-server', '--listen', 'stdio://',
            '-c', 'model_catalog_json=' + json.dumps(str(catalog_path)),
            '-c', 'web_search="disabled"', '-c', 'agents.enabled=false',
            '-c', 'cloud.skills.enabled=false', '-c', 'orchestrator.mcp.enabled=false',
            '-c', 'project_doc_max_bytes=0']
    for feature in _NARROW_FEATURES:
        args.extend(['--disable', feature])
    for name in sorted(set(server_names)):
        args.extend(['-c', 'mcp_servers.' + name + '.enabled=false'])
    return args


def _list_server_names(executable, timeout, flags):
    """Return only enabled names from the CLI; never retain connection details."""
    args = [executable, 'mcp', 'list', '--json']
    for flag in flags:
        args.extend(['--disable', flag])
    env = os.environ.copy()
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY'):
        env.pop(key, None)
    env['LOCAL_AGENT_ORCHESTRATOR_WORKER'] = '1'
    try:
        completed = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, timeout=timeout,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
        if completed.returncode or len(completed.stdout) > _MAX_LINE:
            raise ValueError()
        rows = json.loads(completed.stdout)
        if not isinstance(rows, list):
            raise ValueError()
        names = [row['name'] for row in rows if row.get('enabled') is True]
        if any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', n) for n in names):
            raise ValueError()
        return names
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
        raise ProviderError('Codex server discovery failed') from None


def generate(executable, model, prompt, output_dir, timeout=120, cancel_event=None):
    """Run one restricted ephemeral app-server turn, or raise ProviderError.

    The selected model is checked against thread startup; the protocol does not
    provide provider-observed per-turn model identity, so observed_model is None.
    Existing owner-configured lifecycle hooks retain their normal host policy.
    """
    if not isinstance(prompt, str) or len(prompt) > 8000 or not isinstance(model, str) or not model:
        raise ProviderError('Invalid Codex request')
    if not isinstance(timeout, (float, int)) or not 0 < timeout <= 300:
        raise ProviderError('Invalid Codex timeout')
    if cancel_event is not None and cancel_event.is_set():
        raise ProviderError('Operation cancelled')
    deadline = time.monotonic() + timeout
    proc = None
    reader_thread = None
    temp_holder = None
    try:
        # A names-only CLI query excludes plugin-generated servers before
        # individual child overrides are constructed.
        version = subprocess.run([executable, '--version'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=min(5, max(.1, deadline-time.monotonic())), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
        if version.returncode or version.stdout.strip() != b'codex-cli 0.169.0-alpha.11.1':
            raise ProviderError('Unsupported Codex version')
        names = _list_server_names(executable, min(10, max(.1, deadline-time.monotonic())), _NARROW_FEATURES)
        cache = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'models_cache.json'
        try:
            with cache.open(encoding='utf-8') as f:
                models = json.load(f).get('models')
            catalog = narrowed_catalog(models, model)
        except (OSError, ValueError, TypeError, AttributeError):
            raise ProviderError('Codex model catalog unavailable') from None
        temp_holder = tempfile.TemporaryDirectory(prefix='codex-worker-', dir=str(output_dir))
        temporary = temp_holder.name
        path = Path(temporary) / 'catalog.json'
        path.write_text(json.dumps(catalog), encoding='utf-8')
        env = os.environ.copy()
        env.pop('OPENAI_API_KEY', None)
        for key in ('CODEX_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY'):
            env.pop(key, None)
        env['LOCAL_AGENT_ORCHESTRATOR_WORKER'] = '1'
        args = restricted_server_args(executable, path, names)
        proc = subprocess.Popen(args, cwd=temporary, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                start_new_session=(os.name != 'nt'))
        messages = queue.Queue(maxsize=1000)
        def read_lines():
            try:
                while True:
                    line = proc.stdout.readline(_MAX_LINE + 1)
                    if not line or len(line) > _MAX_LINE:
                        messages.put_nowait(None)
                        return
                    messages.put_nowait(line)
            except (OSError, ValueError, queue.Full):
                with suppress(queue.Full):
                    messages.put_nowait(None)
        reader_thread = threading.Thread(target=read_lines, daemon=True)
        reader_thread.start()
        def send(obj):
            try:
                proc.stdin.write((json.dumps(obj, separators=(',', ':')) + '\n').encode())
                proc.stdin.flush()
            except (OSError, ValueError):
                raise ProviderError('Codex process failed') from None
        def read():
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise ProviderError('Operation cancelled')
                remain = deadline - time.monotonic()
                if remain <= 0:
                    raise ProviderError('Codex timed out')
                try:
                    line = messages.get(timeout=min(.1, remain))
                except queue.Empty:
                    continue
                if line is None:
                    raise ProviderError('Codex process failed')
                try:
                    obj = json.loads(line)
                except (ValueError, UnicodeError):
                    raise ProviderError('Invalid Codex response') from None
                if not isinstance(obj, dict):
                    raise ProviderError('Invalid Codex response')
                return obj
        def request(identifier, method, params):
            send({'id': identifier, 'method': method, 'params': params})
            while True:
                item = read()
                if item.get('id') == identifier:
                    if 'error' in item or not isinstance(item.get('result'), dict):
                        raise ProviderError('Codex request failed')
                    return item['result']
                if 'id' in item and 'method' in item:
                    raise ProviderError('Unexpected Codex server request')
        request(1, 'initialize', {'clientInfo': {'name': 'local_agent_orchestrator', 'version': '1'},
                                  'capabilities': {'experimentalApi': True}})
        send({'method': 'initialized'})
        account = request(2, 'account/read', {'refreshToken': False}).get('account')
        if not isinstance(account, dict) or account.get('type') != 'chatgpt':
            raise ProviderError('Codex ChatGPT sign-in unavailable')
        thread = request(3, 'thread/start', {'model': model, 'modelProvider': 'openai',
            'cwd': temporary, 'ephemeral': True, 'dynamicTools': [], 'environments': [],
            'selectedCapabilityRoots': [], 'allowProviderModelFallback': False})
        if thread.get('model') != model or thread.get('modelProvider') != 'openai':
            raise ProviderError('Codex selected model mismatch')
        thread_id = thread.get('thread', {}).get('id')
        if not isinstance(thread_id, str):
            raise ProviderError('Invalid Codex response')
        status = request(4, 'mcpServerStatus/list', {'threadId': thread_id, 'limit': 100})
        rows = status.get('data')
        if (not isinstance(rows, list) or status.get('nextCursor') or
            any(not isinstance(row, dict) or row.get('runtimeStatus') != 'disabled' or row.get('tools') for row in rows)):
            raise ProviderError('Codex external tools unavailable for restricted execution')
        send({'id': 5, 'method': 'turn/start', 'params': {'threadId': thread_id,
            'input': [{'type': 'text', 'text': prompt, 'text_elements': []}], 'environments': []}})
        text_parts = []
        started = False
        turn_id = None
        while True:
            item = read()
            if item.get('id') == 5:
                if 'error' in item or not isinstance(item.get('result'), dict):
                    raise ProviderError('Codex turn failed')
                turn_id = item['result'].get('turn', {}).get('id')
                if not isinstance(turn_id, str):
                    raise ProviderError('Invalid Codex response')
                started = True
            elif 'id' in item and 'method' in item:
                raise ProviderError('Unexpected Codex server request')
            elif item.get('method') in ('item/started', 'item/completed'):
                part = item.get('params', {}).get('item', {})
                kind = part.get('type')
                if kind == 'agentMessage' and item.get('method') == 'item/completed':
                    if part.get('phase') not in (None, 'final_answer'):
                        continue
                    if not isinstance(part.get('text'), str):
                        raise ProviderError('Invalid Codex response')
                    text_parts.append(part['text'])
                    if sum(map(len, text_parts)) > _MAX_LINE:
                        raise ProviderError('Codex response exceeds size limit')
                elif kind not in ('agentMessage', 'userMessage', 'reasoning', 'plan'):
                    raise ProviderError('Codex attempted a tool or unsupported action')
            elif item.get('method') == 'turn/completed':
                turn = item.get('params', {}).get('turn', {})
                if (not started or turn.get('id') != turn_id or turn.get('status') != 'completed' or turn.get('error')
                        or not ''.join(text_parts).strip() or item.get('params', {}).get('threadId') != thread_id):
                    raise ProviderError('Codex turn failed')
                return {'text': '\n'.join(text_parts), 'artifacts': [], 'observed_model': None,
                        'usage': {}, 'warnings': ['Provider-observed model identity unavailable']}
    except ProviderError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.TimeoutExpired):
        raise ProviderError('Codex execution failed') from None
    finally:
        if proc is not None:
            _stop(proc)
            if reader_thread is not None:
                reader_thread.join(timeout=1)
            with suppress(OSError, ValueError):
                proc.stdin.close()
            if reader_thread is None or not reader_thread.is_alive():
                with suppress(OSError, ValueError):
                    proc.stdout.close()

        if temp_holder is not None:
            with suppress(OSError):
                temp_holder.cleanup()
