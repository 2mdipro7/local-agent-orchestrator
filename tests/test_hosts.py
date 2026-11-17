import json
from pathlib import Path
import tempfile
import unittest

from agenthub.hosts import desktop_configs, register_host, connection_status


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


if __name__ == '__main__':
    unittest.main()
