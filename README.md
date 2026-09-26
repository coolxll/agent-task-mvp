# Agent Task MVP

A local Manager and remote Runner for an Agent-driven coding workflow. In the web UI, choose a local Git folder and an execution node, then describe the requirement in one text box. The Manager snapshots the committed HEAD into a versioned task package and sends a Git bundle to the Runner. Agent sessions plan, implement dependency-ordered steps, review the code, and check acceptance; ordinary code runs the verification gates. The Manager imports the reviewed result back to the Mac. Web approval can fast-forward the selected clean local folder to the reviewed commit. GitHub PR delivery is optional.

[Chinese user guide](README.zh-CN.md) · [GitHub delivery security](docs/github-delivery-security.zh-CN.md) · [Kanban board acceptance](docs/kanban-board-acceptance.zh-CN.md) · [Herdr runner acceptance](docs/herdr-runner-acceptance.zh-CN.md) · [Implementation plan](docs/implementation-plan.zh-CN.md) · [Acceptance record](docs/acceptance.zh-CN.md)


## Quick start

On `corp172-dev`, copy `app.py`, `agent_drivers.py`, `acp_bridge.py`, `control.py`, `pipeline.py`, `git_io.py`, `requirements.txt`, `ui.html`, `ui.zh-CN.html`, and `ui.js` to `/workspace/agent-task-mvp`. Use Python 3.10–3.14. Create a private token file, install dependencies, and run:

```sh
uv venv --python 3.12 /workspace/agent-task-mvp/.venv
uv pip install --python /workspace/agent-task-mvp/.venv/bin/python -r /workspace/agent-task-mvp/requirements.txt
/workspace/agent-task-mvp/.venv/bin/python /workspace/agent-task-mvp/app.py runner \
  --root /workspace/agent-task-mvp/data \
  --token-file /workspace/agent-task-mvp/token \
  --host 127.0.0.1 --port 8766 \
  --agent-access full
```

The access setting is specific to the current `corp172-dev` container, which cannot run Codex's normal `workspace-write` sandbox. Use trusted code there. `AgentDriver` is the workflow boundary. The Runner reports which registered providers have a usable command on that machine, and the task form only offers those providers. Command readiness does not prove authentication, account entitlement, or service quota: an Antigravity CLI 1.2.10 probe launched successfully but the service rejected the current account as ineligible before consuming tokens. The Runner prefers `DEFAULT_AGENT_KIND`, then falls back to an available Codex or another provider. For ACP, install `@agentclientprotocol/codex-acp@1.13.1` and set `ACP_AGENT_COMMAND` to its executable in the Runner environment; the task can then select `acp`.

Paseo remains experimental because its structured-result and session lifecycle have not passed the full remote workflow. It is hidden unless an isolated test Runner sets `ENABLE_EXPERIMENTAL_PASEO=1`. Full-access turns use Paseo's `full-access` mode and read-only turns use `auto-review`.

If code review, a Gate, or Agent acceptance fails, the Runner sends the concrete findings and outputs to a repair turn and repeats independent review, all Gates, and acceptance. It performs at most two repair attempts and preserves every verification round in the Run artifacts.

The Runner watchdog also detects an unexpectedly exited worker. A Run with a prepared worktree and persisted pipeline artifacts resumes completed-stage-aware execution, with at most two automatic worker recoveries. A worker lost during ambiguous provisioning is marked failed instead of risking duplicate workspace creation.

On the Mac, keep an SSH port forward running and start Manager:

```sh
ssh -N -L 18766:127.0.0.1:8766 corp172-dev
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python app.py manager --db manager.sqlite3 --host 127.0.0.1 --port 18765
```

Open <http://127.0.0.1:18765> or <http://127.0.0.1:18765/zh>. Add the Node in Setup with endpoint `http://127.0.0.1:18766` and the remote token. Choose a clean local Git folder, the Node, and enter a requirement. Follow progress and answer Agent questions in Workflow. Code review runs automatically; Delivery acceptance is your final decision to merge into that local folder, keep a result branch, or merge a GitHub PR. The [Chinese guide](README.zh-CN.md) contains the full setup and acceptance flow.

The Manager must remain bound to localhost. The directory browser and project administration are intended for the local user. Runtime data is stored in `manager.sqlite3` and `manager.sqlite3.data/`, which are ignored by Git.

GitHub delivery requires `gh` authenticated on the Mac with push and merge permissions. Newly imported local folders default to local merge after approval; existing project settings remain unchanged until edited. The local branch must still match the submitted commit and have a clean worktree. Approval never overwrites later local work. Projects without an imported local folder can keep their result branch in the Manager's result repository. The current Planner runs all steps on the chosen Node, with a maximum of eight steps. Cross-node scheduling is planned separately.

The real GitHub main path was exercised by [PR #17](https://github.com/coolxll/agent-task-mvp/pull/17): the system created the PR, rechecked its reviewed head and `main` base, merged it through the Run review API, confirmed `MERGED`, and removed the Runner worktree. On the dedicated protected repo `coolxll/agent-task-mvp-protect` a branch-protection rejection was exercised live: the merge was refused with a structured `merge_protection` error while staying retryable, and after the protection was relaxed the approved merge deleted the system-created remote task branch automatically (a repo with `delete_branch_on_merge` also returns a benign "reference does not exist" that is treated as success).
