import io
import json
import threading
import unittest
from unittest.mock import patch

from agenthub.mcp import serve
from agenthub.providers import ProviderManager


class DiscoveryTests(unittest.TestCase):
    def test_worker_cannot_call_orchestrator(self):
        for name in ('submit_task', 'review_task', 'list_tasks'):
            request = json.dumps({'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': {}}}) + '\n'
            sink = io.StringIO()
            with patch.dict('os.environ', {'LOCAL_AGENT_ORCHESTRATOR_WORKER': '1'}):
                serve(object(), io.StringIO(request), sink)
            result = json.loads(sink.getvalue())['result']
            self.assertTrue(result['isError'])
            self.assertIn('Delegated workers', result['content'][0]['text'])

    def test_blocked_probe_does_not_block_task_history_or_start_duplicates(self):
        entered, release = threading.Event(), threading.Event()
        class Hub:
            home = 'synthetic'
            config = {'providers': {}}
            def discover_models(self):
                entered.set()
                release.wait(3)
                return []
            def list_tasks(self):
                return []
            def hardware_info(self):
                return {'logical_processors': 1}
        class Sink(io.StringIO):
            def write(self, text):
                result = super().write(text)
                if json.loads(text).get('id') == 4:
                    release.set()
                return result
        def request(i, name):
            return json.dumps({'id': i, 'method': 'tools/call', 'params': {'name': name, 'arguments': {}}}) + '\n'
        def source():
            yield request(1, 'list_models')
            self.assertTrue(entered.wait(1))
            yield request(2, 'list_models')
            yield request(3, 'list_tasks')
            yield request(4, 'hub_status')
        sink = Sink()
        serve(Hub(), source(), sink)
        results = [json.loads(x) for x in sink.getvalue().splitlines()]
        self.assertEqual([r['id'] for r in results], [2, 3, 4, 1])
        self.assertTrue(results[0]['result']['isError'])
        status = json.loads(results[2]['result']['content'][0]['text'])
        self.assertEqual(status['active_tasks'], 0)
        self.assertIn('version', status)

    def test_provider_timeout_partial_results_and_probe_reuse(self):
        manager = ProviderManager({'providers': {'fast': {'enabled': True}, 'slow': {'enabled': True}}}, lambda _: None)
        entered, release = threading.Event(), threading.Event()
        counts = {'fast': 0, 'slow': 0}
        def discover(provider, cfg):
            counts[provider] += 1
            if provider == 'slow':
                entered.set()
                release.wait(3)
            return [{'provider': provider, 'id': 'synthetic', 'status': 'available'}]
        with patch.object(manager, '_discover_one', side_effect=discover):
            try:
                first = manager.discover(.1)
                self.assertTrue(entered.is_set())
                second = manager.discover(.01)
                self.assertEqual(counts, {'fast': 1, 'slow': 1})
                self.assertEqual(first[0]['status'], 'available')
                self.assertEqual(second[1]['status'], 'unavailable')
                self.assertIn('deadline', second[1]['reason'])
            finally:
                release.set()
            self.assertEqual(manager.discover(1)[1]['status'], 'available')


if __name__ == '__main__':
    unittest.main()
