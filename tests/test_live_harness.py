import json
from pathlib import Path
import tempfile
import unittest

from verify_live_routes import temporary_antigravity_connection


class HarnessTests(unittest.TestCase):
    def test_test_connection_cleanup_preserves_other_changes_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder)/'profile.json'
            original = b'{"mcpServers":{"existing":{"command":"preserve"}},"preference":1}'
            profile.write_bytes(original)
            entry = {'command': 'synthetic', 'args': []}
            with self.assertRaisesRegex(RuntimeError, 'synthetic test failure'):
                with temporary_antigravity_connection(entry, profile):
                    data = json.loads(profile.read_bytes())
                    self.assertEqual(data['mcpServers']['orchestrator-route-check'], entry)
                    data['preference'] = 2
                    profile.write_text(json.dumps(data))
                    raise RuntimeError('synthetic test failure')
            final = json.loads(profile.read_bytes())
            self.assertEqual(final, {'mcpServers': {'existing': {'command': 'preserve'}}, 'preference': 2})
            self.assertEqual(next(Path(folder).glob('*.route-backup-*')).read_bytes(), original)
            final['mcpServers']['orchestrator-route-check'] = {'command': 'other'}
            profile.write_text(json.dumps(final))
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                with temporary_antigravity_connection(entry, profile):
                    self.fail('Must not overwrite a conflicting entry')
