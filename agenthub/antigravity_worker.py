"""Restricted Antigravity print worker with preexecution application guards.

ACP tool filtering does not remove core tools in the installed CLI. Use a
constant-output PreToolUse deny hook plus session-only sensitive-action denies.
These are same-user application controls, not operating-system isolation.
"""
import base64
import json
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time

from .providers import ProviderError

MAX_STREAM = 4 * 1024 * 1024
MAX_LINE = 1024 * 1024
DENY_ACTIONS = ('command(*)', 'mcp(*)', 'read_url(*)', 'execute_url(*)',
                'download_url(*)', 'read_file(*)', 'write_file(*)')
GUARD_REASON = 'LOCAL_AGENT_ORCHESTRATOR_RESPONSE_ONLY_DENY'
# Enabled after live read/write/command/delegation denial, source-adapter text
# completion, guard-error no-op, cancellation and cleanup checks. This records
# application-control verification, not an operating-system sandbox guarantee.
RESPONSE_ONLY_VERIFIED = True


def _stop(proc):
    """Stop this exact process tree and bound every wait."""
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


def _command(args):
    if os.name != 'nt':
        return shlex.join(args)
    # Hook commands are interpreted by a shell. Do not interpolate paths that
    # need shell expansion; reject rather than accidentally execute path text.
    if any(any(c in arg for c in '&|<>^%!"\r\n') for arg in args):
        raise ProviderError('Antigravity guard path contains unsupported shell characters')
    return ' '.join('"' + arg + '"' for arg in args)


def _environment():
    env = os.environ.copy()
    env['LOCAL_AGENT_ORCHESTRATOR_WORKER'] = '1'
    for key in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS'):
        env.pop(key, None)
    return env


def _shell():
    if os.name != 'nt':
        return '/bin/sh'
    return str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/cmd.exe')


def _guard_command(marker, output):
    """Construct only constant code and escaped CLI-owned paths, never stdin."""
    encoded_output = json.dumps(output)
    if os.name == 'nt':
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        if not powershell.is_file():
            raise ProviderError('Windows PowerShell is required for Antigravity guards')
        quote = lambda value: "'" + value.replace("'", "''") + "'"
        script = ("$ErrorActionPreference='Stop';"
                  '[IO.File]::WriteAllText(' + quote(str(marker)) + ",'GUARD_CALLED');"
                  '[Console]::Out.WriteLine(' + quote(encoded_output) + ')')
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        return _command([str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded])
    script = ('set -e; printf %s GUARD_CALLED > ' + shlex.quote(str(marker))
              + "; printf '%s\\n' " + shlex.quote(encoded_output))
    return _command(['/bin/sh', '-c', script])


