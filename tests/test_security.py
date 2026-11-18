"""Synthetic security regressions: no real credentials or external endpoints."""
import base64
from contextlib import contextmanager
from http.client import BadStatusLine
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib import request

from agenthub.install import install_to
from agenthub.providers import ProviderError, ProviderManager, _endpoint, _find_executable, _system_tool
from agenthub.secrets import SecretStore
from agenthub.core import Hub
from agenthub.mcp import serve


class TransportEncodingTests(unittest.TestCase):
    def test_unicode_result_survives_legacy_windows_output_encoding(self):
        class FixtureHub:
            def connection_config(self, _):
                return {'text': '\u2192 \u2705 \u09ac\u09be\u0982\u09b2\u09be'}
        wire = io.BytesIO()
        sink = io.TextIOWrapper(wire, encoding='cp1252')
        source = io.StringIO(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'connection_config', 'arguments': {}}}) + '\n')
        serve(FixtureHub(), source, sink)
        sink.flush()
        result = json.loads(wire.getvalue().decode('utf-8'))
        payload = json.loads(result['result']['content'][0]['text'])
        self.assertEqual(payload['text'], '\u2192 \u2705 \u09ac\u09be\u0982\u09b2\u09be')


@contextmanager
def server(mode='normal', body=b'{"ok": true}'):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.server.received.append((self.path, self.headers.get('Authorization')))
            self.send_response(302 if mode == 'redirect' else 200)
            if mode == 'redirect':
                self.send_header('Location', self.server.redirect)
            self.end_headers()
            try:
                if mode == 'trickle':
                    for _ in range(100):
                        self.wfile.write(b' ')
                        self.wfile.flush()
                        time.sleep(.02)
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    instance.received = []
    thread = threading.Thread(target=lambda: instance.serve_forever(poll_interval=.02), daemon=True)
    thread.start()
    try:
        yield instance, 'http://127.0.0.1:' + str(instance.server_port)
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


class NetworkSecurityTests(unittest.TestCase):
    def setUp(self):
        self.manager = ProviderManager({}, lambda _: 'SYNTHETIC_KEY')

    def test_loopback_ignores_ambient_proxy(self):
        with server() as (target, target_url), server() as (proxy, proxy_url):
            with patch('urllib.request.getproxies', return_value={'http': proxy_url}), patch('urllib.request.proxy_bypass', return_value=False):
                # Demonstrate why the default opener is unsafe for local prompts.
                with request.build_opener().open(target_url, timeout=2) as response:
                    response.read()
                self.assertEqual(len(proxy.received), 1)
                self.assertEqual(target.received, [])
                result = self.manager._http('GET', target_url, headers={'Authorization': 'SYNTHETIC_KEY'}, timeout=2)
            self.assertTrue(result['ok'])
            self.assertEqual(len(proxy.received), 1)
            self.assertEqual(target.received, [('/', 'SYNTHETIC_KEY')])

    def test_redirect_does_not_replay_credentials(self):
        with server() as (sink, sink_url), server('redirect') as (origin, origin_url):
            origin.redirect = sink_url
            with self.assertRaisesRegex(ProviderError, '302'):
                self.manager._http('GET', origin_url, headers={'Authorization': 'SYNTHETIC_KEY'}, timeout=2)
            self.assertEqual(sink.received, [])

    def test_trickling_body_cannot_reset_overall_read_budget(self):
        with server('trickle') as (_, url):
            started = time.monotonic()
            with self.assertRaisesRegex(ProviderError, 'timed out'):
                self.manager._http('GET', url, timeout=.15)
            self.assertLess(time.monotonic() - started, 1)

    def test_cancel_is_checked_between_response_chunks(self):
        with server('trickle') as (_, url):
            cancel = threading.Event()
            timer = threading.Timer(.08, cancel.set)
            timer.start()
            try:
                started = time.monotonic()
                with self.assertRaisesRegex(ProviderError, 'cancelled'):
                    self.manager._http('GET', url, timeout=2, cancel_event=cancel)
                self.assertLess(time.monotonic() - started, 1)
            finally:
                timer.cancel()

    def test_response_limit_and_deep_json_fail_safely(self):
        with server(body=b' ' * 80) as (_, url), patch('agenthub.providers.MAX_RESPONSE', 64):
            with self.assertRaisesRegex(ProviderError, 'size limit'):
                self.manager._http('GET', url, timeout=2)
        with server(body=b'[' * 2000 + b']' * 2000) as (_, url):
            with self.assertRaisesRegex(ProviderError, 'Provider request failed'):
                self.manager._http('GET', url, timeout=2)
        with server() as (_, url), patch('agenthub.providers.json.loads', side_effect=RecursionError):
            with self.assertRaisesRegex(ProviderError, 'RecursionError'):
                self.manager._http('GET', url, timeout=2)

    def test_malformed_http_errors_do_not_echo_server_text(self):
        with patch('agenthub.providers.request.build_opener') as opener:
            opener.return_value.open.side_effect = BadStatusLine('SYNTHETIC_SECRET')
            with self.assertRaises(ProviderError) as result:
                self.manager._http('GET', 'https://example.invalid', timeout=2)
        self.assertNotIn('SYNTHETIC_SECRET', str(result.exception))

    def test_endpoint_rejects_parser_normalized_controls(self):
        for url in (' https://example.invalid', 'https://exam\nple.invalid', 'http://127.0.0.1/\tfoo', 'http://localhost/a b', 'https://example.invalid/\x7f'):
            with self.subTest(url=url), self.assertRaises(ProviderError):
                _endpoint(url)


