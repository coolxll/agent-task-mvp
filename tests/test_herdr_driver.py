"""Unit tests for Herdr and Paseo agent driver integration."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import agent_drivers
from agent_drivers import HerdrDriver, PaseoDriver


class HerdrAndPaseoDriverTests(unittest.TestCase):
    def test_drivers_registered(self):
        kinds = agent_drivers.available_kinds()
        self.assertIn("herdr", kinds)
        self.assertIn("paseo", kinds)
        self.assertIs(agent_drivers.get_driver("herdr"), HerdrDriver)
        self.assertIs(agent_drivers.get_driver("paseo"), PaseoDriver)

    def test_herdr_session_id_parsed_from_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run.log"
            log_path.write_text(
                "[herdr.info] Starting...\n"
                "[herdr.session] wJ:p2\n"
                "[herdr.agent] Started\n"
            )
            session = HerdrDriver.session_id(str(log_path), 0)
            self.assertEqual(session, "wJ:p2")

    def test_herdr_driver_starts_bridge_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            result_path = work_dir / "result.json"
            log_path = work_dir / "run.log"

            with log_path.open("w") as log, patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.pid = 9999
                mock_popen.return_value = mock_proc

                handle = HerdrDriver.start(
                    prompt="Hello Herdr",
                    workspace=work_dir,
                    result_path=result_path,
                    log=log,
                    access="full",
                    session_id="wJ:p2",
                    readonly=True,
                    schema=dict,
                )

                self.assertEqual(handle.pid, 9999)
                called_cmd = mock_popen.call_args[0][0]
                self.assertIn("herdr_bridge.py", called_cmd[2])
                self.assertIn("--workspace", called_cmd)
                self.assertIn(str(work_dir), called_cmd)
                self.assertIn("--access", called_cmd)
                self.assertIn("full", called_cmd)
                self.assertIn("--session-id", called_cmd)
                self.assertIn("wJ:p2", called_cmd)
                self.assertIn("--readonly", called_cmd)
                self.assertIn("--structured", called_cmd)

                # Prompt file check
                prompt_file = result_path.with_suffix(".prompt.txt")
                self.assertTrue(prompt_file.exists())
                self.assertEqual(prompt_file.read_text(encoding="utf-8"), "Hello Herdr")

    def test_paseo_driver_starts_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            result_path = work_dir / "result.json"
            log_path = work_dir / "run.log"

            with log_path.open("w") as log, patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.pid = 8888
                mock_popen.return_value = mock_proc

                handle = PaseoDriver.start(
                    prompt="Hello Paseo",
                    workspace=work_dir,
                    result_path=result_path,
                    log=log,
                    access="full",
                )

                self.assertEqual(handle.pid, 8888)
                called_cmd = mock_popen.call_args[0][0]
                self.assertIn("paseo", called_cmd[0])
                self.assertIn("run", called_cmd)
                self.assertIn("--cwd", called_cmd)
                self.assertIn(str(work_dir), called_cmd)
                self.assertIn("--mode", called_cmd)
                self.assertIn("bypass", called_cmd)
                self.assertIn("Hello Paseo", called_cmd)


if __name__ == "__main__":
    unittest.main()
