#!/usr/bin/env python3
"""Manager and remote Runner for agent-driven Git worktree tasks."""
import argparse
import agent_drivers
import git_io
import pipeline
from contextlib import closing
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def git(*args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=check,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def atomic_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def read_json(path):
    return json.loads(path.read_text())


def update_state(path, changes, require_active=False, allowed_from=None):
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = read_json(path)
        if require_active and data["status"] == "CANCELLED":
            raise InterruptedError("cancelled")
        if allowed_from is not None and data["status"] not in allowed_from:
            raise ValueError("run status changed to %s" % data["status"])
        data.update(changes)
        data["updated_at"] = now()
        atomic_json(path, data)
        return data


def slug(value):
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:40] or "task"


class Http(BaseHTTPRequestHandler):
    def reply(self, status, data, content_type="application/json"):
        body = data.encode() if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def payload(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size > 72_000_000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(size) or b"{}")

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def dispatch(self, method):
        try:
            if method == "POST" and self.headers.get("Origin") and urlparse(self.headers["Origin"]).netloc != self.headers.get("Host"):
                return self.reply(403, {"error": "cross-origin mutation is not allowed"})
            self.route(method, urlparse(self.path).path)
        except (ValueError, KeyError) as exc:
            self.reply(400, {"error": str(exc)})
        except Exception as exc:
            self.reply(500, {"error": str(exc)})

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (now(), fmt % args))


