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
import threading
import time
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


class PiRpcProcessHandle:
    """Manages Pi RPC subprocess lifecycle, standard IO JSONL protocol, and results."""

    def __init__(self, proc: subprocess.Popen, prompt: str, result_path: Union[str, Path],
                 log_file=None, timeout: float = 1800.0):
        self._proc = proc
        self.pid = proc.pid
        self._prompt = prompt
        self._result_path = Path(result_path)
        self._log_file = log_file
        self._timeout = timeout
        self.extracted_session_id = None
        self._error = None
        self._worker_thread = threading.Thread(target=self._run_protocol, daemon=True)
        self._worker_thread.start()

    def _log(self, text: str):
        if self._log_file and not getattr(self._log_file, "closed", True):
            try:
                self._log_file.write(text)
                self._log_file.flush()
            except Exception:
                pass

    def _run_protocol(self):
        try:
            prompt_cmd = {"id": "prompt-1", "type": "prompt", "message": self._prompt}
            if self._proc.stdin:
                self._proc.stdin.write(json.dumps(prompt_cmd) + "\n")
                self._proc.stdin.flush()

            got_text = False
            got_state = False

            while True:
                line = self._proc.stdout.readline() if self._proc.stdout else ""
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    record = json.loads(line_str)
                except Exception:
                    self._log(f"[pi-raw] {line_str}\n")
                    continue

                rtype = record.get("type")
                if rtype == "response" and not record.get("success", False):
                    err = record.get("error", "Unknown Pi RPC error")
                    self._log(f"[pi-error] Command {record.get('command')}: {err}\n")
                    if record.get("id") == "prompt-1":
                        self._error = err
                        self._result_path.write_text(f"ERROR: {err}")
                        break

                if rtype == "tool_call":
                    tool_name = record.get("toolName") or record.get("tool", "tool")
                    args = record.get("args") or {}
                    self._log(f"[tool_call] {tool_name}: {json.dumps(args, ensure_ascii=False)}\n")
                elif rtype == "message_update":
                    update = record.get("assistantMessageEvent") or {}
                    if update.get("type") == "text_delta":
                        delta = update.get("delta", "")
                        self._log(delta)
                elif rtype == "agent_settled":
                    self._log("\n[agent_settled] Run settled, requesting final assistant message and session state...\n")
                    if self._proc.stdin and not getattr(self._proc.stdin, "closed", True):
                        self._proc.stdin.write(json.dumps({"id": "req-text", "type": "get_last_assistant_text"}) + "\n")
                        self._proc.stdin.write(json.dumps({"id": "req-state", "type": "get_state"}) + "\n")
                        self._proc.stdin.flush()

                if record.get("id") == "req-text":
                    data = record.get("data") or {}
                    last_text = data.get("text") or ""
                    self._result_path.write_text(last_text)
                    got_text = True

                if record.get("id") == "req-state":
                    data = record.get("data") or {}
                    self.extracted_session_id = data.get("sessionId")
                    if self.extracted_session_id:
                        meta_path = self._result_path.with_suffix(".session")
                        meta_path.write_text(json.dumps({"session_id": self.extracted_session_id}))
                        self._log(json.dumps({"type": "pi.session", "session_id": self.extracted_session_id}) + "\n")
                    got_state = True

                if got_text and got_state:
                    break

        except Exception as exc:
            self._error = str(exc)
            self._log(f"[pi-exception] {exc}\n")
        finally:
            try:
                if self._proc.stdin and not getattr(self._proc.stdin, "closed", True):
                    self._proc.stdin.close()
            except Exception:
                pass

    def wait(self, timeout=None):
        if timeout is not None:
            start_time = time.time()
            self._worker_thread.join(timeout=timeout)
            elapsed = time.time() - start_time
            remaining = max(0.1, timeout - elapsed)
            return self._proc.wait(timeout=remaining)
        self._worker_thread.join()
        return self._proc.wait()

    def poll(self):
        return self._proc.poll()

    @property
    def returncode(self):
        return self._proc.returncode