def _preflight(command, expected, env):
    try:
        # Execute the exact shell command stored in hooks.json. No Python
        # interpreter is assumed; sys.executable can be the frozen app itself.
        check = subprocess.run(command, shell=True, executable=_shell(), input=b'ignored model input',
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                               timeout=5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if check.returncode != 0 or check.stderr or json.loads(check.stdout) != expected:
            raise ValueError()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise ProviderError('Antigravity preexecution guard preflight failed') from None


def _write_controls(workspace, env):
    """Only CLI-owned constants go in encoded commands; neither reads stdin."""
    agents = workspace / '.agents'
    agents.mkdir()
    audit = workspace / 'guard-denied.marker'
    startup = workspace / 'guard-started.marker'
    denial = {'decision': 'deny', 'reason': GUARD_REASON}
    commands = []
    for marker, output in ((audit, denial), (startup, {})):
        command = _guard_command(marker, output)
        _preflight(command, output, env)
        marker.unlink()
        commands.append(command)
    config = {'local_agent_orchestrator_response_only': {'enabled': True,
        'SessionStart': [{'type': 'command', 'command': commands[1], 'timeout': 5}],
        'PreToolUse': [{'matcher': '*', 'hooks': [{'type': 'command', 'command': commands[0], 'timeout': 5}]}]}}
    (agents / 'hooks.json').write_text(json.dumps(config), encoding='utf-8')
    expected = {str(Path('.agents') / 'hooks.json'): (agents / 'hooks.json').read_bytes()}
    return audit, startup, expected


def _tool_error(name, state, error_type=None):
    error = ProviderError('Antigravity attempted a tool; preexecution guard rejected the response')
    error.tool_evidence = {'tool_name': str(name)[:100], 'state': str(state)[:30], 'error_type': str(error_type)[:100] if error_type else None}
    return error


def _parse_stream(raw, model):
    if len(raw) > MAX_STREAM:
        raise ProviderError('Antigravity response exceeds size limit')
    init = None
    final = None
    tools = []
    failed_step = False
    for line in raw.splitlines():
        if not line.strip():
            continue
        if len(line) > MAX_LINE:
            raise ProviderError('Antigravity response exceeds line limit')
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise ProviderError('Invalid Antigravity stream response') from None
        event = obj.get('event')
        if final is not None:
            raise ProviderError('Antigravity emitted events after terminal response')
        if event == 'init':
            if init is not None or not isinstance(obj.get('init'), dict):
                raise ProviderError('Invalid Antigravity initialization')
            init = obj['init']
            if init.get('model') != model:
                raise ProviderError('Antigravity selected a different model')
            if init.get('permission_mode') == 'always-proceed':
                raise ProviderError('Antigravity reported permission bypass mode')
        elif event == 'step_update':
            step = obj.get('step_update')
            if not isinstance(step, dict):
                raise ProviderError('Invalid Antigravity step response')
            if step.get('state') == 'ERROR':
                failed_step = True
            if step.get('step_type') == 'tool' or step.get('tool_info') or step.get('subagent_info'):
                info = step.get('tool_info') or {}
                if not isinstance(info, dict):
                    raise ProviderError('Invalid Antigravity tool response')
                detail = info.get('error') or {}
                if not isinstance(detail, dict):
                    raise ProviderError('Antigravity reported a failed tool')
                tools.append((step.get('tool_name') or info.get('name') or 'subagent', step.get('state'), detail.get('type')))
        elif event == 'result':
            final = obj.get('result')
        else:
            raise ProviderError('Unsupported Antigravity stream event')
    if tools:
        raise _tool_error(*next((tool for tool in tools if tool[1] == 'ERROR'), tools[0]))
    if failed_step:
        raise ProviderError('Antigravity reported a failed execution step')
    if init is None or not isinstance(final, dict):
        raise ProviderError('Antigravity did not return a terminal response')
    if (final.get('status') != 'SUCCESS' or final.get('is_error') or final.get('error')
            or any(final.get(key) for key in ('denied_actions', 'permission_denials', 'deny_actions'))):
        raise ProviderError('Antigravity reported an error or denied action')
    text = final.get('response')
    if not isinstance(text, str) or not text.strip():
        raise ProviderError('Antigravity returned no response text')
    observed = final.get('modelId') or final.get('model')
    if observed and observed != model:
        raise ProviderError('Antigravity reported a different model')
    return {'text': text, 'artifacts': [], 'observed_model': observed,
            'usage': final.get('usage', {}) if isinstance(final.get('usage'), dict) else {},
            'warnings': [] if observed else ['Antigravity confirmed model selection but did not report generation model identity']}


def _run(executable, model, prompt, workspace, timeout, cancel_event, env):
    args = [executable, '--model', model, '--output-format', 'stream-json',
            '--print-timeout', str(timeout) + 's', '--disable-slash-commands',
            '--sandbox', '--settings', json.dumps({'permissions': {'deny': list(DENY_ACTIONS)}}), '-p', prompt]
    # Wildcard deny rules narrow every supported sensitive action namespace.
    # No allow/ask grants or persistent settings are edited.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            proc = subprocess.Popen(args, cwd=str(workspace), env=env, stdin=subprocess.DEVNULL,
                                    stdout=stdout, stderr=stderr, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                    start_new_session=os.name != 'nt')
        except OSError:
            raise ProviderError('Antigravity executable unavailable') from None
        started = time.monotonic()
        try:
            while proc.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    raise ProviderError('Operation cancelled')
                if time.monotonic() - started >= timeout:
                    raise ProviderError('Antigravity timed out')
                if max(os.fstat(stdout.fileno()).st_size, os.fstat(stderr.fileno()).st_size) > MAX_STREAM:
                    raise ProviderError('Antigravity response exceeds size limit')
                time.sleep(.05)
            if cancel_event is not None and cancel_event.is_set():
                raise ProviderError('Operation cancelled')
            if max(os.fstat(stdout.fileno()).st_size, os.fstat(stderr.fileno()).st_size) > MAX_STREAM:
                raise ProviderError('Antigravity response exceeds size limit')
            stdout.seek(0)
            stderr.seek(0)
            raw, diagnostics = stdout.read(MAX_STREAM + 1), stderr.read(MAX_STREAM + 1)
            if proc.returncode != 0 or b'AGY_ERROR' in diagnostics:
                raise ProviderError('Antigravity process failed')
            return raw
        finally:
            _stop(proc)


def generate(executable, model, prompt, output_dir, timeout=120, cancel_event=None):
    if cancel_event is not None and cancel_event.is_set():
        raise ProviderError('Operation cancelled')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
        raise ProviderError('Antigravity prompt must contain 1 to 8000 characters')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ProviderError('Invalid Antigravity timeout')
    if not isinstance(model, str) or not model.strip():
        raise ProviderError('Invalid Antigravity model')
    if not RESPONSE_ONLY_VERIFIED:
        raise ProviderError('Antigravity response-only execution unavailable: preexecution guard validation is incomplete')
    root = Path(output_dir).resolve()
    if not executable or not root.is_dir():
        raise ProviderError('Antigravity executable or output directory unavailable')
    env = _environment()
    with tempfile.TemporaryDirectory(prefix='.antigravity-response-', dir=str(root)) as folder:
        workspace = Path(folder)
        audit, startup, expected = _write_controls(workspace, env)
        raw = _run(executable, model, prompt, workspace, timeout, cancel_event, env)
        if not startup.is_file() or startup.read_text(encoding='utf-8') != 'GUARD_CALLED':
            raise ProviderError('Antigravity did not confirm preexecution guard startup')
        actual = {str(path.relative_to(workspace)): path.read_bytes() for path in workspace.rglob('*') if path.is_file() and path not in (audit, startup)}
        if actual != expected:
            raise ProviderError('Antigravity child workspace changed unexpectedly')
        if audit.exists():
            error = ProviderError('Antigravity tool attempt denied by preexecution guard')
            try:
                _parse_stream(raw, model)
            except ProviderError as detail:
                error.tool_evidence = getattr(detail, 'tool_evidence', {})
            raise error
        return _parse_stream(raw, model)
