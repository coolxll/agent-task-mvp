"""Run one agent turn inside a persistent Herdr multiplexer pane.

The Herdr bridge manages a dedicated, isolated Herdr pane for the Agent turn,
surviving client disconnects while streaming events to the Runner log.
"""
import argparse
import json
import os
from pathlib import Path
import re
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
    parser.add_argument("--agent-kind", default="claude", help="Underlying agent kind inside herdr (claude, codex, etc.)")
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


def extract_assistant_response(text: str) -> str:
    """Extract substantive assistant text from terminal screen capture."""
    clean = text.strip()
    return clean


def main():
    args = parse_args()
    workspace = Path(args.workspace).resolve()
    prompt_path = Path(args.prompt_file).resolve()
    result_path = Path(args.result_path).resolve()
    prompt = prompt_path.read_text(encoding="utf-8")

    herdr = get_herdr_bin()
    pane_id = None
    agent_name = f"run_{int(time.time())}_{os.getpid()}"

    def cleanup_handler(signum=None, frame=None):
        if pane_id:
            try:
                run_cmd([herdr, "pane", "close", pane_id], timeout=5)
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

        # 2. Split a new pane in the background
        split_res = run_cmd([
            herdr, "pane", "split",
            "--cwd", str(workspace),
            "--direction", "right",
            "--no-focus"
        ], timeout=15)
        if split_res.returncode != 0:
            err = split_res.stderr.strip() or split_res.stdout.strip()
            print(f"[herdr.error] Failed to split pane: {err}", flush=True)
            result_path.write_text(f"Failed to split Herdr pane: {err}")
            return 1

        try:
            split_data = json.loads(split_res.stdout)
            pane_id = split_data.get("result", {}).get("pane", {}).get("pane_id")
        except Exception as e:
            print(f"[herdr.error] Failed to parse pane split response: {e}", flush=True)
            result_path.write_text(f"Invalid Herdr JSON response: {split_res.stdout}")
            return 1

        if not pane_id:
            print(f"[herdr.error] No pane_id returned by Herdr split", flush=True)
            return 1

        print(f"[herdr.session] {pane_id}", flush=True)
        print(f"[herdr.info] Allocated Herdr pane {pane_id} in {workspace}", flush=True)

        # 3. Start coding agent inside the allocated pane
        agent_kind = args.agent_kind or os.environ.get("HERDR_AGENT_KIND", "claude")
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

        start_cmd.extend(extra_args)
        start_res = run_cmd(start_cmd, timeout=30)
        if start_res.returncode != 0:
            err = start_res.stderr.strip() or start_res.stdout.strip()
            print(f"[herdr.error] herdr agent start failed: {err}", flush=True)
            result_path.write_text(f"Agent startup failed in pane {pane_id}: {err}")
            return 1

        print(f"[herdr.agent] Started {agent_kind} agent '{agent_name}' in pane {pane_id}", flush=True)

        # 4. Prompt agent and wait for completion
        timeout_ms = str(max(10, args.timeout) * 1000)
        prompt_res = run_cmd([
            herdr, "agent", "prompt", agent_name, prompt,
            "--wait", "--timeout", timeout_ms
        ], timeout=args.timeout + 15)

        if prompt_res.returncode != 0:
            err = prompt_res.stderr.strip() or prompt_res.stdout.strip()
            print(f"[herdr.warning] herdr agent prompt exited with code {prompt_res.returncode}: {err}", flush=True)

        # 5. Read output from agent
        read_res = run_cmd([
            herdr, "agent", "read", agent_name,
            "--source", "recent-unwrapped", "--lines", "300"
        ], timeout=15)
        raw_output = read_res.stdout if read_res.returncode == 0 else (read_res.stderr or "")

        final_text = extract_assistant_response(raw_output)
        result_path.write_text(final_text, encoding="utf-8")
        print(f"[herdr.done] Agent turn finished in pane {pane_id} ({len(final_text)} chars)", flush=True)
        return 0

    finally:
        cleanup_handler()


if __name__ == "__main__":
    sys.exit(main())
