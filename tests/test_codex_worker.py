import io
import json
import unittest
import tempfile
import os
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
        self.assertEqual(records[0]['status'], 'unverified')
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

    def test_cleanup_is_bounded_when_process_refuses_to_exit(self):
        from unittest.mock import Mock
        import subprocess
        proc = Mock(pid=123)
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired('codex', 2)
        with patch.object(worker.os, 'name', 'nt'), patch.object(worker.subprocess, 'run', side_effect=subprocess.TimeoutExpired('taskkill', 2)) as kill_tree:
            worker._stop(proc)
        self.assertEqual(kill_tree.call_args.kwargs['timeout'], 2)
        self.assertEqual(kill_tree.call_args.kwargs['stdin'], subprocess.DEVNULL)
        proc.kill.assert_called_once()
        proc.wait.assert_called_once_with(timeout=2)

    def test_catalog_narrows_only_tool_capabilities(self):
        original = {'slug': 'chosen', 'context_window': 1000, 'other': {'x': 1},
                    'tool_mode': 'code_mode_only', 'shell_type': 'unified_exec',
                    'apply_patch_tool_type': 'freeform', 'experimental_supported_tools': ['x'],
                    'supports_search_tool': True}
        result = worker.narrowed_catalog([original], 'chosen')['models'][0]
        self.assertEqual(result['slug'], 'chosen')
        self.assertEqual(result['context_window'], 1000)
        self.assertEqual((result['tool_mode'], result['shell_type'], result['apply_patch_tool_type']),
                         ('direct', 'disabled', None))
        self.assertEqual(result['experimental_supported_tools'], [])
        self.assertFalse(result['supports_search_tool'])
        self.assertEqual(original['shell_type'], 'unified_exec')
        with self.assertRaises(ProviderError):
            worker.narrowed_catalog([original, original], 'chosen')

    def test_startup_restrictions_are_child_only_and_validate_names(self):
        args = worker.restricted_server_args('codex', 'C:/tmp/catalog.json', ['alpha', 'beta'])
        for flag in ['cloud.skills.enabled=false', 'orchestrator.mcp.enabled=false',
                     'agents.enabled=false', 'mcp_servers.alpha.enabled=false']:
            self.assertIn(flag, args)
        self.assertIn('goals', args)
        self.assertNotIn('--ignore-rules', args)
        with self.assertRaises(ProviderError):
            worker.restricted_server_args('codex', 'catalog', ['bad.name'])

    def test_rpc_turn_success_failure_and_forbidden_action(self):
        from types import SimpleNamespace
        def event(method, params):
            return (json.dumps({'method': method, 'params': params}) + '\n').encode()
        def run_case(model='chosen', terminal='completed', tool=False):
            out = reply(1, {}) + reply(2, {'account': {'type': 'chatgpt'}})
            out += reply(3, {'model': model, 'modelProvider': 'openai', 'thread': {'id': 'thread'}})
            out += reply(4, {'data': [], 'nextCursor': None})
            out += reply(5, {'turn': {'id': 'turn'}})
            if tool:
                out += event('item/started', {'item': {'type': 'commandExecution'}})
            else:
                out += event('item/completed', {'item': {'type': 'agentMessage', 'text': 'READY', 'phase': 'final_answer'}})
                out += event('turn/completed', {'threadId': 'thread', 'turn': {'id': 'turn', 'status': terminal, 'error': None}})
            proc = Process(out)
            with tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(tmp, 'models_cache.json'), 'w', encoding='utf-8') as f:
                    json.dump({'models': [{'slug': 'chosen'}]}, f)
                with patch.dict(os.environ, {'CODEX_HOME': tmp}), patch.object(worker.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'codex-cli 0.169.0-alpha.11.1')), patch.object(worker, '_list_server_names', return_value=[]), patch.object(worker.subprocess, 'Popen', return_value=proc), patch.object(worker, '_stop', side_effect=lambda p: p.wait()):
                    return worker.generate('codex', 'chosen', 'Reply READY', tmp, timeout=1)
        self.assertEqual(run_case()['text'], 'READY')
        self.assertIsNone(run_case()['observed_model'])
        with self.assertRaisesRegex(ProviderError, 'mismatch'):
            run_case(model='other')
        with self.assertRaisesRegex(ProviderError, 'turn failed'):
            run_case(terminal='failed')
        with self.assertRaisesRegex(ProviderError, 'attempted'):
            run_case(tool=True)

    def test_generation_never_spawns_and_cancel(self):
        with patch.object(worker.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ProviderError, 'Invalid'):
                worker.generate('codex', 'model', 'x' * 8001, '.')
            class Cancel:
                def is_set(self): return True
            with self.assertRaisesRegex(ProviderError, 'cancelled'):
                worker.generate('codex', 'model', 'prompt', '.', cancel_event=Cancel())
            popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