@unittest.skipUnless(os.name == 'nt', 'Windows executable and junction handling')
class WindowsSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='lao-security-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_cwd_and_relative_path_entries_cannot_supply_executable(self):
        launch, trusted = self.root / 'launch', self.root / 'trusted'
        launch.mkdir()
        trusted.mkdir()
        (launch / 'claude.exe').write_bytes(b'UNTRUSTED_FIXTURE_NEVER_EXECUTE')
        (trusted / 'claude.exe').write_bytes(b'TRUSTED_FIXTURE_NEVER_EXECUTE')
        previous = Path.cwd()
        try:
            os.chdir(launch)
            with patch.dict(os.environ, {'PATH': os.pathsep.join(('', '.', str(launch), str(trusted)))}):
                self.assertEqual(Path(_find_executable('claude')), trusted / 'claude.exe')
            with patch.dict(os.environ, {'PATH': '.'}):
                self.assertIsNone(_find_executable('claude'))
        finally:
            os.chdir(previous)

    def test_relative_executable_and_batch_wrappers_rejected(self):
        manager = ProviderManager({}, lambda _: None)
        wrapper = self.root / 'claude.cmd'
        wrapper.write_text('SYNTHETIC NEVER EXECUTE')
        for value in ('relative/claude.exe', str(wrapper)):
            with self.assertRaises(ProviderError):
                manager._executable('claude', {'executable': value})
        self.assertEqual(Path(_system_tool('taskkill.exe')), Path(os.environ['SystemRoot']) / 'System32/taskkill.exe')

    def payload(self):
        app, worker = self.root / 'app.exe', self.root / 'worker.exe'
        app.write_bytes(b'FAKE_APP_NEVER_EXECUTE')
        worker.write_bytes(b'FAKE_WORKER_NEVER_EXECUTE')
        return app, worker

    def test_old_predictable_install_temp_cannot_overwrite_outside_file(self):
        app, worker = self.payload()
        target = self.root / 'installed'
        target.mkdir()
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'KEEP')
        (target / 'LocalAgentOrchestrator.exe.new').hardlink_to(outside)
        install_to(target, payload_app=app, payload_worker=worker, register=False)
        self.assertEqual(outside.read_bytes(), b'KEEP')
        self.assertEqual((target / 'LocalAgentOrchestrator.exe').read_bytes(), app.read_bytes())
        self.assertFalse(list(target.glob('.lao-write-*')))

    def test_linked_document_rejects_install_before_any_payload_write(self):
        app, worker = self.payload()
        target = self.root / 'installed'
        target.mkdir()
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'KEEP')
        (target / 'README.md').hardlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'Hardlinked'):
            install_to(target, payload_app=app, payload_worker=worker, register=False)
        self.assertFalse((target / 'LocalAgentOrchestrator.exe').exists())
        self.assertEqual(outside.read_bytes(), b'KEEP')

    def test_install_directory_junction_is_rejected(self):
        from _winapi import CreateJunction
        app, worker = self.payload()
        outside, target = self.root / 'outside', self.root / 'installed'
        outside.mkdir()
        CreateJunction(str(outside), str(target))
        try:
            with self.assertRaisesRegex(ValueError, 'Linked'):
                install_to(target, payload_app=app, payload_worker=worker, register=False)
        finally:
            target.rmdir()  # Junction only; never recursively remove its target.
        self.assertEqual(list(outside.iterdir()), [])

    def test_credentials_are_encrypted_and_tampering_is_rejected(self):
        path = self.root / 'credentials.json'
        store = SecretStore(path)
        store.set('fixture', 'SYNTHETIC_KEY_NOT_REAL')
        self.assertNotIn('SYNTHETIC_KEY_NOT_REAL', path.read_text())
        self.assertEqual(store.get('fixture'), 'SYNTHETIC_KEY_NOT_REAL')
        saved = json.loads(path.read_text())
        blob = bytearray(base64.b64decode(saved['fixture']))
        blob[-1] ^= 1
        saved['fixture'] = base64.b64encode(blob).decode()
        path.write_text(json.dumps(saved))
        with self.assertRaises(RuntimeError):
            store.get('fixture')

    def test_predictable_settings_and_credentials_temps_cannot_overwrite(self):
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'KEEP')
        data = self.root / 'data'
        hub = Hub(data)
        hub.config_path.with_suffix('.tmp').hardlink_to(outside)
        hub.save_config(hub.config)
        self.assertEqual(outside.read_bytes(), b'KEEP')
        hub.secrets.path.with_suffix('.tmp').hardlink_to(outside)
        hub.secrets.set('fixture', 'SYNTHETIC_NOT_REAL')
        self.assertEqual(outside.read_bytes(), b'KEEP')
        self.assertEqual(hub.secrets.get('fixture'), 'SYNTHETIC_NOT_REAL')