class Runner(Http):
    root: Path
    token: str
    agent_access: str

    def state_path(self, run_id):
        if not re.fullmatch(r"[0-9]+", str(run_id)):
            raise ValueError("invalid run id")
        return self.root / "runs" / str(run_id) / "state.json"

    def update(self, run_id, **changes):
        path = self.state_path(run_id)
        return update_state(path, changes)

    def route(self, method, path):
        if self.headers.get("Authorization") != "Bearer " + self.token:
            return self.reply(401, {"error": "unauthorized"})
        if path == "/health" and method == "GET":
            return self.reply(200, {"ok": True, "api_version": 2,
                                    "agent_kinds": agent_drivers.available_kinds()})
        if path == "/runs" and method == "POST":
            p = self.payload()
            run_id = str(int(p["id"]))
            source_kind = p.get("source_kind", "existing")
            if source_kind == "managed":
                workspace_id = str(int(p["workspace_id"]))
                if not p.get("repo_url") and not p.get("source_bundle"):
                    raise ValueError("managed workspace requires repo_url")
                source = self.root / "repos" / workspace_id
            elif source_kind == "existing":
                source = Path(p["source_path"]).resolve(strict=True)
                if not source.is_dir() or git("rev-parse", "--show-toplevel", cwd=source).stdout.strip() != str(source):
                    raise ValueError("source_path must be a Git repository root")
            else:
                raise ValueError("invalid source_kind")
            if any(x == "" for x in [p.get("title"), p.get("description")]):
                raise ValueError("title and description are required")
            agent_kind = p.get("agent_kind", agent_drivers.default_kind())
            agent_drivers.get_driver(agent_kind)
            run_dir = self.root / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=False)
            branch = "agent/task-%s-run-%s-%s" % (p["task_id"], run_id, slug(p["title"]))
            workspace = self.root / "worktrees" / run_id
            state = {"id": int(run_id), "status": "PENDING", "source_path": str(source),
                     "source_kind": source_kind, "repo_url": p.get("repo_url", ""),
                     "workspace_id": p.get("workspace_id"),
                     "workspace": str(workspace), "branch": branch, "base_ref": p.get("base_ref") or "HEAD",
                     "title": p["title"], "description": p["description"],
                     "acceptance_criteria": p.get("acceptance_criteria", ""),
                     "gates": p.get("gates", []), "agent_kind": agent_kind, "agent_access": self.agent_access,
                     "pid": None,
                     "error": None, "created_at": now(), "updated_at": now()}
            if not isinstance(state["gates"], list) or not all(isinstance(x, str) for x in state["gates"]):
                raise ValueError("gates must be a list of commands")
            state.update(stage="PENDING", package=p.get("package", {}), worker_pid=None)
            if p.get("source_bundle"):
                git_io.decode_bundle(p["source_bundle"], run_dir / "input.bundle")
            atomic_json(run_dir / "package.json", p.get("package", {}))
            atomic_json(run_dir / "state.json", state)
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "execute", "--root", str(self.root),
                              "--run-id", run_id], start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return self.reply(201, state)
        m = re.fullmatch(r"/runs/(\d+)(?:/(logs|artifacts|cancel|review|cleanup|package|bundle|answer))?", path)
        if not m:
            return self.reply(404, {"error": "not found"})
        run_id, suffix = m.groups()
        state = read_json(self.state_path(run_id))
        run_dir = self.root / "runs" / run_id
        if method == "GET" and not suffix:
            return self.reply(200, state)
        if method == "GET" and suffix == "package":
            return self.reply(200, state.get("package", {}))
        if method == "GET" and suffix == "bundle":
            if state["status"] not in ("REVIEW", "SUCCEEDED"):
                raise ValueError("result bundle is not ready")
            return self.reply(200, git_io.encode_bundle(run_dir / "result.bundle"))
        if method == "GET" and suffix == "logs":
            file = run_dir / "run.log"
            return self.reply(200, {"text": file.read_text(errors="replace")[-200_000:] if file.exists() else ""})
        if method == "GET" and suffix == "artifacts":
            file = run_dir / "artifacts.json"
            return self.reply(200, read_json(file) if file.exists() else {})
        if method == "POST" and suffix == "answer":
            answer = self.payload().get("answer", "").strip()
            if not answer or len(answer) > 20000:
                raise ValueError("answer must contain 1–20000 characters")
            state = update_state(self.state_path(run_id), {"status": "RUNNING", "answer": answer,
                "question": None, "error": None}, allowed_from=("NEEDS_INPUT",))
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "execute", "--root", str(self.root),
                              "--run-id", run_id], start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return self.reply(200, state)
        if method == "POST" and suffix == "cancel":
            if state["status"] not in ("PENDING", "PROVISIONING", "RUNNING", "VERIFYING", "NEEDS_INPUT"):
                raise ValueError("run is not active")
            state = update_state(self.state_path(run_id),
                {"status": "CANCELLED", "finished_at": now()},
                allowed_from=("PENDING", "PROVISIONING", "RUNNING", "VERIFYING", "NEEDS_INPUT"))
            if state.get("pid"):
                try:
                    agent_drivers.get_driver(state["agent_kind"]).cancel(state["pid"])
                except ProcessLookupError:
                    pass
            return self.reply(200, state)
        if method == "POST" and suffix == "cleanup":
            if state["status"] not in ("FAILED", "CANCELLED"):
                raise ValueError("only failed or cancelled runs can be cleaned here")
            if state.get("worker_pid"):
                try:
                    os.kill(state["worker_pid"], 0)
                except ProcessLookupError:
                    pass
                else:
                    raise ValueError("worker is stopping; retry cleanup shortly")
            self.cleanup(state, delete_branch=True)
            return self.reply(200, self.update(run_id, cleaned_at=now()))
        if method == "POST" and suffix == "review":
            decision = self.payload().get("decision")
            if state["status"] != "REVIEW" or decision not in ("approve", "reject"):
                raise ValueError("run is not ready for review")
            source = Path(state["source_path"])
            workspace = Path(state["workspace"])
            if decision == "approve":
                artifacts_file = run_dir / "artifacts.json"
                artifacts = read_json(artifacts_file) if artifacts_file.exists() else {}
                if artifacts.get("pipeline_version") and not artifacts.get("ready_to_merge"):
                    raise ValueError("Code review, tests and acceptance must pass before approval")
                if artifacts.get("commit_sha") and git("rev-parse", "HEAD", cwd=workspace).stdout.strip() != artifacts["commit_sha"]:
                    raise ValueError("Reviewed commit changed")
                if artifacts.get("pipeline_version") and git("status", "--porcelain", cwd=workspace).stdout.strip():
                    raise ValueError("Reviewed worktree changed")
                git("add", "-A", cwd=workspace)
                if git("diff", "--cached", "--quiet", cwd=workspace, check=False).returncode:
                    git("-c", "user.name=Agent Task MVP", "-c", "user.email=agent-task-mvp@local",
                        "commit", "-m", "Task %s: %s" % (run_id, state["title"]), cwd=workspace)
                commit = git("rev-parse", "HEAD", cwd=workspace).stdout.strip()
            else:
                commit = None
            self.cleanup(state, delete_branch=decision == "reject")
            return self.reply(200, self.update(run_id, status="SUCCEEDED" if decision == "approve" else "REJECTED",
                                               commit_sha=commit, finished_at=now(), cleaned_at=now()))
        self.reply(404, {"error": "not found"})

    def cleanup(self, state, delete_branch=False):
        source = Path(state["source_path"])
        workspace = Path(state["workspace"])
        if workspace.parent != self.root / "worktrees" or workspace.name != str(state["id"]):
            raise ValueError("workspace outside Runner root")
        if not state["branch"].startswith("agent/task-"):
            raise ValueError("branch is not owned by Runner")
        if workspace.is_symlink():
            raise ValueError("workspace must not be a symlink")
        if workspace.exists():
            git("worktree", "remove", "--force", str(workspace), cwd=source)
        if delete_branch and source.exists() and git("branch", "--list", state["branch"], cwd=source).stdout.strip():
            git("branch", "-D", state["branch"], cwd=source)


