import io
import json
import unittest
from unittest.mock import patch

from agenthub import codex_worker as worker
from agenthub.providers import ProviderError


def reply(identifier, result):
    return (json.dumps({'id': identifier, 'result': result}) + '\n').encode()


class Process:
    def __init__(self, output):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(output)
        self.pid = 123
        self.returncode = None
        self.requests = []

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -1

    def wait(self):
        self.requests = self.stdin.getvalue().splitlines()
        self.returncode = -1


class CodexDiscoveryTests(unittest.TestCase):
    def run_discovery(self, output):
        proc = Process(output)
        with patch.object(worker.subprocess, 'Popen', return_value=proc) as popen, patch.object(worker, '_stop', side_effect=lambda p: p.wait()):
            result = worker.discover_models('codex', 1)
        return result, [json.loads(x) for x in proc.requests], popen

    def test_protocol_pagination_and_model_request_name(self):
        out = reply(1, {}) + reply(2, {'account': {'type': 'chatgpt', 'email': 'private'}})
        out += reply(3, {'data': [{'id': 'catalog-id', 'model': 'request-model', 'displayName': 'Friendly', 'hidden': False}], 'nextCursor': 'page2'})
        out += reply(4, {'data': [{'id': 'x', 'model': 'second', 'displayName': 'Second'}], 'nextCursor': None})
        records, requests, popen = self.run_discovery(out)
        self.assertEqual([r['id'] for r in records], ['request-model', 'second'])
        self.assertEqual(records[0]['status'], 'discovery_only')
        self.assertEqual(requests[0]['method'], 'initialize')
        self.assertEqual(requests[1], {'method': 'initialized'})
        self.assertEqual(requests[2]['params'], {'refreshToken': False})
        self.assertEqual(requests[3]['params']['modelProvider'], 'openai')
        self.assertEqual(requests[4]['params']['cursor'], 'page2')
        self.assertEqual(popen.call_args.args[0], ['codex', 'app-server', '--listen', 'stdio://'])
        self.assertNotIn('OPENAI_API_KEY', popen.call_args.kwargs['env'])

    def test_api_account_and_errors_are_sanitized(self):
        with self.assertRaisesRegex(ProviderError, 'sign-in unavailable'):
            self.run_discovery(reply(1, {}) + reply(2, {'account': {'type': 'apiKey', 'secret': 'secret'}}))
        with self.assertRaises(ProviderError) as caught:
            self.run_discovery(reply(1, {}) + b'{"id":2,"error":{"message":"secret"}}\n')
        self.assertNotIn('secret', str(caught.exception))

    def test_timeout_cleans_up(self):
        proc = Process(b'')
        with patch.object(worker.subprocess, 'Popen', return_value=proc), patch.object(worker, '_stop', side_effect=lambda p: p.wait()) as stop:
            with self.assertRaises(ProviderError):
                worker.discover_models('codex', .01)
            stop.assert_called_once_with(proc)

    def test_generation_never_spawns_and_cancel(self):
        with patch.object(worker.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ProviderError, 'response-only'):
                worker.generate('codex', 'model', 'prompt', '.')
            class Cancel:
                def is_set(self): return True
            with self.assertRaisesRegex(ProviderError, 'cancelled'):
                worker.generate('codex', 'model', 'prompt', '.', cancel_event=Cancel())
            popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