class PiDriver:
    """Pi (派 Agent) adapter using native JSONL RPC protocol (pi --mode rpc)."""

    @classmethod
    def get_binary_path(cls) -> str:
        pi_bin = os.environ.get("PI_PATH")
        if pi_bin and Path(pi_bin).exists():
            return str(pi_bin)
        which = shutil.which("pi")
        if which:
            return which
        nvm_dir = Path.home() / ".nvm" / "versions" / "node"
        if nvm_dir.exists():
            for node_ver in sorted(nvm_dir.glob("*/bin/pi"), reverse=True):
                if node_ver.exists():
                    return str(node_ver)
        return "pi"

    @classmethod
    def start(cls, prompt, workspace, result_path, log, access, session_id=None, readonly=False, schema=None):
        cmd = [cls.get_binary_path(), "--mode", "rpc"]
        session_dir = Path(workspace) / ".pi_sessions"
        session_dir.mkdir(exist_ok=True)
        cmd.extend(["--session-dir", str(session_dir)])

        if session_id:
            cmd.extend(["--session", str(session_id)])

        if readonly:
            cmd.extend(["--tools", "read,grep,find,ls"])

        proc = subprocess.Popen(
            cmd,
            cwd=workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        return PiRpcProcessHandle(proc, prompt=prompt, result_path=result_path, log_file=log)

    @staticmethod
    def session_id(log_path, offset, result_path=None):
        if result_path:
            meta_path = Path(result_path).with_suffix(".session")
            if meta_path.exists():
                try:
                    data = json.loads(meta_path.read_text())
                    if data.get("session_id"):
                        return data["session_id"]
                except Exception:
                    pass
        if log_path and Path(log_path).exists():
            with Path(log_path).open() as events:
                events.seek(offset)
                for line in events:
                    try:
                        event = json.loads(line)
                        if event.get("type") == "pi.session" and event.get("session_id"):
                            return event["session_id"]
                    except Exception:
                        continue
        return None

    @staticmethod
    def result(result_path):
        path = Path(result_path)
        return path.read_text(errors="replace") if path.exists() else ""

    @staticmethod
    def cancel(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass


class AcpDriver:
    """ACP lifecycle adapter; JSON-RPC is handled by the official SDK bridge."""

    @staticmethod
    def start(prompt, workspace, result_path, log, access, session_id=None, readonly=False, schema=None):
        import sys
        prompt_file = Path(result_path).with_suffix('.prompt.txt')
        prompt_file.write_text(prompt)
        command = [sys.executable, '-u', str(Path(__file__).with_name('acp_bridge.py')),
                   '--workspace', str(workspace), '--prompt-file', str(prompt_file),
                   '--result-path', str(result_path), '--access', access]
        if session_id:
            command.extend(['--session-id', session_id])
        if readonly:
            command.append('--readonly')
        if schema:
            command.append('--structured')
        proc = subprocess.Popen(command, cwd=workspace, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=log, start_new_session=True)
        return AgentProcessHandle(proc)

    @staticmethod
    def session_id(log_path, offset, result_path=None):
        with Path(log_path).open() as stream:
            stream.seek(offset)
            for line in stream:
                if line.startswith('[acp.session] '):
                    return line.split(' ', 1)[1].strip()
        return None

    @staticmethod
    def result(result_path):
        return Path(result_path).read_text()

    @staticmethod
    def cancel(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass


class HerdrDriver:
    """Herdr multiplexer adapter: executes turns inside persistent Herdr panes."""

    @staticmethod
    def start(prompt, workspace, result_path, log, access, session_id=None, readonly=False, schema=None):
        import sys
        prompt_file = Path(result_path).with_suffix('.prompt.txt')
        prompt_file.write_text(prompt, encoding='utf-8')
        command = [
            sys.executable, '-u', str(Path(__file__).with_name('herdr_bridge.py')),
            '--workspace', str(workspace),
            '--prompt-file', str(prompt_file),
            '--result-path', str(result_path),
            '--access', access,
        ]
        if session_id:
            command.extend(['--session-id', str(session_id)])
        if readonly:
            command.append('--readonly')
        if schema:
            command.append('--structured')
        agent_kind = os.environ.get("HERDR_AGENT_KIND", "claude")
        command.extend(['--agent-kind', agent_kind])

        proc = subprocess.Popen(
            command, cwd=workspace, stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, start_new_session=True
        )
        return AgentProcessHandle(proc)

    @staticmethod
    def session_id(log_path, offset, result_path=None):
        if log_path and Path(log_path).exists():
            with Path(log_path).open() as stream:
                stream.seek(offset)
                for line in stream:
                    if line.startswith('[herdr.session] '):
                        return line.split(' ', 1)[1].strip()
        return None

    @staticmethod
    def result(result_path):
        path = Path(result_path)
        return path.read_text(encoding='utf-8', errors='replace') if path.exists() else ""

    @staticmethod
    def cancel(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass


class PaseoDriver:
    """Paseo daemon adapter: dispatches agent turns via the Paseo CLI / daemon."""

    @classmethod
    def get_binary_path(cls) -> str:
        paseo_bin = os.environ.get("PASEO_BIN")
        if paseo_bin and Path(paseo_bin).exists():
            return str(paseo_bin)
        return shutil.which("paseo") or "paseo"

    @classmethod
    def start(cls, prompt, workspace, result_path, log, access, session_id=None, readonly=False, schema=None):
        cmd = [cls.get_binary_path(), "run", "--cwd", str(workspace)]
        if access == "full":
            cmd.extend(["--mode", "bypass"])
        if schema:
            schema_json = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema
            cmd.extend(["--output-schema", json.dumps(schema_json)])
        cmd.append(prompt)

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
        return path.read_text(encoding='utf-8', errors='replace') if path.exists() else ""

    @staticmethod
    def cancel(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass


DRIVERS = {
    "acp": AcpDriver,
    "antigravity": AntigravityDriver,
    "claude": ClaudeDriver,
    "codex": CodexDriver,
    "herdr": HerdrDriver,
    "paseo": PaseoDriver,
    "pi": PiDriver,
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
