"""Run one agent turn inside a persistent Herdr multiplexer pane.

The Herdr bridge manages a dedicated, isolated Herdr pane for the Agent turn,
surviving client disconnects while streaming events to the Runner log.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(description="Herdr multiplexer bridge for agent task runner")
    parser.add_argument("--workspace", required=True, help="Working directory for the agent")
    parser.add_argument("--prompt-file", required=True, help="Path to prompt file")
    parser.add_argument("--result-path", required=True, help="Path where final output will be written")
    parser.add_argument("--access", default="workspace", choices=["workspace", "full"], help="Permission level")
    parser.add_argument("--session-id", default=None, help="Existing session or pane handle if resuming")
    parser.add_argument("--agent-kind", default="codex", help="Underlying agent kind inside herdr")
    parser.add_argument("--readonly", action="store_true", help="Read-only mode")
    parser.add_argument("--structured", action="store_true", help="Expect structured JSON output")
    parser.add_argument("--timeout", type=int, default=1800, help="Turn timeout in seconds")
    return parser.parse_args()


def get_herdr_bin():
    return os.environ.get("HERDR_BIN") or shutil.which("herdr") or "herdr"


def run_cmd(cmd, input_text=None, timeout=60):
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def cli_result(process):
    if process.returncode:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip() or "Herdr command failed")
    return json.loads(process.stdout)["result"]


def extract_assistant_response(text: str, marker: str) -> str:
    """Read the marked answer and its terminal-wrapped continuation lines."""
    lines = text.splitlines()
    answers = []
    start = re.compile(r"^[ \t]*[•*][ \t]+" + re.escape(marker) + r"[ \t]+(.*)$")
    for index, line in enumerate(lines):
        match = start.match(line)
        if not match:
            continue
        parts = [match.group(1).strip()]
        for continuation in lines[index + 1:]:
            if not continuation.strip() or not continuation.startswith("  "):
                break
            parts.append(continuation.strip())
        answers.append(" ".join(parts))
    if not answers:
        raise ValueError("Herdr agent did not return a marked final response")
    return answers[-1]


def managed_repo_root(workspace):
    """Return the source clone only for a Manager-owned worktree."""
    if workspace.parent.name != "worktrees" or workspace.parent.parent.name != "data":
        return None
    git_dir = run_cmd(["git", "-C", str(workspace), "rev-parse", "--path-format=absolute",
                       "--git-common-dir"], timeout=10)
    if git_dir.returncode:
        return None
    root = Path(git_dir.stdout.strip()).resolve().parent
    repos = workspace.parent.parent / "repos"
    return root if root.parent == repos and root.is_dir() else None


def clear_safe_startup_dialogs(herdr, agent_name, pane_id, workspace, access):
    """Dismiss known informational prompts; report when an update requires restart."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        screen = run_cmd([herdr, "agent", "read", agent_name,
                          "--source", "visible", "--lines", "50"], timeout=15)
        if screen.returncode and "agent_not_found" in screen.stderr:
            pane = run_cmd([herdr, "pane", "read", pane_id,
                            "--source", "visible", "--lines", "50"], timeout=15)
            if pane.returncode == 0 and "Update ran successfully! Please restart Codex." in pane.stdout:
                return True
            raise RuntimeError("Herdr agent exited during startup: " + pane.stdout.strip())
        if screen.returncode:
            raise RuntimeError("Herdr agent read failed during startup: " + screen.stderr.strip())
        text = screen.stdout
        if "Hooks need review" in text and "Continue without trusting" in text:
            cli_result(run_cmd([herdr, "agent", "send-keys", agent_name,
                                "down", "down", "enter"], timeout=15))
        elif "Update available!" in text and "Press enter to continue" in text:
            cli_result(run_cmd([herdr, "agent", "send-keys", agent_name,
                                "down", "enter"], timeout=15))
        elif "Do you trust the contents of this directory?" in text:
            root = managed_repo_root(workspace) if access == "full" else None
            if not root or str(root) not in text or "1. Yes, continue" not in text:
                raise RuntimeError("Codex requested trust for an unverified repository")
            cli_result(run_cmd([herdr, "agent", "send-keys", agent_name, "enter"], timeout=15))
        elif "Ask Codex to do anything" in text:
            return False
        elif "Updating Codex via `npm install -g @openai/codex`" in text:
            # Codex may update itself after Herdr has already recognized it.
            time.sleep(1)
        elif not text.strip():
            time.sleep(.5)
        else:
            raise RuntimeError("Herdr agent is waiting at an unknown startup prompt")
    raise RuntimeError("Herdr agent did not reach its ready prompt within 120 seconds")


