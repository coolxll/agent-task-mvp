"""Multi-provider coding-agent adapters.

Supports Antigravity, Claude, Codex and extensible custom providers.
Workflow and Manager use provider kinds only.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
from typing import Optional, Protocol, Type, Union
from pydantic import BaseModel


class AgentProcessHandle:
    """Manages process lifecycle and file resources."""

    def __init__(self, popen_obj: subprocess.Popen, out_file=None):
        self._proc = popen_obj
        self._out_file = out_file
        self.pid = popen_obj.pid

    def wait(self, timeout=None):
        try:
            return self._proc.wait(timeout=timeout)
        finally:
            if self._out_file and not getattr(self._out_file, "closed", True):
                self._out_file.close()

    def poll(self):
        res = self._proc.poll()
        if res is not None and self._out_file and not getattr(self._out_file, "closed", True):
            self._out_file.close()
        return res

    @property
    def returncode(self):
        return self._proc.returncode


class AgentDriver(Protocol):
    """Protocol defining the interface required by pipeline.py."""

    @staticmethod
    def start(prompt, workspace, result_path, log, access, session_id=None, readonly=False, schema=None): ...

    @staticmethod
    def session_id(log_path, offset, result_path=None): ...

    @staticmethod
    def result(result_path): ...

    @staticmethod
    def cancel(pid): ...


# Alias for Provider abstraction
AgentProvider = AgentDriver


class AntigravityDriver:
    """Antigravity CLI execution with native schema enforcement and conversation resumption."""

    @staticmethod
    def get_binary_path() -> str:
        agy_bin = os.environ.get("AGY_PATH", "/Users/lynn/.local/bin/agy")
        if not Path(agy_bin).exists():
            agy_bin = shutil.which("agy") or "agy"
        return str(agy_bin)

    @classmethod
    def start(cls, prompt, workspace, result_path, log, access, session_id=None, readonly=False, schema=None):
        cmd = [
            cls.get_binary_path(),
            "-p", prompt,
            "--add-dir", str(workspace),
            "--output-format", "json",
        ]
        if access == "full":
            cmd.append("--dangerously-skip-permissions")
        if readonly:
            cmd.extend(["--mode", "plan"])
        else:
            cmd.extend(["--mode", "accept-edits"])
        if schema:
            schema_json = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema
            cmd.extend(["--json-schema", json.dumps(schema_json)])
        if session_id:
            cmd.extend(["--conversation", session_id])

        out_file = Path(result_path).open("w")
        proc = subprocess.Popen(
            cmd, cwd=workspace, stdout=out_file, stderr=log,
            text=True, start_new_session=True
        )
        return AgentProcessHandle(proc, out_file)

    @staticmethod
    def session_id(log_path, offset, result_path=None):
        if result_path and Path(result_path).exists():
            try:
                data = json.loads(Path(result_path).read_text())
                if data.get("conversation_id"):
                    return data["conversation_id"]
            except Exception:
                pass
        return None

    @staticmethod
    def result(result_path):
        path = Path(result_path)
        if not path.exists():
            return ""
        try:
            data = json.loads(path.read_text())
            if "structured_output" in data and data["structured_output"] is not None:
                so = data["structured_output"]
                return json.dumps(so) if not isinstance(so, str) else so
            return data.get("response", "")
        except Exception:
            return path.read_text(errors="replace")

    @staticmethod
    def cancel(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


class ClaudeDriver:
    """Anthropic Claude execution adapter."""

    @staticmethod
    def start(prompt, workspace, result_path, log, access, session_id=None, readonly=False, schema=None):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        claude_bin = shutil.which("claude")
        if not api_key and not claude_bin:
            raise ValueError(
                "Claude provider requires ANTHROPIC_API_KEY environment variable or 'claude' CLI installed."
            )
        cmd = [claude_bin or "claude", "-p", prompt]
        if session_id:
            cmd.extend(["--resume", session_id])
        out_file = Path(result_path).open("w")
        proc = subprocess.Popen(
            cmd, cwd=workspace, stdout=out_file, stderr=log,
            text=True, start_new_session=True
        )
        return AgentProcessHandle(proc, out_file)

    @staticmethod
    def session_id(log_path, offset, result_path=None):
        return None

    @staticmethod
    def result(result_path):
        path = Path(result_path)
        return path.read_text(errors="replace") if path.exists() else ""

    @staticmethod
    def cancel(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


class CodexDriver:
    """Codex CLI turns, including resume of a persisted session."""

    @staticmethod
    def start(prompt, workspace, result_path, log, access, session_id=None, readonly=False, schema=None):
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
    def session_id(log_path, offset, result_path=None):
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
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


DRIVERS = {
    "antigravity": AntigravityDriver,
    "claude": ClaudeDriver,
    "codex": CodexDriver,
}
PROVIDERS = DRIVERS
DEFAULT_KIND = os.environ.get("DEFAULT_AGENT_KIND", "antigravity")


def get_driver(kind):
    try:
        return DRIVERS[kind]
    except KeyError as exc:
        raise ValueError("unsupported agent kind: %s" % kind) from exc


get_provider = get_driver


def available_kinds():
    return sorted(DRIVERS)


def default_kind():
    return DEFAULT_KIND