def execute(root, run_id):
    state_file = root / "runs" / str(run_id) / "state.json"
    log_file = state_file.parent / "run.log"
    state = read_json(state_file)

    def update(**changes):
        update_state(state_file, changes, require_active=True)

    with log_file.open("a", buffering=1) as log:
        def say(message):
            log.write("[%s] %s\n" % (now(), message))

        try:
            update(worker_pid=os.getpid())
            source = Path(state["source_path"])
            workspace = Path(state["workspace"])
            bundle = state_file.parent / "input.bundle"
            if state.get("base_sha"):
                if not workspace.is_dir() or not (state_file.parent / "artifacts.json").is_file():
                    raise ValueError("Cannot resume: saved workspace or pipeline state is missing")
                pipeline.run(state, state_file.parent, workspace,
                             agent_drivers.get_driver(state["agent_kind"]), git, update, say, log, atomic_json)
                return
            update(status="PROVISIONING", stage="PROVISIONING", started_at=now())
            if state.get("source_kind") == "managed":
                repos = root / "repos"
                repos.mkdir(exist_ok=True)
                if source.parent != repos or source.name != str(int(state["workspace_id"])):
                    raise ValueError("managed source outside Runner root")
                with (repos / (source.name + ".lock")).open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    if not source.exists():
                        temp = repos / (".clone-%s-%s" % (source.name, run_id))
                        if temp.exists():
                            raise ValueError("partial clone already exists: %s" % temp)
                        say("Cloning Project repository into managed workspace %s" % source)
                        try:
                            result = subprocess.run(["git", "clone", "--", str(bundle) if bundle.exists() else state["repo_url"], str(temp)],
                                                    text=True, capture_output=True, timeout=900,
                                                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
                            output = (result.stdout + result.stderr).replace(state["repo_url"] or "<no-remote>", "<repository>")
                            log.write(output)
                            if result.returncode:
                                raise RuntimeError("Git clone failed (exit %s): %s" %
                                                   (result.returncode, output[-2000:]))
                            temp.rename(source)
                        finally:
                            if temp.exists():
                                shutil.rmtree(temp)
                    if bundle.exists():
                        git("fetch", str(bundle), "HEAD", cwd=source)
                        ref = git("rev-parse", "FETCH_HEAD", cwd=source).stdout.strip()
                    else:
                        remote_url = git("remote", "get-url", "origin", cwd=source).stdout.strip()
                        if remote_url != state["repo_url"]:
                            raise ValueError("managed workspace origin does not match Project repo_url")
                        fetched = git("fetch", "origin", "--prune", cwd=source, check=False)
                        if fetched.returncode:
                            raise RuntimeError("Git fetch failed: %s" % fetched.stderr.replace(state["repo_url"] or "<no-remote>", "<repository>")[-2000:])
                        ref = state["base_ref"]
                        if ref == "HEAD":
                            remote_head = git("symbolic-ref", "refs/remotes/origin/HEAD", cwd=source, check=False)
                            ref = remote_head.stdout.strip() if remote_head.returncode == 0 else "HEAD"
                        elif git("rev-parse", "--verify", "refs/remotes/origin/" + ref, cwd=source, check=False).returncode == 0:
                            ref = "refs/remotes/origin/" + ref
            else:
                ref = state["base_ref"]
            base_sha = git("rev-parse", "--verify", ref, cwd=source).stdout.strip()
            expected_sha = state.get("package", {}).get("source", {}).get("commit")
            if expected_sha and base_sha != expected_sha:
                raise ValueError("Source commit does not match task package")
            update(stage="PROVISIONING")
            git("worktree", "add", "-b", state["branch"], str(workspace), base_sha, cwd=source)
            update(base_sha=base_sha, status="RUNNING")
            say("Worktree: %s (%s)" % (workspace, state["branch"]))
            state["base_sha"] = base_sha
            pipeline.run(state, state_file.parent, workspace,
                         agent_drivers.get_driver(state["agent_kind"]), git, update, say, log, atomic_json)
        except InterruptedError:
            say("Cancelled")
        except pipeline.NeedsInput as exc:
            say("Waiting for user input: %s" % exc)
        except Exception as exc:
            say("ERROR: %s" % exc)
            if read_json(state_file)["status"] != "CANCELLED":
                update(status="FAILED", error=str(exc), finished_at=now(), pid=None)
        finally:
            update_state(state_file, {"worker_pid": None, "pid": None})


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_path TEXT NOT NULL,
 repo_url TEXT NOT NULL DEFAULT '',
 base_ref TEXT NOT NULL, gates TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nodes (id INTEGER PRIMARY KEY, name TEXT NOT NULL, endpoint TEXT NOT NULL,
 token TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workspaces (id INTEGER PRIMARY KEY,
 project_id INTEGER NOT NULL REFERENCES projects(id), node_id INTEGER NOT NULL REFERENCES nodes(id),
 name TEXT NOT NULL, source_kind TEXT NOT NULL, source_path TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
 UNIQUE(project_id,node_id,name));
CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
 title TEXT NOT NULL, description TEXT NOT NULL, acceptance_criteria TEXT NOT NULL,
 status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
 node_id INTEGER NOT NULL REFERENCES nodes(id), workspace_id INTEGER REFERENCES workspaces(id),
 agent_kind TEXT NOT NULL, status TEXT NOT NULL,
 error TEXT, workspace TEXT, source_path TEXT, branch TEXT, commit_sha TEXT, agent_session_id TEXT, question TEXT,
 started_at TEXT, finished_at TEXT, cleaned_at TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, artifacts TEXT NOT NULL DEFAULT '{}', logs TEXT NOT NULL DEFAULT '');
"""


def runner_call(node, method, path, payload=None, timeout=10):
    request = urllib.request.Request(node["endpoint"].rstrip("/") + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method, headers={"Authorization": "Bearer " + node["token"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("Runner HTTP %s: %s" % (exc.code, exc.read().decode()[:500])) from exc


class Manager(Http):
    db_path: Path

    def db(self):
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def row(self, con, table, key):
        row = con.execute("SELECT * FROM %s WHERE id=?" % table, (key,)).fetchone()
        if row is None:
            raise ValueError("%s %s not found" % (table, key))
        return dict(row)

    def route(self, method, path):
        if path == "/" and method == "GET":
            return self.reply(200, UI, "text/html")
        if path == "/zh" and method == "GET":
            return self.reply(200, UI_ZH, "text/html")
        if path == "/README.zh-CN.md" and method == "GET":
            return self.reply(200, Path(__file__).with_name("README.zh-CN.md").read_text(encoding="utf-8"), "text/markdown")
        if path == "/ui.js" and method == "GET":
            return self.reply(200, Path(__file__).with_name("ui.js").read_text(encoding="utf-8"), "application/javascript")
        if method == "GET" and re.fullmatch(r"/docs/[A-Za-z0-9.-]+\.md", path):
            doc = Path(__file__).parent / path.lstrip("/")
            if doc.is_file():
                return self.reply(200, doc.read_text(), "text/markdown")
        with closing(self.db()) as con, con:
            import control
            if control.route(self, con, method, path):
                return
            if method == "GET" and path in ("/api/projects", "/api/nodes", "/api/workspaces", "/api/tasks", "/api/runs"):
                table = path.split("/")[-1]
                rows = [dict(x) for x in con.execute("SELECT * FROM %s ORDER BY id DESC" % table)]
                if table == "nodes":
                    for row in rows: row.pop("token")
                if table == "projects":
                    for row in rows: row["gates"] = json.loads(row["gates"])
                if table == "runs":
                    for row in rows: row["artifacts"] = json.loads(row["artifacts"])
                return self.reply(200, rows)
            if method == "GET" and path == "/api/agents":
                return self.reply(200, agent_drivers.available_kinds())
            if method == "POST" and path == "/api/projects":
                p = self.payload()
                if not p.get("name", "").strip() or not (p.get("repo_url", "").strip() or p.get("source_path", "").strip()):
                    raise ValueError("Project requires a name and a repository URL or existing remote path")
                gates = p.get("gates", [])
                if not isinstance(gates, list) or not all(isinstance(x, str) for x in gates):
                    raise ValueError("gates must be a list of commands")
                cur = con.execute("INSERT INTO projects(name,source_path,repo_url,base_ref,gates,created_at) VALUES(?,?,?,?,?,?)",
                    (p["name"].strip(), p.get("source_path", "").strip(), git_io.validate_remote(p.get("repo_url", "").strip()),
                     p.get("base_ref") or "HEAD", json.dumps(gates), now()))
                return self.reply(201, {"id": cur.lastrowid})
            if method == "POST" and path == "/api/nodes":
                p = self.payload()
                runner_call(p, "GET", "/health")
                cur = con.execute("INSERT INTO nodes(name,endpoint,token,created_at) VALUES(?,?,?,?)",
                    (p["name"], p["endpoint"], p["token"], now()))
                return self.reply(201, {"id": cur.lastrowid})
            if method == "POST" and path == "/api/workspaces":
                p = self.payload()
                project = self.row(con, "projects", p["project_id"])
                self.row(con, "nodes", p["node_id"])
                kind = p.get("source_kind")
                if kind not in ("managed", "existing"):
                    raise ValueError("workspace source_kind must be managed or existing")
                if kind == "managed" and not project["repo_url"]:
                    raise ValueError("Project needs a repository URL for a managed clone")
                source_path = p.get("source_path", "").strip()
                if kind == "existing" and not source_path:
                    raise ValueError("existing workspace requires source_path")
                name = p.get("name", "").strip() or ("Managed clone" if kind == "managed" else source_path)
                existing = con.execute("SELECT id FROM workspaces WHERE project_id=? AND node_id=? AND name=?",
                                       (project["id"], p["node_id"], name)).fetchone()
                if existing:
                    return self.reply(200, {"id": existing["id"]})
                cur = con.execute("INSERT INTO workspaces(project_id,node_id,name,source_kind,source_path,created_at) VALUES(?,?,?,?,?,?)",
                    (project["id"], p["node_id"], name, kind, source_path, now()))
                return self.reply(201, {"id": cur.lastrowid})
            if method == "POST" and path == "/api/tasks":
                p = self.payload()
                self.row(con, "projects", p["project_id"])
                cur = con.execute("INSERT INTO tasks(project_id,title,description,acceptance_criteria,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (p["project_id"], p["title"], p["description"], p.get("acceptance_criteria", ""), "TODO", now(), now()))
                return self.reply(201, {"id": cur.lastrowid})
            if method == "POST" and path == "/api/runs":
                return self.reply(201, control.start_run(self, con, self.payload()))
            m = re.fullmatch(r"/api/runs/(\d+)(?:/(logs|artifacts|cancel|review|cleanup|package|bundle|answer))?", path)
            if m:
                run_id, suffix = m.groups()
                run = self.row(con, "runs", run_id)
                node = self.row(con, "nodes", run["node_id"])
                if method == "GET" and not suffix:
                    run["artifacts"] = json.loads(run["artifacts"])
                    return self.reply(200, run)
                if method == "GET" and suffix == "logs":
                    return self.reply(200, {"text": run["logs"]})
                if method == "GET" and suffix == "artifacts":
                    return self.reply(200, json.loads(run["artifacts"]))
                if method == "POST" and suffix == "answer":
                    if run["status"] != "NEEDS_INPUT":
                        raise ValueError("run is not waiting for input")
                    state = runner_call(node, "POST", "/runs/%s/answer" % run_id, self.payload())
                    con.execute("UPDATE runs SET status=?,question=NULL,updated_at=? WHERE id=?",
                                (state["status"], now(), run_id))
                    con.execute("UPDATE tasks SET status='RUNNING',updated_at=? WHERE id=?", (now(), run["task_id"]))
                    return self.reply(200, state)
                if method == "POST" and suffix in ("cancel", "review", "cleanup"):
                    payload = self.payload() if suffix == "review" else {}
                    if suffix == "review":
                        control.review_delivery(self, con, run, node, payload)
                    state = runner_call(node, "POST", "/runs/%s/%s" % (run_id, suffix), payload)
                    con.execute("UPDATE runs SET status=?,commit_sha=?,finished_at=?,cleaned_at=?,updated_at=? WHERE id=?",
                        (state["status"], state.get("commit_sha"), state.get("finished_at"), state.get("cleaned_at"), now(), run_id))
                    task_status = {"SUCCEEDED": "DONE", "REJECTED": "REJECTED", "CANCELLED": "CANCELLED"}.get(state["status"], state["status"])
                    con.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (task_status, now(), run["task_id"]))
                    return self.reply(200, state)
        self.reply(404, {"error": "not found"})


def poll(db_path):
    while True:
        try:
            con = sqlite3.connect(db_path, timeout=10)
            con.row_factory = sqlite3.Row
            rows = con.execute("SELECT r.id,r.task_id,r.node_id,r.workspace_id,n.endpoint,n.token FROM runs r JOIN nodes n ON n.id=r.node_id WHERE r.status IN ('PENDING','PROVISIONING','RUNNING','VERIFYING','NEEDS_INPUT','REVIEW')").fetchall()
            for row in rows:
                try:
                    state = runner_call(row, "GET", "/runs/%s" % row["id"])
                    logs = runner_call(row, "GET", "/runs/%s/logs" % row["id"])["text"]
                    artifacts = runner_call(row, "GET", "/runs/%s/artifacts" % row["id"])
                    with con:
                        current = con.execute("SELECT status FROM runs WHERE id=?", (row["id"],)).fetchone()
                        if current["status"] in ("SUCCEEDED", "REJECTED", "CANCELLED"):
                            continue
                        con.execute("UPDATE runs SET status=?,error=?,workspace=?,source_path=?,branch=?,agent_session_id=?,started_at=?,finished_at=?,artifacts=?,logs=?,updated_at=?,stage=?,commit_sha=?,question=? WHERE id=?",
                            (state["status"], state.get("error"), state.get("workspace"), state.get("source_path"), state.get("branch"),
                             state.get("agent_session_id"), state.get("started_at"), state.get("finished_at"),
                             json.dumps(artifacts), logs, now(), state.get("stage"), state.get("commit_sha"), state.get("question"), row["id"]))
                        if row["workspace_id"] and state.get("source_path"):
                            con.execute("UPDATE workspaces SET source_path=? WHERE id=? AND source_kind='managed'",
                                        (state["source_path"], row["workspace_id"]))
                        if state["status"] in ("FAILED", "CANCELLED", "NEEDS_INPUT", "REVIEW"):
                            con.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (state["status"], now(), row["task_id"]))
                    if state["status"] == "REVIEW" and artifacts.get("pipeline_version"):
                        import control
                        control.publish(con, db_path, row["id"], row)
                except Exception as exc:
                    with con:
                        con.execute("UPDATE runs SET error=?,updated_at=? WHERE id=?", ("Runner unavailable: " + str(exc), now(), row["id"]))
            con.close()
        except Exception as exc:
            sys.stderr.write("poll error: %s\n" % exc)
        time.sleep(2)


UI = (Path(__file__).with_name("ui.html")).read_text(encoding="utf-8")
UI_ZH = (Path(__file__).with_name("ui.zh-CN.html")).read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    manager = sub.add_parser("manager")
    manager.add_argument("--db", default="manager.sqlite3")
    manager.add_argument("--host", default="127.0.0.1")
    manager.add_argument("--port", type=int, default=8765)
    runner = sub.add_parser("runner")
    runner.add_argument("--root", required=True)
    runner.add_argument("--token")
    runner.add_argument("--token-file")
    runner.add_argument("--agent-access", choices=["workspace", "full"], default="workspace")
    runner.add_argument("--host", default="127.0.0.1")
    runner.add_argument("--port", type=int, default=8766)
    worker = sub.add_parser("execute")
    worker.add_argument("--root", required=True)
    worker.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.mode == "execute":
        execute(Path(args.root).resolve(), args.run_id)
        return
    if args.mode == "manager":
        Manager.db_path = Path(args.db).resolve()
        with sqlite3.connect(Manager.db_path) as con:
            con.executescript(SCHEMA)
            if "agent_session_id" not in [x[1] for x in con.execute("PRAGMA table_info(runs)")]:
                con.execute("ALTER TABLE runs ADD COLUMN agent_session_id TEXT")
            if "question" not in [x[1] for x in con.execute("PRAGMA table_info(runs)")]:
                con.execute("ALTER TABLE runs ADD COLUMN question TEXT")
            if "repo_url" not in [x[1] for x in con.execute("PRAGMA table_info(projects)")]:
                con.execute("ALTER TABLE projects ADD COLUMN repo_url TEXT NOT NULL DEFAULT ''")
            if "workspace_id" not in [x[1] for x in con.execute("PRAGMA table_info(runs)")]:
                con.execute("ALTER TABLE runs ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id)")
            if "source_path" not in [x[1] for x in con.execute("PRAGMA table_info(runs)")]:
                con.execute("ALTER TABLE runs ADD COLUMN source_path TEXT")
            import control
            control.migrate(con)
        threading.Thread(target=poll, args=(Manager.db_path,), daemon=True).start()
        handler = Manager
    else:
        Runner.root = Path(args.root).resolve()
        Runner.root.mkdir(parents=True, exist_ok=True)
        (Runner.root / "runs").mkdir(exist_ok=True)
        (Runner.root / "worktrees").mkdir(exist_ok=True)
        (Runner.root / "repos").mkdir(exist_ok=True)
        Runner.token = Path(args.token_file).read_text().strip() if args.token_file else args.token
        if not Runner.token:
            parser.error("runner requires --token or --token-file")
        Runner.agent_access = args.agent_access
        handler = Runner
    print("%s listening on http://%s:%s" % (args.mode, args.host, args.port), flush=True)
    ThreadingHTTPServer((args.host, args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
