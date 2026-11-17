import io
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from agenthub import antigravity_worker as worker
from agenthub.providers import ProviderError

MODEL = 'gemini-3.8-flash-medium'


def reply(i, result):
    return json.dumps({'jsonrpc': '2.0', 'id': i, 'result': result}).encode() + b'\n'


def update(kind, **fields):
    return json.dumps({'method': 'session/update', 'params': {'update': {'sessionUpdate': kind, **fields}}}).encode() + b'\n'


def prefix():
    return (reply(1, {'protocolVersion': 1, 'agentInfo': {'name': 'Antigravity ACP Server'}})
            + reply(2, {'sessionId': 'session', 'models': {'availableModels': [{'modelId': MODEL}]}})
            + reply(3, {}) + reply(4, {}))


class Process:
    def __init__(self, output, errors=b''):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(output)
        self.stderr = io.BytesIO(errors)
        self.pid = 123
        self.returncode = None

    def poll(self):
        return self.returncode


class AntigravityWorkerTests(unittest.TestCase):
    def run_worker(self, output, errors=b'', timeout=1):
        proc = Process(output, errors)
        recorded = []
        def stop(p):
            recorded.extend(json.loads(x) for x in p.stdin.getvalue().splitlines())
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(worker, 'RESPONSE_ONLY_VERIFIED', True), patch.object(worker.subprocess, 'Popen', return_value=proc) as popen, patch.object(worker, '_stop', side_effect=stop) as cleanup:
                try:
                    result = worker.generate('agy', MODEL, 'Echo test', folder, timeout)
                except Exception:
                    self.assertEqual(cleanup.call_count, 1)
                    raise
                return result, recorded, popen

    def test_protocol_controls_and_success(self):
        result, requests, popen = self.run_worker(prefix() + update('agent_message_chunk', content={'type': 'text', 'text': 'OK'}) + reply(5, {'stopReason': 'end_turn'}) + reply(6, {}))
        self.assertEqual(result['text'], 'OK')
        self.assertIsNone(result['observed_model'])
        self.assertTrue(result['warnings'])
        caps = requests[0]['params']['clientCapabilities']
        self.assertFalse(caps['terminal'])
        self.assertFalse(caps['fs']['readTextFile'])
        self.assertEqual(requests[1]['params']['mcpServers'], [])
        self.assertEqual(requests[1]['params']['_meta']['agy']['enabledTools'], ['lao_no_tools'])
        self.assertEqual(requests[2]['params']['modelId'], MODEL)
        self.assertEqual(requests[3]['params']['modeId'], 'default')
        self.assertIn('--include-default-customizations=false', popen.call_args.args[0])
        self.assertNotIn('GEMINI_API_KEY', popen.call_args.kwargs['env'])

    def test_cancel_and_prompt_cap_before_spawn(self):
        event = threading.Event()
        event.set()
        with patch.object(worker.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ProviderError, '^Operation cancelled$'):
                worker.generate('agy', MODEL, 'prompt', '.', cancel_event=event)
            with self.assertRaisesRegex(ProviderError, '8000'):
                worker.generate('agy', MODEL, 'a' * 8001, '.')
            popen.assert_not_called()

    def test_production_gate_blocks_unverified_enforcement(self):
        with patch.object(worker.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ProviderError, 'preexecution tool exclusion remains unverified'):
                worker.generate('agy', MODEL, 'prompt', '.')
            popen.assert_not_called()

    def test_error_denial_and_nonterminal_status(self):
        for final in ({'stopReason': 'cancelled'}, {'stopReason': 'end_turn', 'denied_actions': ['secret']}, {'status': 'FAILED'}):
            with self.subTest(final=final), self.assertRaises(ProviderError) as caught:
                self.run_worker(prefix() + reply(5, final))
            self.assertNotIn('secret', str(caught.exception))

    def test_client_permission_requests_are_denied(self):
        packet = json.dumps({'id': 99, 'method': 'session/request_permission', 'params': {'options': [{'optionId': 'allow', 'kind': 'allow_always'}]}}).encode() + b'\n'
        proc = Process(prefix() + packet)
        sent = []
        with patch.object(worker, 'RESPONSE_ONLY_VERIFIED', True), patch.object(worker.subprocess, 'Popen', return_value=proc), patch.object(worker, '_stop', side_effect=lambda p: sent.extend(json.loads(x) for x in p.stdin.getvalue().splitlines())):
            with self.assertRaisesRegex(ProviderError, 'denied'):
                worker.generate('agy', MODEL, 'prompt', '.')
        self.assertEqual(sent[-1]['result']['outcome']['outcome'], 'cancelled')
        self.assertNotIn('optionId', sent[-1]['result']['outcome'])

    def test_tool_notification_is_failure(self):
        with self.assertRaisesRegex(ProviderError, 'prohibited tool'):
            self.run_worker(prefix() + update('tool_call', toolCallId='x', status='pending'))

    def test_fs_terminal_and_unknown_callbacks_are_denied(self):
        for method in ('fs/read_text_file', 'fs/write_text_file', 'terminal/create', 'approve'):
            with self.subTest(method=method):
                packet = json.dumps({'id': 99, 'method': method, 'params': {}}).encode() + b'\n'
                proc = Process(prefix() + packet)
                sent = []
                with patch.object(worker, 'RESPONSE_ONLY_VERIFIED', True), patch.object(worker.subprocess, 'Popen', return_value=proc), patch.object(worker, '_stop', side_effect=lambda p: sent.extend(json.loads(x) for x in p.stdin.getvalue().splitlines())):
                    with self.assertRaisesRegex(ProviderError, 'denied'):
                        worker.generate('agy', MODEL, 'prompt', '.')
                self.assertEqual(sent[-1]['error']['code'], -32601)

    def test_nonfinite_timeout_is_rejected_before_spawn(self):
        with patch.object(worker.subprocess, 'Popen') as popen:
            for timeout in (float('nan'), float('inf'), 0, -1, True):
                with self.subTest(timeout=timeout), self.assertRaises(ProviderError):
                    worker.generate('agy', MODEL, 'prompt', '.', timeout=timeout)
            popen.assert_not_called()

    def test_explicit_model_mismatch_is_failure(self):
        with self.assertRaisesRegex(ProviderError, 'different model'):
            self.run_worker(prefix() + reply(5, {'stopReason': 'end_turn', 'modelId': 'wrong'}))

    def test_invalid_protocol_timeout_and_output_bound(self):
        for output in (b'garbage\n', b'x' * (worker.MAX_LINE + 1)):
            with self.assertRaises(ProviderError):
                self.run_worker(output)
        with self.assertRaisesRegex(ProviderError, 'timed out'):
            self.run_worker(b'', timeout=.01)

    def test_stderr_structured_error_is_not_success(self):
        with self.assertRaises(ProviderError):
            self.run_worker(prefix(), errors=b'AGY_ERROR secret\n')


if __name__ == '__main__':
    unittest.main()
