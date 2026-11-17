"""Response-only Antigravity ACP worker with session-scoped tool narrowing.

A documented nonempty built-in allowlist contains no real tool. Default
customizations are excluded only in this child; no client MCP servers are
supplied and every client fs/terminal/permission request is denied. Existing
provider-owned sign-in and managed permission policy are not modified.
"""
import json
import math
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time

from .providers import ProviderError

MAX_STREAM = 4 * 1024 * 1024
MAX_LINE = 1024 * 1024
NO_TOOLS = ['lao_no_tools']
# Live containment probe emitted a tool notification whose execution status was
# not retained. Until preexecution exclusion is verified, production cannot use
# the diagnostic protocol path below. This is not configurable from requests.
RESPONSE_ONLY_VERIFIED = False


def _stop(proc):
    """Bounded cleanup of this exact child process tree."""
    if proc.poll() is None:
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=5, check=False)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            raise ProviderError('Antigravity process cleanup unconfirmed') from None


def _structured_failure(obj):
    if not isinstance(obj, dict):
        return False
    if obj.get('is_error') or any(obj.get(k) for k in ('permission_denials', 'denied_actions', 'deny_actions')):
        return True
    status = obj.get('status')
    return isinstance(status, str) and status.upper() in {'ERROR', 'FAILED', 'CANCELLED', 'BLOCKED_PERMISSIONS'}


