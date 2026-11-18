"""Provider discovery and generation for Local Agent Orchestrator."""
import base64
import json
from http.client import HTTPException
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
from urllib import error, parse, request

MAX_RESPONSE = 24 * 1024 * 1024
MAX_IMAGE = 16 * 1024 * 1024


class ProviderError(Exception):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _endpoint(url, local_only=False):
    try:
        if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
            raise ValueError()
        p = parse.urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None or p.query or p.fragment:
            raise ValueError()
        if (p.scheme == 'http' or local_only) and p.hostname.lower() not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError()
        _ = p.port
        return url.rstrip('/')
    except (ValueError, AttributeError):
        raise ProviderError('Invalid provider endpoint') from None


def _find_executable(name):
    """Search only explicit absolute PATH directories, never the launch folder.

    Windows shutil.which may implicitly search cwd. Batch wrappers also invoke
    a shell despite shell=False, so only native binaries are supported there.
    """
    if not isinstance(name, str) or not name or Path(name).name != name:
        return None
    extensions = ('',) if os.name != 'nt' else (('',) if Path(name).suffix.lower() in ('.exe', '.com') else ('.exe', '.com'))
    if os.name == 'nt' and Path(name).suffix and Path(name).suffix.lower() not in ('.exe', '.com'):
        return None
    current = Path.cwd().resolve()
    for entry in os.environ.get('PATH', '').split(os.pathsep):
        directory = Path(entry.strip('"'))
        if not directory.is_absolute() or directory.resolve() == current:
            continue
        for extension in extensions:
            candidate = directory / (name + extension)
            if candidate.is_file() and (os.name == 'nt' or os.access(candidate, os.X_OK)):
                return str(candidate.resolve())
    return None


def _system_tool(name):
    """Resolve Windows maintenance commands without project/PATH lookup."""
    root = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32'
    return str(root / name) if os.name == 'nt' else name


def _cancel(event):
    if event is not None and event.is_set():
        raise ProviderError('Operation cancelled')


def _image_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png', 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpeg', 'image/jpeg'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp', 'image/webp'
    raise ProviderError('Unsupported or invalid image data')


def _read_image(path):
    try:
        p = Path(path)
        if p.stat().st_size > MAX_IMAGE:
            raise ProviderError('Image exceeds size limit')
        data = p.read_bytes()
    except OSError:
        raise ProviderError('Cannot read input image') from None
    ext, mime = _image_type(data)
    return base64.b64encode(data).decode('ascii'), mime