def main():
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    prompt_path = Path(args.prompt_file).resolve()
    result_path = Path(args.result_path).resolve()
    prompt = prompt_path.read_text(encoding="utf-8")

    herdr = get_herdr_bin()
    workspace_id = None
    pane_id = None
    paused = False
    agent_name = f"run_{int(time.time())}_{os.getpid()}"

    def cleanup_handler(signum=None, frame=None):
        if workspace_id and not paused:
            try:
                run_cmd([herdr, "workspace", "close", workspace_id], timeout=10)
            except Exception:
                pass
        if signum is not None:
            sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, cleanup_handler)
    signal.signal(signal.SIGINT, cleanup_handler)

    try:
        # 1. Probe herdr availability
        probe = run_cmd([herdr, "pane", "list"], timeout=10)
        if probe.returncode != 0:
            error_msg = f"[herdr.error] Herdr CLI probe failed: {probe.stderr.strip() or probe.stdout.strip()}"
            print(error_msg, flush=True)
            result_path.write_text(error_msg)
            return 1

        # Every Run stage gets its own workspace. Never split the user's focused pane.
        if args.session_id:
            pane_id = args.session_id
            existing = cli_result(run_cmd([herdr, "agent", "get", pane_id], timeout=15))["agent"]
            if Path(existing["cwd"]).resolve() != workspace:
                raise ValueError("Herdr session belongs to another worktree")
            workspace_id = existing["workspace_id"]
            agent_name = existing["name"]
        else:
            created = cli_result(run_cmd([herdr, "workspace", "create", "--cwd", str(workspace),
                                          "--label", agent_name, "--no-focus"], timeout=20))
            workspace_id = created["workspace"]["workspace_id"]
            pane_id = created["root_pane"]["pane_id"]

        print(f"[herdr.session] {pane_id}", flush=True)
        print(f"[herdr.info] Allocated Herdr workspace {workspace_id}, pane {pane_id}", flush=True)

        # 3. Start coding agent inside the allocated pane
        agent_kind = args.agent_kind or os.environ.get("HERDR_AGENT_KIND", "codex")
        start_cmd = [herdr, "agent", "start", agent_name, "--kind", agent_kind, "--pane", pane_id]

        # Pass native bypass flags if full access requested
        extra_args = []
        if args.access == "full":
            if agent_kind == "claude":
                extra_args = ["--", "--permission-mode", "bypassPermissions"]
            elif agent_kind == "codex":
                extra_args = ["--", "--dangerously-bypass-approvals-and-sandbox"]
            elif agent_kind == "agy":
                extra_args = ["--", "--dangerously-skip-permissions"]

        if not args.session_id:
            start_cmd.extend(extra_args)
            for restart in range(2):
                start_res = run_cmd(start_cmd, timeout=35)
                if start_res.returncode:
                    error = start_res.stderr.strip() or start_res.stdout.strip()
                    if "agent_not_ready" not in error or agent_kind != "codex":
                        raise RuntimeError("Herdr agent startup failed: " + error)
                if agent_kind != "codex" or not clear_safe_startup_dialogs(herdr, agent_name, pane_id, workspace, args.access):
                    break
                if restart:
                    raise RuntimeError("Codex requested another restart after updating")

        print(f"[herdr.agent] Started {agent_kind} agent '{agent_name}' in pane {pane_id}", flush=True)

        # 4. Prompt agent and wait for completion
        timeout_ms = str(max(10, args.timeout) * 1000)
        marker = "TASK_RESULT_" + secrets.token_hex(8)
        prompt += ("\nFinal response contract: reply in exactly ONE line beginning with " + marker +
                   " followed by your final answer. If a JSON schema was requested, put the complete compact "
                   "JSON object on that same line. If you need input, put NEEDS_INPUT: <question> after the marker. "
                   "Do not include Markdown fences or any other final text.")
        for attempt in range(4):
            prompt_res = run_cmd([herdr, "agent", "prompt", agent_name, prompt,
                                  "--wait", "--timeout", timeout_ms], timeout=args.timeout + 15)
            if not prompt_res.returncode:
                break
            if "agent_blocked" not in (prompt_res.stderr + prompt_res.stdout) or agent_kind != "codex" or attempt == 3:
                break
            # Herdr may report readiness between successive Codex startup dialogs.
            time.sleep(.5)
            clear_safe_startup_dialogs(herdr, agent_name, pane_id, workspace, args.access)

        if prompt_res.returncode:
            raise RuntimeError("Herdr agent prompt failed: " +
                               (prompt_res.stderr.strip() or prompt_res.stdout.strip()))

        # 5. Read output from agent
        read_res = run_cmd([
            herdr, "agent", "read", agent_name,
            "--source", "recent-unwrapped", "--lines", "300"
        ], timeout=15)
        if read_res.returncode:
            raise RuntimeError("Herdr agent read failed: " +
                               (read_res.stderr.strip() or read_res.stdout.strip()))
        final_text = extract_assistant_response(read_res.stdout, marker)
        paused = final_text.startswith("NEEDS_INPUT:")
        result_path.write_text(final_text, encoding="utf-8")
        print(f"[herdr.done] Agent turn finished in pane {pane_id} ({len(final_text)} chars)", flush=True)
        return 0

    finally:
        cleanup_handler()


if __name__ == "__main__":
    sys.exit(main())
