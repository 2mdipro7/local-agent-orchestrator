import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from agenthub.mcp import MAX_REQUEST_CHARACTERS, serve


class BoundedSource(io.StringIO):
    def __init__(self, value):
        super().__init__(value)
        self.read_sizes = []

    def __iter__(self):
        raise AssertionError('Unbounded line iteration is forbidden')

    def readline(self, size=-1):
        if not 0 < size <= MAX_REQUEST_CHARACTERS + 1:
            raise AssertionError('Every input read must have a bounded size')
        self.read_sizes.append(size)
        return super().readline(size)


class McpFramingTests(unittest.TestCase):
    ping = json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'ping'}) + '\n'

    def replies(self, source):
        sink = io.StringIO()
        serve(object(), source, sink)
        return [json.loads(line) for line in sink.getvalue().splitlines()]

    def test_oversized_frame_is_drained_in_bounded_chunks_and_recovers(self):
        source = BoundedSource('x' * (MAX_REQUEST_CHARACTERS + 3 * 65536) + '\n' + self.ping)
        replies = self.replies(source)
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]['error']['code'], -32700)
        self.assertIsNone(replies[0]['id'])
        self.assertEqual(replies[1]['id'], 7)
        self.assertEqual(replies[1]['result'], {})
        self.assertGreaterEqual(source.read_sizes.count(65536), 3)

    def test_oversized_unterminated_frame_reports_once_at_eof(self):
        replies = self.replies(BoundedSource('x' * (MAX_REQUEST_CHARACTERS + 1)))
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0]['error']['code'], -32700)

    def test_binary_transport_recovers_after_bad_utf8_and_oversized_frame(self):
        source = io.BytesIO(b'{"id":"\xff"}\n' + b'x' * (MAX_REQUEST_CHARACTERS + 3) + b'\n' + self.ping.encode())
        replies = self.replies(source)
        self.assertEqual([r.get('error', {}).get('code') for r in replies], [-32700, -32700, None])
        self.assertEqual(replies[-1]['id'], 7)

    def test_real_entry_uses_utf8_despite_legacy_python_io_encoding(self):
        import os
        import tempfile
        request = json.dumps({'jsonrpc': '2.0', 'id': '\u09ac\u09be\u0982\u09b2\u09be', 'method': 'ping'}, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run([sys.executable, 'mcp_entry.py', '--home', home],
                input=(request + '\n').encode('utf-8'), capture_output=True, timeout=10,
                env={**os.environ, 'PYTHONIOENCODING': 'cp1252'},
                cwd=Path(__file__).resolve().parents[1],
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.decode('utf-8'))['id'], '\u09ac\u09be\u0982\u09b2\u09be')

    def test_json_recursion_error_does_not_stop_next_request(self):
        # Decoder recursion thresholds vary by Python build. Inject its actual
        # failure type without depending on a large nesting depth.
        deep = '[' * 32 + '0' + ']' * 32 + '\n'
        decode = json.loads

        def recursion_failure(value, *args, **kwargs):
            if value == deep:
                raise RecursionError('synthetic decoder nesting limit')
            return decode(value, *args, **kwargs)

        with patch('agenthub.mcp.json.loads', side_effect=recursion_failure):
            replies = self.replies(BoundedSource(deep + self.ping))
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]['error']['code'], -32700)
        self.assertEqual(replies[1]['id'], 7)

    def test_stringio_and_stdio_text_stream_accept_normal_and_final_frames(self):
        request = json.dumps({'jsonrpc': '2.0', 'id': 'বাংলা', 'method': 'ping'}, ensure_ascii=False)
        sources = [io.StringIO(request), io.TextIOWrapper(io.BytesIO((request + '\n').encode('utf-8')), encoding='utf-8')]
        for source in sources:
            with source, self.subTest(source=type(source).__name__):
                replies = self.replies(source)
                self.assertEqual(replies[0]['id'], 'বাংলা')
                self.assertEqual(replies[0]['result'], {})

    def test_real_stdio_pipe_accepts_a_normal_request(self):
        result = subprocess.run(
            [sys.executable, '-c', 'from agenthub.mcp import serve; serve(object())'],
            input=self.ping, capture_output=True, text=True, timeout=10,
            cwd=Path(__file__).resolve().parents[1],
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['id'], 7)


if __name__ == '__main__':
    unittest.main()
