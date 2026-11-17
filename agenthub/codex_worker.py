"""Codex CLI discovery adapter. Generation is intentionally unsupported.

Discovery returns ProviderManager-style records with status discovery_only: a
catalog entry is neither proof of execution access nor an observed model.
Raises ProviderError with sanitized messages; never returns account details.
"""
import json
from contextlib import suppress
import os
import queue
import subprocess
import threading
import time

from .providers import ProviderError

_MAX_LINE = 2 * 1024 * 1024
_MAX_PAGES = 100


def _stop(proc):
    if proc.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
        else:
            # A new session is created below, so descendants are also terminated.
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if proc.poll() is None:
            proc.kill()
    proc.wait()


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
                                    'modality': 'text', 'status': 'discovery_only'})
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
        with suppress(OSError, ValueError):
            proc.stdout.close()


def generate(executable, model, prompt, output_dir, timeout=120, cancel_event=None):
    """Fail closed: installed protocol has no verified response-only tool denial."""
    if cancel_event is not None and cancel_event.is_set():
        raise ProviderError('Operation cancelled')
    raise ProviderError('Codex execution unavailable: response-only tool denial cannot be verified')
