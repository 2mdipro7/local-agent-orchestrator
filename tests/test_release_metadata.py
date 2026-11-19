import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_windows
from release_metadata import version_resource, windows_version


class ReleaseMetadataTests(unittest.TestCase):
    def test_version_validation(self):
        self.assertEqual(windows_version('1.2.3-rc.1+build.05'), (1, 2, 3, 0))
        for version in ('1.2', '01.2.3', '1.2.3-01', '1.2.3;', '1.2.3\n', '65536.0.0', '-1.2.3', '1.2.3+bad!', ''):
            with self.subTest(version=version), self.assertRaises(ValueError):
                windows_version(version)

    def test_resource_metadata_is_valid_pyinstaller_resource(self):
        from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file
        with tempfile.TemporaryDirectory() as directory:
            for worker, name, description in [(True, 'LocalAgentOrchestratorMCP', 'Local Agent Orchestrator MCP Server'), (False, 'LocalAgentOrchestrator', 'Local Agent Orchestrator')]:
                path = Path(directory) / 'version.txt'
                path.write_text(version_resource('1.2.3-rc.1', worker=worker), encoding='utf-8')
                info = load_version_info_from_text_file(str(path))
                self.assertEqual((info.ffi.fileVersionMS, info.ffi.fileVersionLS), (0x10002, 0x30000))
                self.assertEqual((info.ffi.productVersionMS, info.ffi.productVersionLS), (0x10002, 0x30000))
                fields = {item.name: item.val for item in info.kids[0].kids[0].kids}
                self.assertEqual(fields['ProductName'], 'Local Agent Orchestrator')
                self.assertEqual(fields['CompanyName'], 'Mehrab Mashrafi')
                self.assertEqual(fields['ProductVersion'], '1.2.3-rc.1')
                self.assertEqual(fields['FileVersion'], '1.2.3-rc.1')
                self.assertEqual(fields['InternalName'], name)
                self.assertEqual(fields['OriginalFilename'], name + '.exe')
                self.assertEqual(fields['FileDescription'], description)

    def test_stages_and_worker_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / 'dist/LocalAgentOrchestratorMCP.exe'
            calls = []
            def fake_run(command, **kwargs):
                calls.append(command)
                if '--console' in command:
                    worker.parent.mkdir(exist_ok=True)
                    worker.write_bytes(b'worker')
                else:
                    self.assertEqual(worker.read_bytes(), b'signed worker')
                    self.assertIn(str(worker) + ';bin', command)
            with patch.object(build_windows.subprocess, 'run', side_effect=fake_run):
                with self.assertRaises(FileNotFoundError):
                    build_windows.build('app', root)
                self.assertEqual(calls, [])
                build_windows.build('worker', root)
                self.assertEqual(len(calls), 1)
                worker.write_bytes(b'signed worker')
                build_windows.build('app', root)
                self.assertEqual(worker.read_bytes(), b'signed worker')
                self.assertEqual(len(calls), 2)
                calls.clear()
                # Simulate a newly signed worker after the worker build for all-stage ordering.
                def all_run(command, **kwargs):
                    calls.append(command)
                    if '--console' in command:
                        worker.write_bytes(b'signed worker')
                    else:
                        self.assertEqual(worker.read_bytes(), b'signed worker')
                with patch.object(build_windows.subprocess, 'run', side_effect=all_run):
                    build_windows.build('all', root)
                self.assertEqual(len(calls), 2)
                self.assertIn('--console', calls[0])
                self.assertIn('--windowed', calls[1])
                for command in calls:
                    self.assertIn('--version-file', command)

    def test_default_stage(self):
        with patch.object(build_windows, 'build') as build, patch.object(build_windows.sys, 'argv', ['build_windows.py']), patch.object(build_windows.sys, 'version_info', (3, 14, 10)):
            build_windows.main()
        build.assert_called_once_with('all')


if __name__ == '__main__':
    unittest.main()
