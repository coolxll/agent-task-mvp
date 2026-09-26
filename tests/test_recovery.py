"""Runner worker watchdog recovery checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import app


class WorkerRecoveryTests(unittest.TestCase):
    def state(self, root, status="RUNNING", attempts=0, resumable=True):
        run_dir = root / "runs" / "1"
        run_dir.mkdir(parents=True)
        workspace = root / "worktrees" / "1"
        if resumable:
            workspace.mkdir(parents=True)
            (run_dir / "artifacts.json").write_text("{}")
        value = {"id": 1, "status": status, "worker_pid": 99999999, "pid": None,
                 "agent_kind": "codex", "workspace": str(workspace),
                 "base_sha": "a" * 40 if resumable else None,
                 "recovery_attempts": attempts, "updated_at": app.now()}
        app.atomic_json(run_dir / "state.json", value)
        return run_dir / "state.json"

    def test_resumable_worker_is_restarted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_file = self.state(root)
            with patch("app.spawn_worker") as spawn:
                self.assertEqual(app.recover_stale_runs(root), 1)
            state = json.loads(state_file.read_text())
            self.assertEqual(state["recovery_attempts"], 1)
            self.assertIsNone(state["worker_pid"])
            spawn.assert_called_once_with(root, "1")
            self.assertIn("Recovering worker", (state_file.parent / "run.log").read_text())

    def test_non_resumable_provisioning_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_file = self.state(root, status="PROVISIONING", resumable=False)
            with patch("app.spawn_worker") as spawn:
                self.assertEqual(app.recover_stale_runs(root), 0)
            state = json.loads(state_file.read_text())
            self.assertEqual(state["status"], "FAILED")
            self.assertIn("non-resumable provisioning", state["error"])
            spawn.assert_not_called()

    def test_recovery_attempts_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_file = self.state(root, attempts=app.MAX_WORKER_RECOVERIES)
            with patch("app.spawn_worker") as spawn:
                self.assertEqual(app.recover_stale_runs(root), 0)
            state = json.loads(state_file.read_text())
            self.assertEqual(state["status"], "FAILED")
            self.assertIn("limit exceeded", state["error"])
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
