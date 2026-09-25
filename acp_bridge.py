"""Run one ACP turn using the official Python SDK.

This process is intentionally short lived. The Runner owns its process group, so
existing cancellation also terminates the ACP agent subprocess.
"""
import argparse
import asyncio
import json
import os
import shlex
import sys
from pathlib import Path

from acp import PROTOCOL_VERSION, Client, RequestError, connect_to_agent
from acp.schema import (
    AgentMessageChunk, ClientCapabilities, DeclineElicitationResponse,
    Implementation, RequestPermissionResponse, TextContentBlock,
)


def complete_trailing_json(value):
    """Repair only missing closing brackets at EOF from streamed ACP chunks."""
    try:
        json.loads(value)
        return value
    except json.JSONDecodeError as error:
        if error.pos != len(value):
            return value
    stack = []
    quoted = escaped = False
    for char in value:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or stack.pop() != char:
                return value
    if quoted or not stack:
        return value
    repaired = value + "".join(reversed(stack))
    try:
        json.loads(repaired)
    except json.JSONDecodeError:
        return value
    print("\n[acp.warning] Completed missing JSON closing bracket at EOF", flush=True)
    return repaired


class RunnerClient(Client):
    def __init__(self, access, readonly):
        self.access = access
        self.readonly = readonly
        self.messages = []

    async def session_update(self, session_id, update, **kwargs):
        kind = getattr(update, "session_update", type(update).__name__)
        if isinstance(update, AgentMessageChunk) and isinstance(update.content, TextContentBlock):
            self.messages.append(update.content.text)
            print(update.content.text, end="", flush=True)
        elif kind in ("tool_call", "tool_call_update", "plan", "plan_update"):
            if kind == "tool_call":
                self.messages.clear()
            event = {"type": kind, "title": getattr(update, "title", None),
                     "status": getattr(update, "status", None),
                     "tool_call_id": getattr(update, "tool_call_id", None)}
            print("\n[acp.event] " + json.dumps(event, ensure_ascii=False), flush=True)

    async def request_permission(self, session_id, tool_call, options, **kwargs):
        if self.readonly or self.access != "full":
            print("\n[acp.permission] denied", flush=True)
            return RequestPermissionResponse(outcome={"outcome": "cancelled"})
        option = next((item for item in options if item.kind == "allow_once"), None)
        if option is None:
            option = next((item for item in options if item.kind == "allow_always"), None)
        if option is None:
            raise RuntimeError("ACP agent requested permission without an allow option")
        print("\n[acp.permission] allowed: " + option.name, flush=True)
        return RequestPermissionResponse(outcome={"outcome": "selected", "optionId": option.option_id})

    async def create_elicitation(self, message, mode, **kwargs):
        # Interactive ACP forms need a durable request/response channel. Do not
        # pretend that declining the request is a user answer.
        print("\n[acp.elicitation] unsupported interactive request: " + message, flush=True)
        return DeclineElicitationResponse(action="decline")

    async def complete_elicitation(self, elicitation_id, **kwargs):
        print("\n[acp.elicitation] completed: " + elicitation_id, flush=True)

    async def ext_method(self, method, params):
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method, params):
        print("[acp.extension] " + method, flush=True)


async def run(args):
    command = shlex.split(os.environ.get("ACP_AGENT_COMMAND", "codex-acp"))
    if not command:
        raise ValueError("ACP_AGENT_COMMAND is empty")
    proc = await asyncio.create_subprocess_exec(*command, cwd=args.workspace,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    async def relay_stderr():
        while line := await proc.stderr.readline():
            print("[acp.stderr] " + line.decode(errors="replace").rstrip(), flush=True)

    relay = asyncio.create_task(relay_stderr())
    try:
        client = RunnerClient(args.access, args.readonly)
        conn = connect_to_agent(client, proc.stdin, proc.stdout)
        initialized = await conn.initialize(protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(),
            client_info=Implementation(name="agent-task-runner", version="0.1.0"))
        print("[acp.protocol] " + str(initialized.protocol_version), flush=True)
        if args.session_id:
            if not initialized.agent_capabilities.load_session:
                raise RuntimeError("ACP agent does not support session/load")
            await conn.load_session(cwd=args.workspace, session_id=args.session_id)
            session_id = args.session_id
            client.messages.clear()  # load may replay earlier turns
        else:
            session = await conn.new_session(cwd=args.workspace)
            session_id = session.session_id
        print("[acp.session] " + session_id, flush=True)
        response = await conn.prompt(session_id=session_id,
            prompt=[TextContentBlock(type="text", text=Path(args.prompt_file).read_text())])
        print("\n[acp.stop] " + response.stop_reason, flush=True)
        if response.stop_reason not in ("end_turn",):
            raise RuntimeError("ACP turn stopped: " + response.stop_reason)
        result = "".join(client.messages).strip()
        if not result:
            raise RuntimeError("ACP agent returned no message")
        if args.structured:
            result = complete_trailing_json(result)
        Path(args.result_path).write_text(result)
    finally:
        if proc.returncode is None:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        await relay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--result-path", required=True)
    parser.add_argument("--access", required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--readonly", action="store_true")
    parser.add_argument("--structured", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:
        print("[acp.error] " + repr(exc), file=sys.stderr, flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