class _ACP:
    def __init__(self, proc, timeout, cancel_event):
        self.proc = proc
        self.deadline = time.monotonic() + timeout
        self.cancel_event = cancel_event
        self.messages = queue.Queue(maxsize=256)
        self.bad_stream = threading.Event()
        self.text = []
        self.usage = {}
        self.selected_family = None
        self.selected_effort = None
        self.counter = 0
        self.readers = []
        for stream, is_stdout in ((proc.stdout, True), (proc.stderr, False)):
            reader = threading.Thread(target=self._read, args=(stream, is_stdout), daemon=True)
            self.readers.append(reader)
            reader.start()

    def _read(self, stream, is_stdout):
        total = 0
        try:
            while True:
                line = stream.readline(MAX_LINE + 1)
                if not line:
                    break
                total += len(line)
                if len(line) > MAX_LINE or total > MAX_STREAM:
                    self.bad_stream.set()
                    return
                if is_stdout:
                    self.messages.put_nowait(line)
                elif b'AGY_ERROR' in line:
                    self.bad_stream.set()
        except (OSError, ValueError, queue.Full):
            self.bad_stream.set()

    def _send(self, obj):
        try:
            self.proc.stdin.write((json.dumps(obj) + '\n').encode('utf-8'))
            self.proc.stdin.flush()
        except (OSError, ValueError):
            raise ProviderError('Antigravity protocol connection closed') from None

    def _notification(self, obj):
        if obj.get('method') != 'session/update':
            return
        update = obj.get('params', {}).get('update', {})
        if not isinstance(update, dict) or _structured_failure(update):
            raise ProviderError('Antigravity reported an error or denied action')
        kind = update.get('sessionUpdate', '')
        if kind in ('tool_call', 'tool_call_update'):
            error = ProviderError('Antigravity attempted a prohibited tool; response rejected')
            error.tool_evidence = {key: update.get(key) for key in ('toolCallId', 'title', 'kind', 'status') if key in update}
            raise error
        if kind == 'agent_message_chunk':
            content = update.get('content', {})
            if content.get('type') == 'text' and isinstance(content.get('text'), str):
                self.text.append(content['text'])
        elif kind == 'config_option_update':
            for option in update.get('configOptions', []):
                if option.get('id') == 'model':
                    self.selected_family = option.get('currentValue')
                elif option.get('id') == 'thought_level':
                    self.selected_effort = option.get('currentValue')
        elif kind == 'usage_update':
            self.usage = {k: v for k, v in update.items() if isinstance(v, (int, float))}

    def request(self, method, params):
        self.counter += 1
        identifier = self.counter
        self._send({'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params})
        while True:
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise ProviderError('Operation cancelled')
            if self.bad_stream.is_set():
                raise ProviderError('Antigravity stream exceeded limits or reported an error')
            if time.monotonic() >= self.deadline:
                raise ProviderError('Antigravity timed out')
            try:
                raw = self.messages.get(timeout=.05)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise ProviderError('Antigravity exited before terminal response')
                continue
            try:
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError()
            except (ValueError, UnicodeError):
                raise ProviderError('Invalid Antigravity protocol response') from None
            if 'method' in obj and 'id' in obj:
                if obj['method'] == 'session/request_permission':
                    self._send({'jsonrpc': '2.0', 'id': obj['id'], 'result': {'outcome': {'outcome': 'cancelled'}}})
                else:
                    self._send({'jsonrpc': '2.0', 'id': obj['id'], 'error': {'code': -32601, 'message': 'Client tools unavailable'}})
                raise ProviderError('Antigravity requested a prohibited client action; denied')
            if obj.get('id') == identifier:
                result = obj.get('result')
                if obj.get('error') or not isinstance(result, dict) or _structured_failure(result):
                    raise ProviderError('Antigravity reported an error or denied action')
                return result
            if 'id' in obj:
                raise ProviderError('Unexpected Antigravity response ID')
            self._notification(obj)


def generate(executable, model, prompt, output_dir, timeout=120, cancel_event=None):
    """Return only completed text; reject all tool attempts and errors."""
    if cancel_event is not None and cancel_event.is_set():
        raise ProviderError('Operation cancelled')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
        raise ProviderError('Antigravity prompt must contain 1 to 8000 characters')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ProviderError('Invalid Antigravity timeout')
    if not isinstance(model, str) or not model.strip():
        raise ProviderError('Invalid Antigravity model')
    if not RESPONSE_ONLY_VERIFIED:
        raise ProviderError('Antigravity response-only execution unavailable: live containment test emitted an unclassified tool notification; preexecution tool exclusion remains unverified')
    cwd = Path(output_dir).resolve()
    if not executable or not cwd.is_dir():
        raise ProviderError('Antigravity executable or output directory unavailable')
    env = os.environ.copy()
    env['LOCAL_AGENT_ORCHESTRATOR_WORKER'] = '1'
    for key in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS'):
        env.pop(key, None)
    args = [executable, 'acp', '--include-default-customizations=false', '--log-file', os.devnull]
    try:
        proc = subprocess.Popen(args, cwd=str(cwd), env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                start_new_session=os.name != 'nt')
    except OSError:
        raise ProviderError('Antigravity executable unavailable') from None
    acp = None
    result = None
    try:
        acp = _ACP(proc, timeout, cancel_event)
        init = acp.request('initialize', {'protocolVersion': 1, 'clientCapabilities': {
            'fs': {'readTextFile': False, 'writeTextFile': False}, 'terminal': False},
            'clientInfo': {'name': 'local-agent-orchestrator', 'version': '0.1'}})
        if init.get('protocolVersion') != 1 or init.get('agentInfo', {}).get('name') != 'Antigravity ACP Server':
            raise ProviderError('Unsupported Antigravity ACP server')
        session = acp.request('session/new', {'cwd': str(cwd), 'mcpServers': [],
            '_meta': {'agy': {'enabledTools': NO_TOOLS, 'disabledTools': []}}})
        sid = session.get('sessionId')
        if not isinstance(sid, str) or not sid:
            raise ProviderError('Invalid Antigravity session')
        models = session.get('models', {}).get('availableModels', [])
        if model not in [x.get('modelId') for x in models if isinstance(x, dict)]:
            raise ProviderError('Requested Antigravity model is unavailable')
        acp.request('session/set_model', {'sessionId': sid, 'modelId': model})
        acp.request('session/set_mode', {'sessionId': sid, 'modeId': 'default'})
        final = acp.request('session/prompt', {'sessionId': sid, 'prompt': [{'type': 'text', 'text': prompt}]})
        if final.get('stopReason') != 'end_turn':
            raise ProviderError('Antigravity did not complete successfully')
        observed = final.get('modelId') or final.get('model')
        if observed and observed != model:
            raise ProviderError('Antigravity reported a different model')
        if acp.selected_family and not (model == acp.selected_family or model.startswith(acp.selected_family + '-')):
            raise ProviderError('Antigravity selected a different model family')
        if acp.selected_effort and model.endswith(('-low', '-medium', '-high', '-xhigh', '-max')) and not model.endswith('-' + acp.selected_effort):
            raise ProviderError('Antigravity selected a different model effort')
        text = ''.join(acp.text)
        if not text.strip():
            raise ProviderError('Antigravity returned no text')
        acp.request('session/close', {'sessionId': sid})
        result = {'text': text, 'artifacts': [], 'observed_model': observed, 'usage': acp.usage,
                  'warnings': [] if observed else ['Antigravity confirmed model selection but did not report generation model identity']}
    finally:
        _stop(proc)
        readers = acp.readers if acp else []
        for reader in readers:
            reader.join(timeout=.5)
        safe_streams = [proc.stdin]
        for index, stream in enumerate((proc.stdout, proc.stderr)):
            if not readers or not readers[index].is_alive():
                safe_streams.append(stream)
        for stream in safe_streams:
            try:
                stream.close()
            except (OSError, ValueError):
                pass
        if any(reader.is_alive() for reader in readers):
            raise ProviderError('Antigravity stream cleanup unconfirmed')
    if acp.bad_stream.is_set():
        raise ProviderError('Antigravity stream exceeded limits or reported an error')
    while not acp.messages.empty():
        try:
            packet = json.loads(acp.messages.get_nowait())
        except (ValueError, UnicodeError):
            raise ProviderError('Invalid Antigravity protocol response') from None
        acp._notification(packet)
    return result
