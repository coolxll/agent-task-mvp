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
        self.assertIn("pi", kinds)

    def test_get_driver(self):
        self.assertIs(agent_drivers.get_driver("antigravity"), agent_drivers.AntigravityDriver)
        self.assertIs(agent_drivers.get_driver("claude"), agent_drivers.ClaudeDriver)
        self.assertIs(agent_drivers.get_driver("codex"), agent_drivers.CodexDriver)
        self.assertIs(agent_drivers.get_driver("pi"), agent_drivers.PiDriver)
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

    def test_pi_driver_cmd_construction(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result_path = workspace / "out.txt"
            log_path = workspace / "test.log"

            with patch("subprocess.Popen") as mock_popen, log_path.open("w") as log:
                mock_proc = MagicMock()
                mock_proc.pid = 23456
                mock_proc.stdout = None
                mock_proc.stdin = None
                mock_popen.return_value = mock_proc

                handle = agent_drivers.PiDriver.start(
                    prompt="implement fix",
                    workspace=workspace,
                    result_path=result_path,
                    log=log,
                    access="full",
                    session_id="pi-sess-567",
                    readonly=True,
                )

                self.assertEqual(handle.pid, 23456)
                call_args = mock_popen.call_args[0][0]
                self.assertIn("--mode", call_args)
                self.assertIn("rpc", call_args)
                self.assertIn("--session-dir", call_args)
                self.assertIn("--session", call_args)
                self.assertIn("pi-sess-567", call_args)
                self.assertIn("--tools", call_args)
                self.assertIn("read,grep,find,ls", call_args)

    def test_pi_rpc_protocol_handle(self):
        import io
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result_path = workspace / "out.txt"
            log_path = workspace / "test.log"

            mock_proc = MagicMock()
            mock_proc.pid = 34567
            mock_proc.poll.return_value = 0
            mock_proc.wait.return_value = 0
            mock_proc.returncode = 0

            mock_proc.stdin = io.StringIO()

            stream = [
                json.dumps({"id": "prompt-1", "type": "response", "command": "prompt", "success": True}) + "\n",
                json.dumps({"type": "tool_call", "toolName": "bash", "args": {"cmd": "pytest"}}) + "\n",
                json.dumps({"type": "agent_settled"}) + "\n",
                json.dumps({"id": "req-text", "type": "response", "data": {"text": "All tests pass"}}) + "\n",
                json.dumps({"id": "req-state", "type": "response", "data": {"sessionId": "pi-sess-abc-999"}}) + "\n",
                "",
            ]
            mock_proc.stdout = MagicMock()
            mock_proc.stdout.readline.side_effect = stream

            with log_path.open("w") as log:
                handle = agent_drivers.PiRpcProcessHandle(
                    mock_proc,
                    prompt="test prompt",
                    result_path=result_path,
                    log_file=log,
                )
                exit_code = handle.wait(timeout=5)
                self.assertEqual(exit_code, 0)

            self.assertEqual(result_path.read_text(), "All tests pass")
            self.assertEqual(agent_drivers.PiDriver.result(result_path), "All tests pass")

            session_id = agent_drivers.PiDriver.session_id(log_path, 0, result_path=result_path)
            self.assertEqual(session_id, "pi-sess-abc-999")

            log_content = log_path.read_text()
            self.assertIn("[tool_call] bash", log_content)
            self.assertIn("pi-sess-abc-999", log_content)


if __name__ == "__main__":
    unittest.main()

