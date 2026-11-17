import base64
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from agenthub import antigravity_worker as worker
from agenthub.providers import ProviderError

MODEL = 'gemini-3.8-flash-medium'


def stream(final=None, steps=(), model=MODEL, mode='proceed-in-sandbox'):
    events = [{'event': 'init', 'init': {'model': model, 'permission_mode': mode}}]
    events += [{'event': 'step_update', 'step_update': step} for step in steps]
    events += [{'event': 'result', 'result': final if final is not None else {'status': 'SUCCESS', 'response': 'OK', 'usage': {'input_tokens': 3}}}]
    return b'\n'.join(json.dumps(x).encode() for x in events) + b'\n'


class AntigravityWorkerTests(unittest.TestCase):
    def test_plain_response_and_selected_observed_distinction(self):
        result = worker._parse_stream(stream(), MODEL)
        self.assertEqual(result['text'], 'OK')
        self.assertIsNone(result['observed_model'])
        self.assertTrue(result['warnings'])
        result = worker._parse_stream(stream({'status': 'SUCCESS', 'response': 'OK', 'modelId': MODEL}), MODEL)
        self.assertEqual(result['observed_model'], MODEL)
        self.assertFalse(result['warnings'])

    def test_status_denials_and_missing_final(self):
        for final in ({'status': 'ERROR', 'response': 'secret'}, {'status': 'SUCCESS', 'response': 'OK', 'denied_actions': ['secret']}, {'status': 'SUCCESS', 'response': ''}):
            with self.subTest(final=final), self.assertRaises(ProviderError) as caught:
                worker._parse_stream(stream(final), MODEL)
            self.assertNotIn('secret', str(caught.exception))
        with self.assertRaises(ProviderError):
            worker._parse_stream(b'{"event":"init","init":{}}\n', MODEL)

    def test_model_mismatch_and_permission_bypass(self):
        for raw in (stream(model='wrong'), stream({'status': 'SUCCESS', 'response': 'OK', 'modelId': 'wrong'}), stream(mode='always-proceed')):
            with self.assertRaises(ProviderError):
                worker._parse_stream(raw, MODEL)

    def test_tool_and_delegation_events_rejected_with_sanitized_evidence(self):
        for name in ('read_file', 'write_to_file', 'run_command', 'invoke_subagent'):
            step = {'step_type': 'tool', 'tool_name': name, 'state': 'ERROR', 'tool_info': {'error': {'type': 'TOOL_ERROR', 'message': 'private canary path'}}}
            with self.subTest(name=name), self.assertRaises(ProviderError) as caught:
                worker._parse_stream(stream(steps=[step]), MODEL)
            self.assertEqual(caught.exception.tool_evidence['tool_name'], name)
            self.assertNotIn('private', str(caught.exception.tool_evidence))
        with self.assertRaises(ProviderError):
            worker._parse_stream(stream(steps=[{'step_type': 'agent_action', 'subagent_info': {'subagents': []}}]), MODEL)

    def test_invalid_stream_and_postterminal_events(self):
        for raw in (b'bad\n', b'[]\n', stream() + b'{"event":"init","init":{}}\n', b'x' * (worker.MAX_LINE + 1)):
            with self.assertRaises(ProviderError):
                worker._parse_stream(raw, MODEL)
        with self.assertRaisesRegex(ProviderError, 'failed execution step'):
            worker._parse_stream(stream(steps=[{'step_type': 'unknown', 'state': 'ERROR'}]), MODEL)

    def test_constant_guard_ignores_invalid_stdin_and_resets_preflight_audits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audit, startup, expected = worker._write_controls(root, worker._environment())
            self.assertFalse(audit.exists())
            self.assertFalse(startup.exists())
            cfg = json.loads((root / '.agents/hooks.json').read_text())
            command = cfg['local_agent_orchestrator_response_only']['PreToolUse'][0]['hooks'][0]['command']
            worker._preflight(command, {'decision': 'deny', 'reason': worker.GUARD_REASON}, worker._environment())
            self.assertTrue(audit.is_file())
            self.assertEqual(set(expected), {'.agents\\hooks.json'} if worker.os.name == 'nt' else {'.agents/hooks.json'})
            self.assertEqual(cfg['local_agent_orchestrator_response_only']['PreToolUse'][0]['matcher'], '*')

    def test_hook_commands_do_not_require_python_or_interpret_model_stdin(self):
        with tempfile.TemporaryDirectory() as folder, patch('sys.executable', 'frozen-app.exe'):
            marker = Path(folder) / "guard 'snowman-\u2603 & marker.txt"
            command = worker._guard_command(marker, {'decision': 'deny'})
            self.assertNotIn('frozen-app.exe', command)
            self.assertNotIn('ExecutionPolicy', command)
            if worker.os.name == 'nt':
                self.assertIn('-EncodedCommand', command)
                encoded = command.rsplit('"', 2)[1]
                script = base64.b64decode(encoded).decode('utf-16-le')
                self.assertIn("guard ''snowman-\u2603 & marker.txt", script)
                for token in ('ReadLine', '$input', 'Get-Content', 'stdin'):
                    self.assertNotIn(token, script)
            worker._preflight(command, {'decision': 'deny'}, worker._environment())
            self.assertEqual(marker.read_text(encoding='utf-8'), 'GUARD_CALLED')

    def test_failed_guard_preflight_prevents_inference(self):
        with patch.object(worker.subprocess, 'run', return_value=type('Failure', (), {'returncode': 7, 'stderr': b'', 'stdout': b'{}'})()):
            with self.assertRaisesRegex(ProviderError, 'preflight failed'):
                worker._preflight('constant guard command', {}, {})

    def test_generate_startup_and_unchanged_workspace_checks(self):
        def run(exe, model, prompt, workspace, *args):
            (workspace / 'guard-started.marker').write_text('GUARD_CALLED')
            return stream()
        with tempfile.TemporaryDirectory() as folder, patch.object(worker, 'RESPONSE_ONLY_VERIFIED', True), patch.object(worker, '_run', side_effect=run):
            self.assertEqual(worker.generate('agy', MODEL, 'prompt', folder)['text'], 'OK')
            self.assertEqual(list(Path(folder).iterdir()), [])
        with tempfile.TemporaryDirectory() as folder, patch.object(worker, 'RESPONSE_ONLY_VERIFIED', True), patch.object(worker, '_run', return_value=stream()):
            with self.assertRaisesRegex(ProviderError, 'guard startup'):
                worker.generate('agy', MODEL, 'prompt', folder)

    def test_denial_audit_rejects_success_and_unexpected_files_rejected(self):
        def run(exe, model, prompt, workspace, *args):
            (workspace / 'guard-started.marker').write_text('GUARD_CALLED')
            (workspace / 'guard-denied.marker').write_text('GUARD_CALLED')
            return stream(steps=[{'step_type': 'tool', 'tool_name': 'read_file', 'state': 'ERROR'}])
        with tempfile.TemporaryDirectory() as folder, patch.object(worker, 'RESPONSE_ONLY_VERIFIED', True), patch.object(worker, '_run', side_effect=run):
            with self.assertRaisesRegex(ProviderError, 'denied by preexecution') as caught:
                worker.generate('agy', MODEL, 'prompt', folder)
            self.assertEqual(caught.exception.tool_evidence['tool_name'], 'read_file')
        def modified(exe, model, prompt, workspace, *args):
            (workspace / 'guard-started.marker').write_text('GUARD_CALLED')
            (workspace / 'unexpected').write_text('CANARY')
            return stream()
        with tempfile.TemporaryDirectory() as folder, patch.object(worker, 'RESPONSE_ONLY_VERIFIED', True), patch.object(worker, '_run', side_effect=modified):
            with self.assertRaisesRegex(ProviderError, 'changed unexpectedly'):
                worker.generate('agy', MODEL, 'prompt', folder)

    def test_prompt_timeout_cancel_and_unverified_gate_before_spawn(self):
        event = threading.Event(); event.set()
        with patch.object(worker.subprocess, 'Popen') as popen:
            for prompt in ('', 'a' * 8001):
                with self.assertRaises(ProviderError): worker.generate('agy', MODEL, prompt, '.')
            for timeout in (float('nan'), float('inf'), 0, -1, True):
                with self.assertRaises(ProviderError): worker.generate('agy', MODEL, 'prompt', '.', timeout=timeout)
            with self.assertRaisesRegex(ProviderError, 'cancelled'): worker.generate('agy', MODEL, 'prompt', '.', cancel_event=event)
            with patch.object(worker, 'RESPONSE_ONLY_VERIFIED', False), self.assertRaisesRegex(ProviderError, 'validation is incomplete'):
                worker.generate('agy', MODEL, 'prompt', '.')
            popen.assert_not_called()

    def test_run_uses_session_denies_and_no_permission_bypass(self):
        class Process:
            returncode = 0
            pid = 123
            def poll(self): return 0
        def start(args, **kwargs):
            kwargs['stdout'].write(stream())
            return Process()
        with tempfile.TemporaryDirectory() as folder, patch.object(worker.subprocess, 'Popen', side_effect=start) as popen, patch.object(worker, '_stop') as stop:
            raw = worker._run('agy', MODEL, 'prompt', Path(folder), 10, None, worker._environment())
            self.assertEqual(worker._parse_stream(raw, MODEL)['text'], 'OK')
            args = popen.call_args.args[0]
            self.assertEqual(set(json.loads(args[args.index('--settings') + 1])['permissions']['deny']), set(worker.DENY_ACTIONS))
            self.assertNotIn('--dangerously-skip-permissions', args)
            self.assertEqual(popen.call_args.kwargs['env']['LOCAL_AGENT_ORCHESTRATOR_WORKER'], '1')
            self.assertNotIn('GEMINI_API_KEY', popen.call_args.kwargs['env'])
            stop.assert_called_once()

    def test_run_timeout_cancel_and_output_limit_cleanup(self):
        class Process:
            returncode = None
            pid = 123
            def poll(self): return None
        with tempfile.TemporaryDirectory() as folder:
            for event in (None, threading.Event()):
                if event: event.set()
                with patch.object(worker.subprocess, 'Popen', return_value=Process()), patch.object(worker, '_stop') as stop:
                    with self.assertRaisesRegex(ProviderError, 'timed out|cancelled'):
                        worker._run('agy', MODEL, 'prompt', Path(folder), .01, event, {})
                    stop.assert_called_once()
            def large(args, **kwargs):
                kwargs['stdout'].write(b'x' * (worker.MAX_STREAM + 1)); return Process()
            with patch.object(worker.subprocess, 'Popen', side_effect=large), patch.object(worker, '_stop') as stop:
                with self.assertRaisesRegex(ProviderError, 'size limit'):
                    worker._run('agy', MODEL, 'prompt', Path(folder), 10, None, {})
                stop.assert_called_once()


if __name__ == '__main__':
    unittest.main()
