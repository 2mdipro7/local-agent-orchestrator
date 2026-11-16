import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib import error

from agenthub.providers import ProviderManager, ProviderError, _endpoint

PNG = b'\x89PNG\r\n\x1a\nexample'


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.cfg = {'providers': {'ollama': {'enabled': True}, 'openai_compatible': {'enabled': True, 'base_url': 'https://api.example/v1'}, 'gemini': {'enabled': True}, 'claude': {'enabled': True}, 'opencode': {'enabled': True}}}
        self.manager = ProviderManager(self.cfg, lambda name: 'secret-key')

    def test_endpoint_restrictions(self):
        for url in ('http://example.com', 'https://user:secret@example.com', 'https://example.com/?token=x', 'https://example.com/#x'):
            with self.assertRaises(ProviderError):
                _endpoint(url)
        self.assertEqual(_endpoint('http://[::1]:1234/v1/'), 'http://[::1]:1234/v1')

    def test_ollama_image_request(self):
        image = self.out / 'input.png'
        image.write_bytes(PNG)
        with mock.patch.object(self.manager, '_http', return_value={'message': {'content': 'yes'}, 'model': 'observed'}) as send:
            result = self.manager.generate('ollama', 'chosen', 'describe', output_dir=self.out, images=[image])
        args = send.call_args.args
        self.assertEqual(args[1], 'http://127.0.0.1:11434/api/chat')
        self.assertEqual(args[2]['messages'][0]['images'], [base64.b64encode(PNG).decode()])
        self.assertFalse(args[2]['stream'])
        self.assertEqual(result['observed_model'], 'observed')

    def test_openai_image_and_gemini_parts(self):
        encoded = base64.b64encode(PNG).decode()
        with mock.patch.object(self.manager, '_http', return_value={'data': [{'b64_json': encoded}]}) as send:
            result = self.manager.generate('openai_compatible', 'm', 'draw', output_dir=self.out, task_kind='image')
        self.assertEqual(send.call_args.args[2]['response_format'], 'b64_json')
        self.assertEqual((self.out / result['artifacts'][0]).read_bytes(), PNG)
        obj = {'modelVersion': 'actual', 'candidates': [{'content': {'parts': [{'text': 'hello'}, {'inlineData': {'data': encoded, 'mimeType': 'image/png'}}]}}]}
        with mock.patch.object(self.manager, '_http', return_value=obj) as send:
            result = self.manager.generate('gemini', 'x/y', 'draw', output_dir=self.out, task_kind='image')
        self.assertIn('x%2Fy:generateContent', send.call_args.args[1])
        self.assertEqual(send.call_args.args[3]['x-goog-api-key'], 'secret-key')
        self.assertEqual(result['text'], 'hello')
        self.assertEqual(result['observed_model'], 'actual')
        self.assertEqual(len(result['artifacts']), 1)

    def test_unavailable_and_unsupported(self):
        with self.assertRaises(ProviderError):
            self.manager.generate('missing', 'm', 'p', output_dir=self.out)
        with self.assertRaises(ProviderError):
            self.manager.generate('ollama', 'm', 'p', output_dir=self.out, task_kind='image')
        with self.assertRaises(ProviderError):
            self.manager.generate('opencode', 'm', 'p', output_dir=self.out)
        with mock.patch.object(self.manager, '_http', return_value={'data': [{'url': 'https://other/image'}]}):
            with self.assertRaises(ProviderError):
                self.manager.generate('openai_compatible', 'm', 'p', output_dir=self.out, task_kind='image')

    def test_discovery_isolated_errors(self):
        self.cfg['providers'] = {'ollama': {'enabled': True}, 'lmstudio': {'enabled': True}, 'gemini': {'enabled': False}}
        with mock.patch.object(self.manager, '_http', side_effect=[ProviderError('bad'), {'data': [{'id': 'model'}]}]):
            result = self.manager.discover()
        self.assertEqual(result[0]['status'], 'unavailable')
        self.assertEqual(result[1]['id'], 'model')

    def test_no_redirect_and_secret_safe_error(self):
        response = error.HTTPError('https://secret-key@example.com', 302, 'secret-key', {}, None)
        with mock.patch('agenthub.providers.request.build_opener') as opener:
            opener.return_value.open.side_effect = response
            with self.assertRaises(ProviderError) as ctx:
                self.manager._http('GET', 'https://example.com', headers={'Authorization': 'secret-key'})
        self.assertNotIn('secret-key', str(ctx.exception))
        self.assertIn('302', str(ctx.exception))
        response.close()

    def test_cli_arguments_and_denial(self):
        with mock.patch.object(self.manager, '_executable', return_value='claude.exe'), mock.patch.object(self.manager, '_process', return_value=json.dumps({'result': 'ok', 'modelUsage': {'actual': {}}})) as run:
            result = self.manager.generate('claude', 'exact-model', 'hi', output_dir=self.out)
        self.assertEqual(run.call_args.args[0], ['claude.exe', '--model', 'exact-model', '-p', 'hi', '--tools', '', '--max-turns', '1', '--output-format', 'json'])
        self.assertEqual(result['observed_model'], 'actual')
        with mock.patch.object(self.manager, '_executable', return_value='claude.exe'), mock.patch.object(self.manager, '_process', return_value='{"permission_denials":[{}]}'):
            with self.assertRaises(ProviderError):
                self.manager.generate('claude', 'm', 'p', output_dir=self.out)

    def test_cancel_and_timeout(self):
        event = threading.Event()
        event.set()
        with self.assertRaisesRegex(ProviderError, 'cancelled'):
            self.manager.generate('ollama', 'm', 'p', output_dir=self.out, cancel_event=event)
        proc = mock.Mock(pid=123, returncode=None)
        proc.poll.return_value = None
        with mock.patch('agenthub.providers.subprocess.Popen', return_value=proc), mock.patch('agenthub.providers.time.monotonic', side_effect=[0, 2]), mock.patch('agenthub.providers.subprocess.run'):
            with self.assertRaisesRegex(ProviderError, 'timed out'):
                self.manager._process(['x'], self.out, 1)

    def test_agy_discovery_and_restricted_execution(self):
        self.cfg['providers'] = {'antigravity': {'enabled': True}}
        listing = 'Fetching available models...\nmodel-one\tModel One\nmodel-two\tModel Two\n'
        with mock.patch.object(self.manager, '_executable', return_value='agy.exe'), mock.patch.object(self.manager, '_process', return_value=listing):
            models = self.manager.discover()
        self.assertEqual([(m['id'], m['name']) for m in models], [('model-one', 'Model One'), ('model-two', 'Model Two')])
        with mock.patch.object(self.manager, '_executable', return_value='agy.exe'), mock.patch.object(self.manager, '_process', return_value='{"response":"ok"}') as run:
            self.manager.generate('antigravity', 'model-one', 'prompt', output_dir=self.out)
        args = run.call_args.args[0]
        self.assertIn('--sandbox', args)
        settings = json.loads(args[args.index('--settings') + 1])
        self.assertEqual(settings['permissions']['deny'], ['command(*)', 'mcp(*)', 'read_url(*)', 'execute_url(*)', 'download_url(*)', 'read_file(*)', 'write_file(*)'])
        with mock.patch.object(self.manager, '_executable', return_value='agy.exe'), mock.patch.object(self.manager, '_process', return_value='{"denied_actions":[{}]}'):
            with self.assertRaises(ProviderError):
                self.manager.generate('antigravity', 'model-one', 'prompt', output_dir=self.out)

    def test_local_loopback_and_ollama_limits(self):
        self.cfg['providers']['ollama']['base_url'] = 'https://remote.example'
        with self.assertRaises(ProviderError):
            self.manager.generate('ollama', 'qwen3:8b', 'hi', output_dir=self.out)
        self.cfg['providers']['ollama']['base_url'] = 'http://127.0.0.1:11434'
        with mock.patch.object(self.manager, '_http', return_value={'message': {'content': 'ok'}}) as send:
            self.manager.generate('ollama', 'qwen3:8b', 'hi', output_dir=self.out)
        payload = send.call_args.args[2]
        self.assertEqual(payload['keep_alive'], '2m')
        self.assertEqual(payload['options'], {'num_ctx': 4096, 'num_predict': 1024})
        self.assertFalse(payload['think'])

    def test_claude_candidates_and_winget_path(self):
        self.cfg['providers'] = {'claude': {'enabled': True}}
        with mock.patch.object(self.manager, '_executable', return_value='claude.exe'):
            models = self.manager.discover()
        self.assertEqual([x['id'] for x in models], ['claude-sonnet-5-5', 'claude-opus-5-5', 'claude-haiku-5-5'])
        self.assertTrue(all(x['status'] == 'unverified' for x in models))
        target = self.out / 'Microsoft' / 'WinGet' / 'Packages' / 'Anthropic.ClaudeCode_example' / 'claude.exe'
        target.parent.mkdir(parents=True)
        target.touch()
        with mock.patch.dict('os.environ', {'LOCALAPPDATA': str(self.out)}), mock.patch('agenthub.providers.shutil.which', return_value=None):
            self.assertEqual(Path(self.manager._executable('claude', {})), target)

    def test_openai_local_key_optional_remote_required(self):
        self.manager.secret_getter = lambda name: None
        self.cfg['providers']['openai_compatible']['base_url'] = 'http://127.0.0.1:7777/v1'
        with mock.patch.object(self.manager, '_http', return_value={'choices': [{'message': {'content': 'ok'}}]}) as send:
            self.manager.generate('openai_compatible', 'm', 'hi', output_dir=self.out)
        self.assertEqual(send.call_args.args[3], {})
        self.cfg['providers']['openai_compatible']['base_url'] = 'https://remote.example/v1'
        with self.assertRaisesRegex(ProviderError, 'Credential unavailable'):
            self.manager.generate('openai_compatible', 'm', 'hi', output_dir=self.out)

    def test_ollama_capabilities_and_opencode_status(self):
        self.cfg['providers'] = {'ollama': {'enabled': True}, 'opencode': {'enabled': True}}
        data = {'models': [{'name': 'a', 'capabilities': ['completion', 'vision']}, {'name': 'b', 'capabilities': ['thinking']}, {'name': 'c'}]}
        with mock.patch.object(self.manager, '_http', return_value=data), mock.patch.object(self.manager, '_executable', return_value='opencode.exe'), mock.patch.object(self.manager, '_process', return_value='provider/model'):
            result = self.manager.discover()
        self.assertEqual([x['modality'] for x in result[:3]], ['text, image input', 'text', 'text'])
        self.assertEqual(result[3]['status'], 'discovery_only')

    def test_output_bounds_and_local_secret_retrieval(self):
        self.cfg['providers']['openai_compatible']['base_url'] = 'http://127.0.0.1:9999/v1'
        getter = mock.Mock(return_value=None)
        self.manager.secret_getter = getter
        with mock.patch.object(self.manager, '_http', return_value={'choices': [{'message': {'content': 'ok'}}]}) as send:
            self.manager.generate('openai_compatible', 'm', 'p', output_dir=self.out)
        self.assertEqual(send.call_args.args[2]['max_tokens'], 1024)
        getter.assert_not_called()
        self.manager.secret_getter = lambda _: 'secret'
        with mock.patch.object(self.manager, '_http', return_value={'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}) as send:
            self.manager.generate('gemini', 'm', 'p', output_dir=self.out)
        self.assertEqual(send.call_args.args[2]['generationConfig'], {'maxOutputTokens': 1024})
        encoded = base64.b64encode(PNG).decode()
        with mock.patch.object(self.manager, '_http', return_value={'candidates': [{'content': {'parts': [{'inlineData': {'data': encoded}}]}}]}) as send:
            self.manager.generate('gemini', 'm', 'p', output_dir=self.out, task_kind='image')
        self.assertEqual(send.call_args.args[2]['generationConfig'], {'responseModalities': ['TEXT', 'IMAGE'], 'candidateCount': 1})

if __name__ == '__main__':
    unittest.main()
