import json
import sys
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from agenthub import __version__
from agenthub.connection_check import _exchange
from agenthub.install import setup_installation
from agenthub.mcp import TOOLS


class ConnectionTests(unittest.TestCase):
    def run_fixture(self, mode, timeout=3):
        script = '''import json, sys, time, subprocess
mode = sys.argv[1]
if mode == "timeout":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    open(sys.argv[4], "w").write(str(child.pid))
    time.sleep(30)
    sys.exit()
if mode == "exit": sys.exit(1)
first = json.loads(sys.stdin.readline())
assert first["method"] == "initialize"
version = "wrong" if mode == "version" else sys.argv[2]
if mode == "oversize":
    print("x" * 270000, flush=True)
    sys.exit()
print(json.dumps({"jsonrpc":"2.0", "id":1, "result":{"protocolVersion":"bad" if mode == "protocol" else "2025-03-26", "capabilities":{} if mode == "capabilities" else {"tools":{}}, "serverInfo":{"name":"local-agent-orchestrator", "version":version}}}), flush=True)
if mode == "version": sys.exit()
assert json.loads(sys.stdin.readline())["method"] == "notifications/initialized"
assert json.loads(sys.stdin.readline())["method"] == "tools/list"
names = json.loads(sys.argv[3])
if mode == "missing": names.pop()
print(json.dumps({"jsonrpc":"2.0", "id":2, "result":{"tools":[{"name":n} for n in names]}}), flush=True)
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixture.py'
            path.write_text(script, encoding='utf-8')
            result = _exchange([sys.executable, str(path), mode, __version__, json.dumps([n for n, _, _ in TOOLS]), str(Path(tmp) / 'pid')], timeout)
            if mode == 'timeout':
                pid = int((Path(tmp) / 'pid').read_text())
                if os.name == 'nt':
                    import ctypes
                    from ctypes import wintypes
                    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                    kernel.OpenProcess.restype = wintypes.HANDLE
                    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                    handle = kernel.OpenProcess(0x1000, False, pid)
                    if handle:
                        code = wintypes.DWORD()
                        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                        kernel.CloseHandle(handle)
                        self.assertNotEqual(code.value, 259, 'fixture child survived cleanup')
                else:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        pass
                    else:
                        self.assertEqual(Path('/proc', str(pid), 'stat').read_text().split()[2], 'Z')
            return result

    def test_protocol_and_validation(self):
        self.assertTrue(self.run_fixture('ok')['ok'])
        self.assertFalse(self.run_fixture('version')['ok'])
        self.assertFalse(self.run_fixture('missing')['ok'])
        self.assertFalse(self.run_fixture('exit')['ok'])
        self.assertFalse(self.run_fixture('protocol')['ok'])
        self.assertFalse(self.run_fixture('capabilities')['ok'])
        self.assertFalse(self.run_fixture('oversize')['ok'])

    def test_timeout_is_bounded(self):
        start = time.monotonic()
        self.assertEqual(self.run_fixture('timeout', 1)['status'], 'connection timed out')
        self.assertLess(time.monotonic() - start, 4)

    def test_partial_setup_report_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch('agenthub.install.install_to', return_value=Path(tmp)), mock.patch('agenthub.install.register_default_hosts', return_value=[{'id':'claude', 'name':'Claude', 'path':'config', 'status':'unchanged', 'reason':'A different entry already exists; review it in host settings.'}]), mock.patch('agenthub.connection_check.check_installed_server', return_value={'ok': True, 'status': 'MCP server responded'}):
                report = setup_installation()
            self.assertFalse(report['ok'])
            saved = (Path(tmp) / 'setup-report.json').read_text(encoding='utf-8')
            self.assertNotIn('secret', saved)
            self.assertEqual(report['hosts'][0]['status'], 'unchanged')

    def test_skipped_hosts_are_truthful_and_probe_failure_is_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch('agenthub.install.install_to', return_value=Path(tmp)), mock.patch('agenthub.install.register_default_hosts') as register, mock.patch('agenthub.connection_check.check_installed_server', return_value={'ok': False, 'status': 'connection timed out'}):
                report = setup_installation(connect=False)
            register.assert_not_called()
            self.assertEqual(report['host_registration'], 'skipped')
            self.assertFalse(report['ok'])


    def test_host_detail_reports_safe_reasons(self):
        from agenthub.install import register_default_hosts
        from agenthub.hosts import host_targets
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app = base / 'app'
            app.mkdir()
            exe = app / 'LocalAgentOrchestratorMCP.exe'
            exe.write_bytes(b'fixture')
            home = base / 'profile'
            home.mkdir()
            config = home / '.claude.json'
            config.write_text(json.dumps({'mcpServers': {'local-agent-orchestrator': {'command': str(exe), 'enabled': False, 'env': {'TOKEN': 'secret'}}}}))
            details = register_default_hosts(app, home=home, environ={}, detailed=True)
            item = next(item for item in details if item['id'] == 'claude-code')
            self.assertEqual(item['status'], 'unchanged')
            self.assertIn('Disabled', item['reason'])
            self.assertEqual(item['path'], str(config))
            self.assertNotIn('secret', json.dumps(details))
            self.assertEqual(len(details), len(host_targets(home, {})))

if __name__ == '__main__': unittest.main()
