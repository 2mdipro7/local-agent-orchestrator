"""Provider discovery and generation for Local Agent Orchestrator."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
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
        p = parse.urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None or p.query or p.fragment:
            raise ValueError()
        if (p.scheme == 'http' or local_only) and p.hostname.lower() not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError()
        _ = p.port
        return url.rstrip('/')
    except (ValueError, AttributeError):
        raise ProviderError('Invalid provider endpoint') from None


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
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        req = request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with request.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
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
        except (OSError, ValueError, UnicodeError, TimeoutError) as exc:
            raise ProviderError('Provider request failed (%s)' % type(exc).__name__) from None

    def _executable(self, provider, cfg):
        value = cfg.get('executable')
        if value:
            return shutil.which(value) or (value if Path(value).is_file() else None)
        name = {'claude': 'claude', 'antigravity': 'agy', 'opencode': 'opencode'}[provider]
        found = shutil.which(name)
        if found:
            return found
        local = os.environ.get('LOCALAPPDATA')
        if local:
            root = Path(local)
            candidates = []
            if provider == 'antigravity':
                candidates = [root / 'Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/agy/bin/agy.exe', root / 'agy/bin/agy.exe']
            elif provider == 'claude':
                candidates = list((root / 'Microsoft/WinGet/Packages').glob('Anthropic.ClaudeCode_*/claude.exe')) + list((root / 'Microsoft/WinGet/Links').glob('claude*'))
            for item in candidates:
                if item.is_file():
                    return str(item)
        return None

    def _process(self, args, cwd, timeout, cancel_event=None):
        _cancel(cancel_event)
        env = os.environ.copy()
        for name in ('ANTHROPIC_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY'):
            env.pop(name, None)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        with tempfile.TemporaryFile(dir=str(cwd)) as stdout, tempfile.TemporaryFile(dir=str(cwd)) as stderr:
            try:
                proc = subprocess.Popen(args, cwd=str(cwd), env=env, stdout=stdout, stderr=stderr, creationflags=flags)
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
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, check=False)
                    else:
                        proc.kill()
                    proc.wait()
                    raise ProviderError(reason)
                time.sleep(.1)
            _cancel(cancel_event)
            if proc.returncode != 0:
                raise ProviderError('Provider process failed')
            if stdout.tell() > MAX_RESPONSE or stderr.tell() > MAX_RESPONSE:
                raise ProviderError('Provider response exceeds size limit')
            stdout.seek(0)
            return stdout.read(MAX_RESPONSE + 1).decode('utf-8', errors='replace')

    def discover(self):
        records = []
        for provider, cfg in self.config.get('providers', {}).items():
            if not cfg.get('enabled'):
                continue
            try:
                models = self._discover_one(provider, cfg)
                records.extend(models)
            except (ProviderError, KeyError, TypeError, ValueError):
                records.append({'provider': provider, 'id': '', 'name': provider, 'modality': 'unknown', 'status': 'unavailable'})
        return records

    def _discover_one(self, provider, cfg):
        def record(mid, name=None, modality='text', status='available'):
            return {'provider': provider, 'id': mid, 'name': name or mid, 'modality': modality, 'status': status}
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
            output = self._process([exe, 'models'], Path.cwd(), 8)
            if provider == 'antigravity':
                result = []
                for line in output.splitlines():
                    columns = line.strip().split('\t', 1)
                    if len(columns) != 2:
                        continue
                    mid, display = (part.strip() for part in columns)
                    if mid and display and ' ' not in mid:
                        result.append(record(mid, display))
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
        if images and provider in ('claude', 'antigravity', 'opencode'):
            raise ProviderError('Image input unsupported by provider')
        _cancel(cancel_event)
        result = {'text': '', 'artifacts': [], 'observed_model': None, 'usage': {}, 'warnings': []}
        if provider in ('claude', 'antigravity', 'opencode'):
            if provider == 'opencode':
                raise ProviderError('OpenCode execution unavailable: tool denial cannot be verified')
            exe = self._executable(provider, cfg)
            if not exe:
                raise ProviderError('Provider executable unavailable')
            args = ([exe, '--model', model, '-p', prompt, '--tools', '', '--max-turns', '1', '--output-format', 'json'] if provider == 'claude' else [exe, '-p', prompt, '--model', model, '--output-format', 'json', '--sandbox', '--settings', json.dumps({'permissions': {'deny': ['command(*)', 'mcp(*)', 'read_url(*)', 'execute_url(*)', 'download_url(*)', 'read_file(*)', 'write_file(*)']}})])
            raw = self._process(args, output_dir, timeout, cancel_event)
            try:
                obj = json.loads(raw)
            except ValueError:
                raise ProviderError('Invalid provider response') from None
            if not isinstance(obj, dict):
                raise ProviderError('Invalid provider response')
            if obj.get('is_error') or obj.get('permission_denials') or obj.get('denied_actions') or obj.get('deny_actions'):
                raise ProviderError('Provider reported an error or denied action')
            result['text'] = str(obj.get('result', obj.get('response', '')) or '')
            result['usage'] = obj.get('usage', {}) if isinstance(obj.get('usage', {}), dict) else {}
            if provider == 'claude' and isinstance(obj.get('modelUsage'), dict):
                names = list(obj['modelUsage'])
                if len(names) == 1:
                    result['observed_model'] = names[0]
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
