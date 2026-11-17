import json
from pathlib import Path
import tempfile
import unittest

from agenthub.hosts import desktop_configs, host_targets, register_host, connection_status


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        exe = self.root / 'MCP.exe'
        exe.write_bytes(b'test')
        self.entry = {'command': str(exe), 'args': []}
        self.path = self.root / 'config.json'

    def test_merge_backup_idempotence(self):
        before = {'preferences': {'theme': 'dark'}, 'mcpServers': {'other': {'env': {'KEY': 'synthetic'}}}}
        raw = json.dumps(before).encode()
        self.path.write_bytes(raw)
        result = register_host(self.path, self.entry)
        self.assertEqual(Path(result['backup']).read_bytes(), raw)
        after = json.loads(self.path.read_bytes())
        self.assertEqual(after['preferences'], before['preferences'])
        self.assertEqual(after['mcpServers']['other'], before['mcpServers']['other'])
        self.assertFalse(register_host(self.path, self.entry)['changed'])
        self.assertIn('Configured', connection_status(self.path, self.entry))

    def test_conflict_and_invalid_preserved(self):
        for value in ('{broken', '{"a":1,"a":2}', '[]', '{"mcpServers":null}',
                      '{"mcpServers":{"local-agent-orchestrator":{"command":"other"}}}'):
            self.path.write_text(value)
            with self.assertRaises(ValueError):
                register_host(self.path, self.entry)
            self.assertEqual(self.path.read_text(), value)

    def test_missing_executable(self):
        self.path.write_text('{}')
        with self.assertRaises(ValueError):
            register_host(self.path, {'command': str(self.root / 'missing.exe')})
        self.assertEqual(self.path.read_text(), '{}')

    def test_antigravity_empty_initial_config(self):
        path = self.root / '.gemini/config/mcp_config.json'
        path.parent.mkdir(parents=True)
        path.touch()
        targets = host_targets(self.root, {})
        self.assertIn('antigravity', [t['id'] for t in targets])
        result = register_host(path, self.entry)
        self.assertEqual(Path(result['backup']).read_bytes(), b'')
        self.assertEqual(json.loads(path.read_text())['mcpServers']['local-agent-orchestrator'], self.entry)
        self.path.touch()
        with self.assertRaises(ValueError):
            register_host(self.path, self.entry)

    def test_migrated_profile_detected_without_stale_directory(self):
        local = self.root / 'Local'
        roaming = self.root / 'Roaming'
        stale = local / 'Packages/Claude_example/LocalCache/Roaming/Claude'
        stale.mkdir(parents=True)
        (stale / '.user-data-left').touch()
        active = local / 'Claude-Data/claude_example/claude_desktop_config.json'
        active.parent.mkdir(parents=True)
        active.write_text('{}')
        self.assertEqual(desktop_configs(self.root, {'LOCALAPPDATA':str(local),'APPDATA':str(roaming)}), [active])

    def test_registered_store_profile_before_first_launch(self):
        local = self.root / 'Local'
        env = {'LOCALAPPDATA': str(local), 'APPDATA': str(self.root / 'Roaming')}
        expected = local / 'Packages/Claude_current/LocalCache/Roaming/Claude/claude_desktop_config.json'
        targets = host_targets(self.root, env, claude_package_families=['Claude_current', '../bad'])
        self.assertEqual(Path(targets[0]['path']), expected)
        register_host(expected, self.entry)
        self.assertTrue(expected.is_file())

    def test_registered_store_does_not_override_migrated_profile(self):
        local = self.root / 'Local'
        migrated = local / 'Claude-Data/current'
        migrated.mkdir(parents=True)
        (migrated / 'Preferences').write_text('{}')
        self.assertEqual(desktop_configs(self.root, {'LOCALAPPDATA': str(local)}, ['Claude_current']),
                         [migrated / 'claude_desktop_config.json'])

    def test_store_query_bounded_and_validated(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from agenthub.hosts import _registered_claude_families
        with patch('agenthub.hosts.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='["Claude_current", "../bad", 3]')) as run:
            if __import__('os').name == 'nt':
                self.assertEqual(_registered_claude_families(), ['Claude_current'])
                self.assertEqual(run.call_args.kwargs['timeout'], 5)

    def test_fresh_profile_and_codex_home(self):
        from agenthub.install import register_default_hosts
        app = self.root / 'app'
        app.mkdir()
        (app / 'LocalAgentOrchestratorMCP.exe').write_bytes(b'test')
        home = self.root / 'home'
        env = {'CODEX_HOME': str(self.root / 'custom-codex')}
        targets = host_targets(home, env)
        self.assertEqual(len(targets), 4)
        notes = register_default_hosts(app, home=home, environ=env)
        self.assertEqual(len(notes), 4)
        self.assertTrue(all(': configured' in n for n in notes), notes)
        for target in targets:
            self.assertIn('Configured', connection_status(target['path'], {'command': str(app / 'LocalAgentOrchestratorMCP.exe'), 'args': []}, target['format']))
        self.assertTrue((self.root / 'custom-codex/config.toml').is_file())
        self.assertTrue(all('already configured' in n for n in register_default_hosts(app, home=home, environ=env)))

    def test_toml_preservation_and_conflicts(self):
        path = self.root / 'config.toml'
        raw = b'# keep this\r\nmodel = "abc"\r\n[mcp_servers.other]\r\ncommand = "example"\r\n'
        path.write_bytes(raw)
        result = register_host(path, self.entry, 'toml')
        self.assertEqual(Path(result['backup']).read_bytes(), raw)
        self.assertTrue(path.read_bytes().startswith(raw))
        self.assertFalse(register_host(path, self.entry, 'toml')['changed'])
        import tomllib
        self.assertEqual(tomllib.loads(path.read_text())['mcp_servers']['local-agent-orchestrator']['startup_timeout_sec'], 60)
        for text in ('bad = [', 'x = 1\nx = 2', '[mcp_servers.local-agent-orchestrator]\ncommand = "other"', 'mcp_servers = 1'):
            path.write_text(text)
            with self.assertRaises(ValueError):
                register_host(path, self.entry, 'toml')
            self.assertEqual(path.read_text(), text)

    def test_existing_launch_options_and_disabled_state_preserved(self):
        existing = {**self.entry, 'startup_timeout_sec': 90, 'env': {'EXAMPLE': 'fixture'}}
        self.path.write_text(json.dumps({'mcpServers': {'local-agent-orchestrator': existing}}))
        original = self.path.read_bytes()
        self.assertFalse(register_host(self.path, self.entry)['changed'])
        self.assertEqual(self.path.read_bytes(), original)
        for flag in ({'enabled': False}, {'disabled': True}):
            disabled = {**existing, **flag}
            self.path.write_text(json.dumps({'mcpServers': {'local-agent-orchestrator': disabled}}))
            original = self.path.read_bytes()
            self.assertIn('Disabled', connection_status(self.path, self.entry))
            with self.assertRaisesRegex(ValueError, 'disabled'):
                register_host(self.path, self.entry)
            self.assertEqual(self.path.read_bytes(), original)

    def test_active_profile_without_config(self):
        local = self.root / 'Local'
        active = local / 'Claude-Data/profile'
        active.mkdir(parents=True)
        (active / 'Preferences').write_text('{}')
        stale = local / 'Packages/Claude_old/LocalCache/Roaming/Claude'
        stale.mkdir(parents=True)
        self.assertEqual(desktop_configs(self.root, {'LOCALAPPDATA': str(local)}), [active / 'claude_desktop_config.json'])

    def test_setup_reports_one_conflict_and_continues_other_hosts(self):
        from agenthub.install import register_default_hosts
        app = self.root / 'app'
        app.mkdir()
        (app / 'LocalAgentOrchestratorMCP.exe').write_bytes(b'test')
        home = self.root / 'home'
        config = home / '.claude.json'
        home.mkdir()
        before = b'{"mcpServers":{"local-agent-orchestrator":{"command":"owned-existing"}}}'
        config.write_bytes(before)
        notes = register_default_hosts(app, home=home, environ={})
        self.assertEqual(sum(': configured' in n for n in notes), 3)
        self.assertEqual(sum(': unchanged' in n for n in notes), 1)
        self.assertEqual(config.read_bytes(), before)
        self.assertTrue((home / '.codex/config.toml').is_file())

    def test_read_helper_remains_compatible_with_live_harness(self):
        from agenthub.hosts import _read
        self.path.write_text('{}')
        self.assertEqual(_read(self.path), (b'{}', {}))

    def test_new_file_race_does_not_overwrite(self):
        from unittest.mock import patch
        import os
        path = self.root / 'new/config.json'
        real_link = os.link
        def competing_link(source, destination):
            Path(destination).write_text('{"other": true}')
            return real_link(source, destination)
        with patch('agenthub.hosts.os.link', side_effect=competing_link):
            with self.assertRaises(ValueError):
                register_host(path, self.entry)
        self.assertEqual(json.loads(path.read_text()), {'other': True})

    def test_linked_path_refused(self):
        link = self.root / 'link'
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError:
            from unittest.mock import patch
            original = Path.is_symlink
            with patch.object(Path, 'is_symlink', lambda p: p == link or original(p)):
                with self.assertRaises(ValueError):
                    register_host(link / 'config.json', self.entry)
            return
        with self.assertRaises(ValueError):
            register_host(link / 'config.json', self.entry)


if __name__ == '__main__':
    unittest.main()