def _save_image(encoded, output_dir, index):
    try:
        if not isinstance(encoded, str) or len(encoded) > (MAX_IMAGE * 4 // 3 + 8):
            raise ValueError()
        data = base64.b64decode(encoded, validate=True)
        if not data or len(data) > MAX_IMAGE:
            raise ValueError()
    except (ValueError, TypeError):
        raise ProviderError('Invalid generated image data') from None
    ext, _ = _image_type(data)
    path = Path(output_dir) / ('generated-%d.%s' % (index, ext))
    try:
        path.write_bytes(data)
    except OSError:
        raise ProviderError('Cannot save generated image') from None
    return path.name


class ProviderManager:
    def __init__(self, config, secret_getter):
        self.config = config
        self.secret_getter = secret_getter
        self._discovery_lock = threading.Lock()
        self._discovery_cache = {}
        self._discovery_inflight = {}

    def _config(self, provider):
        return self.config.get('providers', {}).get(provider, {})

    def _key(self, provider, cfg):
        name = cfg.get('credential', provider)
        try:
            key = self.secret_getter(name)
        except Exception:
            raise ProviderError('Credential unavailable') from None
        if not key:
            raise ProviderError('Credential unavailable')
        return key

    def _headers(self, provider, cfg, base):
        if provider == 'gemini':
            return {'x-goog-api-key': self._key(provider, cfg)}
        if provider == 'openai_compatible':
            host = parse.urlsplit(base).hostname.lower()
            if host in ('localhost', '127.0.0.1', '::1'):
                key = None
                if cfg.get('credential'):
                    try:
                        key = self.secret_getter(cfg['credential'])
                    except Exception:
                        key = None
            else:
                key = self._key(provider, cfg)
            return {'Authorization': 'Bearer ' + key} if key else {}
        return {}

    def _http(self, method, url, payload=None, headers=None, timeout=120, cancel_event=None):
        _cancel(cancel_event)
        deadline = time.monotonic() + timeout
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        req = request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            handlers = [_NoRedirect()]
            if parse.urlsplit(url).hostname in ('localhost', '127.0.0.1', '::1'):
                # Local-model prompts must not leave the PC via ambient proxies.
                handlers.append(request.ProxyHandler({}))
            with request.build_opener(*handlers).open(req, timeout=timeout) as response:
                raw = bytearray()
                while True:
                    _cancel(cancel_event)
                    if time.monotonic() >= deadline:
                        raise ProviderError('Provider request timed out')
                    chunk = response.read1(min(65536, MAX_RESPONSE + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise ProviderError('Provider response exceeds size limit')
            _cancel(cancel_event)
            obj = json.loads(raw.decode('utf-8'))
            if not isinstance(obj, dict):
                raise ValueError()
            return obj
        except ProviderError:
            raise
        except error.HTTPError as exc:
            raise ProviderError('Provider HTTP error %s' % exc.code) from None
        except error.URLError as exc:
            reason = exc.reason
            code = getattr(reason, 'winerror', None) or getattr(reason, 'errno', None)
            raise ProviderError('Provider connection failed (%s%s)' % (type(reason).__name__, ', code %s' % code if code is not None else '')) from None
        except (OSError, ValueError, UnicodeError, TimeoutError, HTTPException, RecursionError) as exc:
            raise ProviderError('Provider request failed (%s)' % type(exc).__name__) from None

    def _executable(self, provider, cfg):
        value = cfg.get('executable')
        if value:
            if not isinstance(value, str):
                raise ProviderError('Invalid provider executable')
            path = Path(value)
            if path.is_absolute():
                if os.name == 'nt' and path.suffix.lower() not in ('.exe', '.com'):
                    raise ProviderError('Provider executable must be a native binary, not a shell wrapper')
                return str(path.resolve()) if path.is_file() else None
            if path.name != value:
                raise ProviderError('Provider executable path must be absolute')
            return _find_executable(value)
        name = {'claude': 'claude', 'antigravity': 'agy', 'opencode': 'opencode', 'codex': 'codex'}[provider]
        found = _find_executable(name)
        if found:
            return found
        # Desktop hosts do not necessarily inherit the terminal's PATH. Search
        # only known per-user install locations, never unrelated workspaces.
        roots = list(dict.fromkeys([Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')),
                                   Path.home() / 'AppData/Local']))
        candidates = [Path.home() / '.local/bin/claude.exe'] if provider == 'claude' else []
        for root in roots:
            if provider == 'antigravity':
                candidates.extend([root / 'agy/bin/agy.exe', root / 'Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/agy/bin/agy.exe'])
            elif provider == 'claude':
                candidates.extend(sorted((root / 'Microsoft/WinGet/Packages').glob('Anthropic.ClaudeCode_*/claude.exe')))
                candidates.append(root / 'Microsoft/WinGet/Links/claude.exe')
            elif provider == 'codex':
                candidates.extend([root / 'Programs/Codex/resources/codex.exe',
                                   root / 'Programs/Codex/app/resources/codex.exe'])
        for item in candidates:
            if item.is_file():
                return str(item)
        if provider == 'codex' and os.name == 'nt':
            return self._codex_app_executable()
        return None

    @staticmethod
    def _codex_app_executable():
        """Locate this user's registered Store app without a version-pinned path.

        This read-only OS query does not launch Codex or access account data.
        Version/tool confinement remains enforced by the worker adapter.
        """
        shell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        try:
            result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-Command',
                                     'Get-AppxPackage -Name OpenAI.Codex | Select-Object -ExpandProperty InstallLocation | ConvertTo-Json -Compress'],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, timeout=4, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
            if result.returncode or len(result.stdout) > 32768:
                return None
            locations = json.loads(result.stdout)
            if isinstance(locations, str):
                locations = [locations]
            if not isinstance(locations, list):
                return None
            for location in locations:
                if isinstance(location, str) and Path(location).is_absolute():
                    candidate = Path(location) / 'app/resources/codex.exe'
                    if candidate.is_file():
                        return str(candidate)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return None

    def _process(self, args, cwd, timeout, cancel_event=None):
        _cancel(cancel_event)
        env = os.environ.copy()
        for name in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY'):
            env.pop(name, None)
        env['LOCAL_AGENT_ORCHESTRATOR_WORKER'] = '1'
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        with tempfile.TemporaryFile(dir=str(cwd)) as stdout, tempfile.TemporaryFile(dir=str(cwd)) as stderr:
            try:
                proc = subprocess.Popen(args, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, creationflags=flags, start_new_session=os.name != 'nt')
            except OSError:
                raise ProviderError('Provider executable unavailable') from None
            start = time.monotonic()
            reason = None
            while proc.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    reason = 'Operation cancelled'
                elif time.monotonic() - start >= timeout:
                    reason = 'Provider timed out'
                elif stdout.tell() > MAX_RESPONSE or stderr.tell() > MAX_RESPONSE:
                    reason = 'Provider response exceeds size limit'
                if reason:
                    try:
                        if os.name == 'nt':
                            subprocess.run([_system_tool('taskkill.exe'), '/PID', str(proc.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, check=False, timeout=3)
                        else:
                            os.killpg(proc.pid, signal.SIGKILL)
                    except (OSError, subprocess.TimeoutExpired):
                        proc.kill()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        raise ProviderError('Provider cleanup unconfirmed') from None
                    raise ProviderError(reason)
                time.sleep(.1)
            _cancel(cancel_event)
            if proc.returncode != 0:
                raise ProviderError('Provider process failed')
            if stdout.tell() > MAX_RESPONSE or stderr.tell() > MAX_RESPONSE:
                raise ProviderError('Provider response exceeds size limit')
            stdout.seek(0)
            return stdout.read(MAX_RESPONSE + 1).decode('utf-8', errors='replace')

    def discover(self, deadline_seconds=25):
        """Concurrent bounded probes; retain in-flight probes instead of retry storms."""
        enabled = {p: c for p, c in self.config.get('providers', {}).items() if c.get('enabled')}
        def unavailable(provider, reason):
            return {'provider': provider, 'id': '', 'name': provider, 'modality': 'unknown', 'status': 'unavailable', 'reason': reason}
        def probe(provider, cfg, event):
            try:
                models = self._discover_one(provider, cfg)
            except Exception as exc:
                reason = str(exc)[:180] if isinstance(exc, ProviderError) else 'Provider discovery failed'
                models = [unavailable(provider, reason)]
            with self._discovery_lock:
                self._discovery_cache[provider] = (time.monotonic(), models)
                self._discovery_inflight.pop(provider, None)
                event.set()
        deadline = time.monotonic() + deadline_seconds
        with self._discovery_lock:
            for provider, cfg in enabled.items():
                cached = self._discovery_cache.get(provider)
                if (cached and time.monotonic() - cached[0] < 30) or provider in self._discovery_inflight:
                    continue
                event = threading.Event()
                self._discovery_inflight[provider] = event
                threading.Thread(target=probe, args=(provider, cfg, event), daemon=True).start()
            waiting = list(self._discovery_inflight.values())
        for event in waiting:
            event.wait(max(0, deadline - time.monotonic()))
        with self._discovery_lock:
            return [record for provider in enabled for record in
                    (self._discovery_cache[provider][1] if provider not in self._discovery_inflight and provider in self._discovery_cache
                     else [unavailable(provider, 'Probe still running after discovery deadline; no duplicate probe started')])]

    def _discover_one(self, provider, cfg):
        def record(mid, name=None, modality='text', status='available'):
            return {'provider': provider, 'id': mid, 'name': name or mid, 'modality': modality, 'status': status}
        if provider == 'codex':
            from .codex_worker import discover_models
            return discover_models(self._executable(provider, cfg))
        if provider in ('ollama', 'lmstudio', 'openai_compatible', 'gemini'):
            default = {'ollama': 'http://127.0.0.1:11434', 'lmstudio': 'http://127.0.0.1:1234/v1', 'gemini': 'https://generativelanguage.googleapis.com/v1beta'}.get(provider, '')
            base = _endpoint(cfg.get('base_url', default), local_only=provider in ('ollama', 'lmstudio'))
            headers = self._headers(provider, cfg, base)
            obj = self._http('GET', base + ('/api/tags' if provider == 'ollama' else '/models'), headers=headers, timeout=8)
            items = obj.get('models' if provider in ('ollama', 'gemini') else 'data', [])
            result = []
            for item in items:
                mid = item.get('name') if provider in ('ollama', 'gemini') else item.get('id')
                if mid:
                    if provider == 'gemini' and mid.startswith('models/'):
                        mid = mid[7:]
                    modality = 'text, image input' if provider == 'ollama' and 'vision' in item.get('capabilities', []) else 'text'
                    result.append(record(mid, item.get('displayName') or mid, modality))
            return result
        if provider in ('claude', 'antigravity', 'opencode'):
            exe = self._executable(provider, cfg)
            if not exe:
                raise ProviderError('Provider executable unavailable')
            if provider == 'claude':
                return [record(mid, status='unverified') for mid in ('claude-sonnet-5-5', 'claude-opus-5-5', 'claude-haiku-5-5')]
            # Desktop hosts may start in protected application directories.
            # Discovery must neither depend on that cwd nor load its project files.
            with tempfile.TemporaryDirectory(prefix='lao-model-probe-') as probe_dir:
                output = self._process([exe, 'models'], Path(probe_dir), 20)
            if provider == 'antigravity':
                result = []
                for line in output.splitlines():
                    columns = line.strip().split('\t', 1)
                    if len(columns) != 2:
                        continue
                    mid, display = (part.strip() for part in columns)
                    if mid and display and ' ' not in mid:
                        result.append(record(mid, display, status='unverified'))
                return result
            # CLI output may be JSON or newline-separated model IDs.
            try:
                parsed = json.loads(output)
                if isinstance(parsed, dict):
                    parsed = parsed.get('models', [])
                ids = [x.get('id', x.get('name', '')) if isinstance(x, dict) else x for x in parsed] if isinstance(parsed, list) else []
            except ValueError:
                ids = [line.strip() for line in output.splitlines()]
            return [record(str(mid), status='discovery_only') for mid in ids if mid]
        raise ProviderError('Unsupported provider')

    def generate(self, provider, model, prompt, *, output_dir, images=None, task_kind='text', timeout=120, cancel_event=None):
        cfg = self._config(provider)
        if not cfg.get('enabled'):
            raise ProviderError('Provider unavailable')
        if task_kind not in ('text', 'image'):
            raise ProviderError('Unsupported task kind')
        if task_kind == 'image' and provider not in ('openai_compatible', 'gemini'):
            raise ProviderError('Image generation unsupported by provider')
        if images and provider in ('claude', 'antigravity', 'codex', 'opencode'):
            raise ProviderError('Image input unsupported by provider')
        _cancel(cancel_event)
        result = {'text': '', 'artifacts': [], 'observed_model': None, 'usage': {}, 'warnings': []}
        if provider in ('claude', 'antigravity', 'codex', 'opencode'):
            if provider == 'opencode':
                raise ProviderError('OpenCode execution unavailable: tool denial cannot be verified')
            exe = self._executable(provider, cfg)
            if not exe:
                raise ProviderError('Provider executable unavailable')
            if provider == 'antigravity':
                from .antigravity_worker import generate
                return generate(exe, model, prompt, output_dir, timeout, cancel_event)
            if provider == 'codex':
                from .codex_worker import generate
                return generate(exe, model, prompt, output_dir, timeout, cancel_event)
            args = [exe, '--model', model, '-p', prompt, '--tools', '', '--max-turns', '1',
                    '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                    '--permission-prompts', 'none', '--disable-slash-commands', '--no-chrome',
                    '--settings', json.dumps({'disableAllHooks': True, 'autoMemoryEnabled': False,
                                             'disableWorkflows': True, 'disableClaudeAiConnectors': True}),
                    '--output-format', 'stream-json', '--verbose']
            raw = self._process(args, output_dir, timeout, cancel_event)
            try:
                events = [json.loads(line) for line in raw.splitlines() if line.strip()]
            except ValueError:
                raise ProviderError('Invalid provider response') from None
            if any(not isinstance(event, dict) for event in events):
                raise ProviderError('Invalid provider response')
            init = [e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init']
            terminal = [e for e in events if e.get('type') == 'result']
            if len(init) != 1 or init[0].get('tools') != [] or init[0].get('mcp_servers') != []:
                raise ProviderError('Claude response-only tool configuration could not be verified')
            for event in events:
                content = event.get('message', {}).get('content', []) if isinstance(event.get('message'), dict) else []
                if any(isinstance(part, dict) and part.get('type') in ('tool_use', 'server_tool_use') for part in content):
                    raise ProviderError('Claude attempted a prohibited tool; response rejected')
            if len(terminal) != 1 or terminal[0].get('subtype') != 'success':
                raise ProviderError('Claude did not complete successfully')
            obj = terminal[0]
            if obj.get('is_error') or obj.get('permission_denials') or obj.get('denied_actions') or obj.get('deny_actions'):
                raise ProviderError('Provider reported an error or denied action')
            result['text'] = str(obj.get('result', obj.get('response', '')) or '')
            result['usage'] = obj.get('usage', {}) if isinstance(obj.get('usage', {}), dict) else {}
            if provider == 'claude' and isinstance(obj.get('modelUsage'), dict):
                names = list(obj['modelUsage'])
                if names and names != [model]:
                    raise ProviderError('Claude reported a different model')
                result['observed_model'] = names[0] if names else None
            if not result['observed_model']:
                result['warnings'].append('Claude did not report generation model identity')
            if not result['text'].strip():
                raise ProviderError('Claude returned no text')
            return result
        default = {'ollama': 'http://127.0.0.1:11434', 'lmstudio': 'http://127.0.0.1:1234/v1', 'gemini': 'https://generativelanguage.googleapis.com/v1beta'}.get(provider, '')
        if provider not in ('ollama', 'lmstudio', 'openai_compatible', 'gemini'):
            raise ProviderError('Unsupported provider')
        base = _endpoint(cfg.get('base_url', default), local_only=provider in ('ollama', 'lmstudio'))
        headers = self._headers(provider, cfg, base)
        encoded = [_read_image(p) for p in (images or [])]
        if task_kind == 'image' and images and provider == 'openai_compatible':
            raise ProviderError('Image input is unsupported for image generation')
        if provider == 'gemini':
            parts = [{'text': prompt}] + [{'inlineData': {'mimeType': mime, 'data': data}} for data, mime in encoded]
            payload = {'contents': [{'role': 'user', 'parts': parts}]}
            if task_kind == 'image':
                payload['generationConfig'] = {'responseModalities': ['TEXT', 'IMAGE'], 'candidateCount': 1}
            else:
                payload['generationConfig'] = {'maxOutputTokens': 1024}
            url = base + '/models/' + parse.quote(model.removeprefix('models/'), safe='') + ':generateContent'
        elif provider == 'ollama':
            msg = {'role': 'user', 'content': prompt}
            if encoded:
                msg['images'] = [data for data, _ in encoded]
            payload = {'model': model, 'messages': [msg], 'stream': False, 'keep_alive': '2m', 'options': {'num_ctx': 4096, 'num_predict': 1024}}
            if 'qwen3' in model.lower():
                payload['think'] = False
            url = base + '/api/chat'
        elif task_kind == 'image':
            payload = {'model': model, 'prompt': prompt, 'response_format': 'b64_json'}
            url = base + '/images/generations'
        else:
            content = prompt if not encoded else [{'type': 'text', 'text': prompt}] + [{'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (mime, data)}} for data, mime in encoded]
            payload = {'model': model, 'messages': [{'role': 'user', 'content': content}], 'max_tokens': 1024}
            url = base + '/chat/completions'
        obj = self._http('POST', url, payload, headers, timeout, cancel_event)
        try:
            if provider == 'gemini':
                for candidate in obj.get('candidates', []):
                    for part in candidate.get('content', {}).get('parts', []):
                        if 'text' in part:
                            result['text'] += part['text']
                        inline = part.get('inlineData', part.get('inline_data'))
                        if inline and task_kind == 'image':
                            result['artifacts'].append(_save_image(inline.get('data'), output_dir, len(result['artifacts']) + 1))
                result['observed_model'] = obj.get('modelVersion')
                result['usage'] = obj.get('usageMetadata', {})
            elif provider == 'ollama':
                result['text'] = obj.get('message', {}).get('content', '')
                result['observed_model'] = obj.get('model')
                result['usage'] = {k: obj[k] for k in ('prompt_eval_count', 'eval_count') if k in obj}
            elif task_kind == 'image':
                for item in obj.get('data', []):
                    if 'b64_json' in item:
                        result['artifacts'].append(_save_image(item['b64_json'], output_dir, len(result['artifacts']) + 1))
                    else:
                        result['warnings'].append('A non-base64 image result was ignored')
                result['usage'] = obj.get('usage', {})
            else:
                result['text'] = obj['choices'][0]['message'].get('content') or ''
                result['observed_model'] = obj.get('model')
                result['usage'] = obj.get('usage', {})
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError('Invalid provider response') from None
        if task_kind == 'image' and not result['artifacts']:
            raise ProviderError('Provider returned no valid generated image')
        return result
