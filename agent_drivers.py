"""Coding-agent process adapters. Workflow and Manager use agent kinds only."""
import json
import os
from pathlib import Path
import signal
import subprocess
from typing import Protocol


class AgentDriver(Protocol):
    def start(self, prompt, workspace, result_path, log, access, session_id=None, readonly=False): ...
    def session_id(self, log_path, offset): ...
    def result(self, result_path): ...
    def cancel(self, pid): ...


class CodexDriver:
    """Codex CLI turns, including resume of a persisted session."""

    @staticmethod
    def start(prompt, workspace, result_path, log, access, session_id=None, readonly=False):
        sandbox = "read-only" if readonly else "workspace-write"
        command = ["codex", "exec"]
        if session_id:
            command += ["resume", "--json"]
            command += (["--dangerously-bypass-approvals-and-sandbox"] if access == "full"
                        else ["--config", 'sandbox_mode="%s"' % sandbox])
            command += ["--output-last-message", str(result_path), session_id, "-"]
        else:
            command += ["--json"]
            command += (["--dangerously-bypass-approvals-and-sandbox"] if access == "full"
                        else ["--sandbox", sandbox])
            command += ["--cd", str(workspace), "--output-last-message", str(result_path), "-"]
        proc = subprocess.Popen(command, cwd=workspace, stdin=subprocess.PIPE, stdout=log,
                                stderr=subprocess.STDOUT, text=True, start_new_session=True)
        proc.stdin.write(prompt)
        proc.stdin.close()
        return proc

    @staticmethod
    def session_id(log_path, offset):
        with Path(log_path).open() as events:
            events.seek(offset)
            for line in events:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "thread.started":
                    return event.get("thread_id")
        return None

    @staticmethod
    def result(result_path):
        path = Path(result_path)
        return path.read_text(errors="replace") if path.exists() else ""

    @staticmethod
    def cancel(pid):
        os.killpg(pid, signal.SIGTERM)


DRIVERS = {"codex": CodexDriver}
DEFAULT_KIND = "codex"


def get_driver(kind):
    try:
        return DRIVERS[kind]
    except KeyError as exc:
        raise ValueError("unsupported agent kind: %s" % kind) from exc


def available_kinds():
    return sorted(DRIVERS)


def default_kind():
    return DEFAULT_KIND
