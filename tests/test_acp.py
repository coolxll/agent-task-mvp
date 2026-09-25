"""Regression checks for ACP streamed output and driver handoff."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from acp_bridge import complete_trailing_json
from agent_drivers import AcpDriver


class AcpTests(unittest.TestCase):
    def test_only_missing_json_closers_are_repaired(self):
        self.assertEqual(json.loads(complete_trailing_json('{"ok":true,"rows":[1]}')),
                         {"ok": True, "rows": [1]})
        self.assertEqual(complete_trailing_json('{"ok":tru'), '{"ok":tru')

    def test_driver_passes_session_and_schema_to_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with (path / 'log').open('w') as log, patch('subprocess.Popen') as popen:
                popen.return_value = MagicMock(pid=123)
                AcpDriver.start('prompt', path, path / 'result.json', log, 'full',
                                session_id='session-1', readonly=True, schema=dict)
                command = popen.call_args.args[0]
                self.assertIn('--session-id', command)
                self.assertIn('session-1', command)
                self.assertIn('--readonly', command)
                self.assertIn('--structured', command)
                self.assertEqual((path / 'result.prompt.txt').read_text(), 'prompt')


if __name__ == '__main__':
    unittest.main()
