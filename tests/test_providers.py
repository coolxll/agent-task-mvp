"""Tests for multi-provider adapters."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import agent_drivers
from pipeline import Plan


class ProviderTests(unittest.TestCase):
    def test_registered_providers(self):
        kinds = agent_drivers.available_kinds()
        self.assertIn("antigravity", kinds)
        self.assertIn("claude", kinds)
        self.assertIn("codex", kinds)

    def test_get_driver(self):
        self.assertIs(agent_drivers.get_driver("antigravity"), agent_drivers.AntigravityDriver)
        self.assertIs(agent_drivers.get_driver("claude"), agent_drivers.ClaudeDriver)
        self.assertIs(agent_drivers.get_driver("codex"), agent_drivers.CodexDriver)
        with self.assertRaises(ValueError):
            agent_drivers.get_driver("nonexistent")

    def test_antigravity_driver_session_id_and_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "result.json"
            result_path.write_text(json.dumps({
                "conversation_id": "test-conv-1234",
                "status": "SUCCESS",
                "structured_output": {"summary": "plan summary", "steps": [], "acceptance_criteria": [], "gates": []}
            }))

            session_id = agent_drivers.AntigravityDriver.session_id("dummy.log", 0, result_path=result_path)
            self.assertEqual(session_id, "test-conv-1234")

            res = agent_drivers.AntigravityDriver.result(result_path)
            parsed = json.loads(res)
            self.assertEqual(parsed["summary"], "plan summary")

    def test_antigravity_driver_cmd_construction(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result_path = workspace / "out.json"
            log_path = workspace / "test.log"

            with patch("subprocess.Popen") as mock_popen, log_path.open("w") as log:
                mock_proc = MagicMock()
                mock_proc.pid = 12345
                mock_popen.return_value = mock_proc

                handle = agent_drivers.AntigravityDriver.start(
                    prompt="do something",
                    workspace=workspace,
                    result_path=result_path,
                    log=log,
                    access="full",
                    session_id="conv-456",
                    readonly=True,
                    schema=Plan,
                )

                self.assertEqual(handle.pid, 12345)
                call_args = mock_popen.call_args[0][0]
                self.assertIn("-p", call_args)
                self.assertIn("do something", call_args)
                self.assertIn("--add-dir", call_args)
                self.assertIn(str(workspace), call_args)
                self.assertIn("--output-format", call_args)
                self.assertIn("json", call_args)
                self.assertIn("--dangerously-skip-permissions", call_args)
                self.assertIn("--mode", call_args)
                self.assertIn("plan", call_args)
                self.assertIn("--conversation", call_args)
                self.assertIn("conv-456", call_args)
                self.assertIn("--json-schema", call_args)

    def test_claude_driver_without_key_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result_path = workspace / "out.json"
            with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value=None):
                with self.assertRaisesRegex(ValueError, "ANTHROPIC_API_KEY"):
                    agent_drivers.ClaudeDriver.start(
                        prompt="hello",
                        workspace=workspace,
                        result_path=result_path,
                        log=None,
                        access="workspace"
                    )


if __name__ == "__main__":
    unittest.main()
