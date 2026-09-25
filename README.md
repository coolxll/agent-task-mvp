# Agent Task MVP

A local Manager and remote Runner for an Agent-driven coding workflow. In the web UI, choose a local Git folder and an execution node, then describe the requirement in one text box. The Manager snapshots the committed HEAD into a versioned task package and sends a Git bundle to the Runner. Separate Codex sessions plan, implement dependency-ordered steps, review the code, and check acceptance; ordinary code runs the verification gates. The Manager imports the reviewed result back to the Mac. For GitHub projects, it creates a PR and merges the exact reviewed commit after web approval.

[Chinese user guide](README.zh-CN.md) · [Implementation plan](docs/implementation-plan.zh-CN.md) · [Acceptance record](docs/acceptance.zh-CN.md)

## Quick start

On `corp172-dev`, copy `app.py`, `agent_drivers.py`, `control.py`, `pipeline.py`, `git_io.py`, `requirements.txt`, `ui.html`, `ui.zh-CN.html`, and `ui.js` to `/workspace/agent-task-mvp`. Create a private token file, install dependencies, and run:

```sh
python3 -m venv /workspace/agent-task-mvp/.venv
/workspace/agent-task-mvp/.venv/bin/python -m pip install -r /workspace/agent-task-mvp/requirements.txt
/workspace/agent-task-mvp/.venv/bin/python /workspace/agent-task-mvp/app.py runner \
  --root /workspace/agent-task-mvp/data \
  --token-file /workspace/agent-task-mvp/token \
  --host 127.0.0.1 --port 8766 \
  --agent-access full
```

The access setting is specific to the current `corp172-dev` container, which cannot run Codex's normal `workspace-write` sandbox. Use trusted code there. `AgentDriver` is the workflow boundary; Codex is the only registered implementation in this version.

On the Mac, keep an SSH port forward running and start Manager:

```sh
ssh -N -L 18766:127.0.0.1:8766 corp172-dev
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py manager --db manager.sqlite3 --host 127.0.0.1 --port 18765
```

Open <http://127.0.0.1:18765> or <http://127.0.0.1:18765/zh>. Add the Node in Setup with endpoint `http://127.0.0.1:18766` and the remote token. Choose a clean local Git folder, the Node, and enter a requirement. Follow progress and answer Agent questions in Workflow. Code review runs automatically; Delivery acceptance is your final decision to keep the result branch or merge a GitHub PR. The [Chinese guide](README.zh-CN.md) contains the full setup and acceptance flow.

The Manager must remain bound to localhost. The directory browser and project administration are intended for the local user. Runtime data is stored in `manager.sqlite3` and `manager.sqlite3.data/`, which are ignored by Git.

GitHub delivery requires `gh` authenticated on the Mac with push and merge permissions. Projects without a GitHub remote retain their result branch in the Manager's local result repository. The selected local repository must be clean; the system never changes its checkout or discards local modifications. The current Planner runs all steps on the chosen Node, with a maximum of eight steps. Cross-node scheduling is planned separately.
