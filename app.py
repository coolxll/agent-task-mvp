#!/usr/bin/env python3
"""Manager and remote Runner for agent-driven Git worktree tasks."""
import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

import agent_drivers
import control
import git_io
import pipeline


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


async def get_payload(request: Request) -> dict:
    body = await request.body()
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except Exception as exc:
        raise ValueError(f"invalid JSON payload: {exc}")


class Runner:
    root: Path = None
    token: str = None
    agent_access: str = "workspace"

    def __init__(self, root: Optional[Path] = None, token: Optional[str] = None, agent_access: str = "workspace"):
        if root is not None:
            self.root = Path(root).resolve()
        if token is not None:
            self.token = token
        self.agent_access = agent_access

    def state_path(self, run_id):
        if not re.fullmatch(r"[0-9]+", str(run_id)):
            raise ValueError("invalid run id")
        root = getattr(self, "root", None) or Runner.root
        return root / "runs" / str(run_id) / "state.json"

    def update(self, run_id, **changes):
        path = self.state_path(run_id)
        return update_state(path, changes)

    def cleanup(self, state, delete_branch=False):
        root = getattr(self, "root", None) or Runner.root
        source = Path(state["source_path"])
        workspace = Path(state["workspace"])
        if workspace.parent != root / "worktrees" or workspace.name != str(state["id"]):
            raise ValueError("workspace outside Runner root")
        if not state["branch"].startswith("agent/task-"):
            raise ValueError("branch is not owned by Runner")
        if workspace.is_symlink():
            raise ValueError("workspace must not be a symlink")
        if workspace.exists():
            git("worktree", "remove", "--force", str(workspace), cwd=source)
        if delete_branch and source.exists() and git("branch", "--list", state["branch"], cwd=source).stdout.strip():
            git("branch", "-D", state["branch"], cwd=source)


def create_runner_app(root: Path, token: str, agent_access: str = "workspace") -> FastAPI:
    app = FastAPI(title="Agent Task Runner", docs_url="/docs", redoc_url=None)
    runner = Runner(root, token, agent_access)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if exc.detail != "Not Found" else "not found"
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(Exception)
    async def general_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": str(exc)})

    @app.middleware("http")
    async def runner_middleware(request: Request, call_next):
        origin = request.headers.get("origin")
        host = request.headers.get("host")
        if request.method == "POST" and origin:
            if urlparse(origin).netloc != host:
                return JSONResponse(status_code=403, content={"error": "cross-origin mutation is not allowed"})
        content_length = int(request.headers.get("content-length", 0))
        if content_length > 72_000_000:
            return JSONResponse(status_code=400, content={"error": "request too large"})
        auth = request.headers.get("authorization")
        if auth != "Bearer " + token:
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"ok": True, "api_version": 2, "agent_kinds": agent_drivers.available_kinds()}

    @app.post("/runs", status_code=201)
    async def create_run(request: Request):
        p = await get_payload(request)
        run_id = str(int(p["id"]))
        source_kind = p.get("source_kind", "existing")
        if source_kind == "managed":
            workspace_id = str(int(p["workspace_id"]))
            if not p.get("repo_url") and not p.get("source_bundle"):
                raise ValueError("managed workspace requires repo_url")
            source = root / "repos" / workspace_id
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
        run_dir = root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        branch = "agent/task-%s-run-%s-%s" % (p["task_id"], run_id, slug(p["title"]))
        workspace = root / "worktrees" / run_id
        state = {"id": int(run_id), "status": "PENDING", "source_path": str(source),
                 "source_kind": source_kind, "repo_url": p.get("repo_url", ""),
                 "workspace_id": p.get("workspace_id"),
                 "workspace": str(workspace), "branch": branch, "base_ref": p.get("base_ref") or "HEAD",
                 "title": p["title"], "description": p["description"],
                 "acceptance_criteria": p.get("acceptance_criteria", ""),
                 "gates": p.get("gates", []), "agent_kind": agent_kind, "agent_access": agent_access,
                 "pid": None,
                 "error": None, "created_at": now(), "updated_at": now()}
        if not isinstance(state["gates"], list) or not all(isinstance(x, str) for x in state["gates"]):
            raise ValueError("gates must be a list of commands")
        state.update(stage="PENDING", package=p.get("package", {}), worker_pid=None)
        if p.get("source_bundle"):
            git_io.decode_bundle(p["source_bundle"], run_dir / "input.bundle")
        atomic_json(run_dir / "package.json", p.get("package", {}))
        atomic_json(run_dir / "state.json", state)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "execute", "--root", str(root),
                          "--run-id", run_id], start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return state

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        sp = runner.state_path(run_id)
        if not sp.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return read_json(sp)

    @app.get("/runs/{run_id}/package")
    def get_run_package(run_id: str):
        sp = runner.state_path(run_id)
        if not sp.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return read_json(sp).get("package", {})

    @app.get("/runs/{run_id}/bundle")
    def get_run_bundle(run_id: str):
        sp = runner.state_path(run_id)
        if not sp.is_file():
            raise HTTPException(status_code=404, detail="not found")
        state = read_json(sp)
        if state["status"] not in ("REVIEW", "SUCCEEDED"):
            raise ValueError("result bundle is not ready")
        run_dir = root / "runs" / str(run_id)
        return git_io.encode_bundle(run_dir / "result.bundle")

    @app.get("/runs/{run_id}/logs")
    def get_run_logs(run_id: str):
        sp = runner.state_path(run_id)
        if not sp.is_file():
            raise HTTPException(status_code=404, detail="not found")
        run_dir = root / "runs" / str(run_id)
        file = run_dir / "run.log"
        return {"text": file.read_text(errors="replace")[-200_000:] if file.exists() else ""}

    @app.get("/runs/{run_id}/artifacts")
    def get_run_artifacts(run_id: str):
        sp = runner.state_path(run_id)
        if not sp.is_file():
            raise HTTPException(status_code=404, detail="not found")
        run_dir = root / "runs" / str(run_id)
        file = run_dir / "artifacts.json"
        return read_json(file) if file.exists() else {}

    @app.post("/runs/{run_id}/answer")
    async def run_answer(run_id: str, request: Request):
        p = await get_payload(request)
        answer = p.get("answer", "").strip()
        if not answer or len(answer) > 20000:
            raise ValueError("answer must contain 1–20000 characters")
        state = update_state(runner.state_path(run_id), {"status": "RUNNING", "answer": answer,
            "question": None, "error": None}, allowed_from=("NEEDS_INPUT",))
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "execute", "--root", str(root),
                          "--run-id", run_id], start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return state

    @app.post("/runs/{run_id}/cancel")
    def run_cancel(run_id: str):
        state = read_json(runner.state_path(run_id))
        if state["status"] not in ("PENDING", "PROVISIONING", "RUNNING", "VERIFYING", "NEEDS_INPUT"):
            raise ValueError("run is not active")
        state = update_state(runner.state_path(run_id),
            {"status": "CANCELLED", "finished_at": now()},
            allowed_from=("PENDING", "PROVISIONING", "RUNNING", "VERIFYING", "NEEDS_INPUT"))
        if state.get("pid"):
            try:
                agent_drivers.get_driver(state["agent_kind"]).cancel(state["pid"])
            except ProcessLookupError:
                pass
        return state

    @app.post("/runs/{run_id}/cleanup")
    def run_cleanup(run_id: str):
        state = read_json(runner.state_path(run_id))
        if state["status"] not in ("FAILED", "CANCELLED"):
            raise ValueError("only failed or cancelled runs can be cleaned here")
        if state.get("worker_pid"):
            try:
                os.kill(state["worker_pid"], 0)
            except ProcessLookupError:
                pass
            else:
                raise ValueError("worker is stopping; retry cleanup shortly")
        runner.cleanup(state, delete_branch=True)
        return runner.update(run_id, cleaned_at=now())

    @app.post("/runs/{run_id}/review")
    async def run_review(run_id: str, request: Request):
        p = await get_payload(request)
        decision = p.get("decision")
        state = read_json(runner.state_path(run_id))
        if state["status"] != "REVIEW" or decision not in ("approve", "reject"):
            raise ValueError("run is not ready for review")
        source = Path(state["source_path"])
        workspace = Path(state["workspace"])
        run_dir = root / "runs" / run_id
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
        runner.cleanup(state, delete_branch=decision == "reject")
        return runner.update(run_id, status="SUCCEEDED" if decision == "approve" else "REJECTED",
                             commit_sha=commit, finished_at=now(), cleaned_at=now())

    return app


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


class Manager:
    db_path: Path = None

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is not None:
            self.db_path = Path(db_path).resolve()

    def db(self):
        db_file = getattr(self, "db_path", None) or Manager.db_path
        con = sqlite3.connect(db_file, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def row(self, con, table, key):
        row = con.execute("SELECT * FROM %s WHERE id=?" % table, (key,)).fetchone()
        if row is None:
            raise ValueError("%s %s not found" % (table, key))
        return dict(row)


def create_manager_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="Agent Task Manager", docs_url="/docs", redoc_url=None)
    manager = Manager(db_path)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if exc.detail != "Not Found" else "not found"
        return JSONResponse(status_code=exc.status_code, content={"error": detail})

    @app.exception_handler(Exception)
    async def general_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": str(exc)})

    @app.middleware("http")
    async def manager_middleware(request: Request, call_next):
        origin = request.headers.get("origin")
        host = request.headers.get("host")
        if request.method == "POST" and origin:
            if urlparse(origin).netloc != host:
                return JSONResponse(status_code=403, content={"error": "cross-origin mutation is not allowed"})
        content_length = int(request.headers.get("content-length", 0))
        if content_length > 72_000_000:
            return JSONResponse(status_code=400, content={"error": "request too large"})
        return await call_next(request)

    # Static / Document routes
    @app.get("/", response_class=HTMLResponse)
    def index():
        return UI

    @app.get("/zh", response_class=HTMLResponse)
    def index_zh():
        return UI_ZH

    @app.get("/ui.js")
    def get_ui_js():
        return Response(content=Path(__file__).with_name("ui.js").read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/README.zh-CN.md")
    def get_readme():
        return Response(content=Path(__file__).with_name("README.zh-CN.md").read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")

    @app.get("/docs/{name}")
    def get_doc(name: str):
        if not re.fullmatch(r"[A-Za-z0-9.-]+\.md", name):
            raise HTTPException(status_code=404, detail="not found")
        doc = Path(__file__).parent / "docs" / name
        if not doc.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return Response(content=doc.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")

    # API: Folders
    @app.get("/api/folders")
    def get_folders(path: Optional[str] = None):
        target = Path(path or str(Path.home() / "workspace")).expanduser().resolve(strict=True)
        if not target.is_dir():
            raise ValueError("Not a directory")
        directories = []
        for child in sorted(target.iterdir()):
            if not child.name.startswith(".") and child.is_dir():
                directories.append({"name": child.name, "path": str(child), "git": (child / ".git").exists()})
        return {"path": str(target), "parent": str(target.parent), "directories": directories}

    # API: Projects
    @app.get("/api/projects")
    def list_projects():
        with closing(manager.db()) as con:
            rows = [dict(x) for x in con.execute("SELECT * FROM projects ORDER BY id DESC")]
            for row in rows:
                row["gates"] = json.loads(row["gates"])
            return rows

    @app.post("/api/projects", status_code=201)
    async def create_project(request: Request):
        p = await get_payload(request)
        if not p.get("name", "").strip() or not (p.get("repo_url", "").strip() or p.get("source_path", "").strip()):
            raise ValueError("Project requires a name and a repository URL or existing remote path")
        gates = p.get("gates", [])
        if not isinstance(gates, list) or not all(isinstance(x, str) for x in gates):
            raise ValueError("gates must be a list of commands")
        with closing(manager.db()) as con, con:
            cur = con.execute("INSERT INTO projects(name,source_path,repo_url,base_ref,gates,created_at) VALUES(?,?,?,?,?,?)",
                (p["name"].strip(), p.get("source_path", "").strip(), git_io.validate_remote(p.get("repo_url", "").strip()),
                 p.get("base_ref") or "HEAD", json.dumps(gates), now()))
            return {"id": cur.lastrowid}

    @app.post("/api/projects/import")
    async def import_project(request: Request):
        p = await get_payload(request)
        info = git_io.inspect_repo(p["path"])
        with closing(manager.db()) as con, con:
            existing = con.execute("SELECT id FROM projects WHERE local_path=?", (info["local_path"],)).fetchone()
            if existing:
                project_id = existing["id"]
            else:
                cur = con.execute("INSERT INTO projects(name,source_path,repo_url,base_ref,gates,created_at,local_path,delivery) VALUES(?,?,?,?,?,?,?,?)",
                    (info["name"], "", info["repo_url"], info["base_ref"], "[]", now(), info["local_path"],
                     "github" if git_io.github_repo(info["repo_url"]) else "branch"))
                project_id = cur.lastrowid
            return {**info, "id": project_id}

    @app.post("/api/projects/{project_id}/settings")
    async def update_project_settings(project_id: int, request: Request):
        body = await get_payload(request)
        with closing(manager.db()) as con, con:
            project = manager.row(con, "projects", project_id)
            delivery = body.get("delivery", project["delivery"])
            if delivery not in ("github", "branch"):
                raise ValueError("Invalid delivery method")
            if delivery == "github" and not git_io.github_repo(project["repo_url"]):
                raise ValueError("GitHub delivery requires a github.com repository remote")
            gates = body.get("gates", json.loads(project["gates"]))
            if not isinstance(gates, list) or not all(isinstance(x, str) and x.strip() for x in gates):
                raise ValueError("Invalid gates")
            base = body.get("base_ref", project["base_ref"]).strip()
            if not base or base.startswith("-"):
                raise ValueError("Invalid base branch")
            con.execute("UPDATE projects SET delivery=?,gates=?,base_ref=? WHERE id=?",
                        (delivery, json.dumps(gates), base, project["id"]))
            return {"ok": True}

    # API: Nodes
    @app.get("/api/nodes")
    def list_nodes():
        with closing(manager.db()) as con:
            rows = [dict(x) for x in con.execute("SELECT * FROM nodes ORDER BY id DESC")]
            for row in rows:
                row.pop("token", None)
            return rows

    @app.post("/api/nodes", status_code=201)
    async def create_node(request: Request):
        p = await get_payload(request)
        runner_call(p, "GET", "/health")
        with closing(manager.db()) as con, con:
            cur = con.execute("INSERT INTO nodes(name,endpoint,token,created_at) VALUES(?,?,?,?)",
                (p["name"], p["endpoint"], p["token"], now()))
            return {"id": cur.lastrowid}

    # API: Workspaces
    @app.get("/api/workspaces")
    def list_workspaces():
        with closing(manager.db()) as con:
            return [dict(x) for x in con.execute("SELECT * FROM workspaces ORDER BY id DESC")]

    @app.post("/api/workspaces")
    async def create_workspace(request: Request):
        p = await get_payload(request)
        with closing(manager.db()) as con, con:
            project = manager.row(con, "projects", p["project_id"])
            manager.row(con, "nodes", p["node_id"])
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
                return JSONResponse(status_code=200, content={"id": existing["id"]})
            cur = con.execute("INSERT INTO workspaces(project_id,node_id,name,source_kind,source_path,created_at) VALUES(?,?,?,?,?,?)",
                (project["id"], p["node_id"], name, kind, source_path, now()))
            return JSONResponse(status_code=201, content={"id": cur.lastrowid})

    # API: Tasks
    @app.get("/api/tasks")
    def list_tasks():
        with closing(manager.db()) as con:
            return [dict(x) for x in con.execute("SELECT * FROM tasks ORDER BY id DESC")]

    @app.post("/api/tasks", status_code=201)
    async def create_task(request: Request):
        p = await get_payload(request)
        with closing(manager.db()) as con, con:
            manager.row(con, "projects", p["project_id"])
            cur = con.execute("INSERT INTO tasks(project_id,title,description,acceptance_criteria,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (p["project_id"], p["title"], p["description"], p.get("acceptance_criteria", ""), "TODO", now(), now()))
            return {"id": cur.lastrowid}

    # API: Agents
    @app.get("/api/agents")
    def list_agents():
        return agent_drivers.available_kinds()

    # API: Submit
    @app.post("/api/submit", status_code=201)
    async def submit_task(request: Request):
        p = await get_payload(request)
        requirement = p.get("requirement", "").strip()
        if not requirement or len(requirement) > 100000:
            raise ValueError("Requirement must contain 1–100000 characters")
        planner_mode = p.get('planner', 'remote')
        if planner_mode not in ('remote', 'manager'):
            raise ValueError('planner must be remote or manager')
        with closing(manager.db()) as con, con:
            project = manager.row(con, "projects", p["project_id"])
            node = manager.row(con, "nodes", p["node_id"])
            if project["local_path"] and git_io.inspect_repo(project["local_path"])["dirty"]:
                raise ValueError("工作目录有未提交改动，请先提交后再运行；系统不会自动修改或忽略这些改动。")
            title = requirement.splitlines()[0][:100]
            cur = con.execute("INSERT INTO tasks(project_id,title,description,acceptance_criteria,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (project["id"], title, requirement, "", "TODO", now(), now()))
            task_id = cur.lastrowid
            manager_plan = None
            if planner_mode == 'manager':
                try:
                    import native_planner
                    manager_plan = await native_planner.plan_task(requirement, project, node)
                except Exception as exc:
                    error = 'Manager Planner failed: ' + str(exc)[:2000]
                    failed = con.execute('INSERT INTO runs(task_id,node_id,agent_kind,status,error,created_at,updated_at) '
                        'VALUES(?,?,?,?,?,?,?)', (task_id, node['id'], p.get('agent_kind', agent_drivers.default_kind()),
                                                  'FAILED', error, now(), now()))
                    con.execute("UPDATE tasks SET status='FAILED',updated_at=? WHERE id=?", (now(), task_id))
                    return {'id': failed.lastrowid, 'task_id': task_id, 'status': 'FAILED', 'error': error}
            result = control.start_run(manager, con, {"task_id": task_id, "node_id": p["node_id"],
                "agent_kind": p.get("agent_kind", agent_drivers.default_kind()),
                "planner": planner_mode, "manager_plan": manager_plan})
            return result

    # API: Runs
    @app.get("/api/runs")
    def list_runs():
        with closing(manager.db()) as con:
            rows = [dict(x) for x in con.execute("SELECT * FROM runs ORDER BY id DESC")]
            for row in rows:
                row["artifacts"] = json.loads(row["artifacts"])
            return rows

    @app.post("/api/runs", status_code=201)
    async def create_run_endpoint(request: Request):
        p = await get_payload(request)
        with closing(manager.db()) as con, con:
            return control.start_run(manager, con, p)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int):
        with closing(manager.db()) as con:
            run = manager.row(con, "runs", run_id)
            run["artifacts"] = json.loads(run["artifacts"])
            return run

    @app.get("/api/runs/{run_id}/logs")
    def get_run_logs(run_id: int):
        with closing(manager.db()) as con:
            run = manager.row(con, "runs", run_id)
            return {"text": run["logs"]}

    @app.get("/api/runs/{run_id}/artifacts")
    def get_run_artifacts(run_id: int):
        with closing(manager.db()) as con:
            run = manager.row(con, "runs", run_id)
            return json.loads(run["artifacts"])

    @app.get("/api/runs/{run_id}/package")
    def get_run_package(run_id: int):
        with closing(manager.db()) as con:
            run = manager.row(con, "runs", run_id)
            return json.loads(run["package"])

    @app.post("/api/runs/{run_id}/publish")
    def publish_run_endpoint(run_id: int):
        with closing(manager.db()) as con, con:
            run = manager.row(con, "runs", run_id)
            if run["status"] != "REVIEW":
                raise ValueError("Run is not ready for delivery")
            con.execute("UPDATE runs SET delivery_status='pending',delivery_error=NULL WHERE id=? AND delivery_status='failed'", (run["id"],))
            return {"ok": True}

    @app.post("/api/runs/{run_id}/answer")
    async def answer_run(run_id: int, request: Request):
        p = await get_payload(request)
        with closing(manager.db()) as con, con:
            run = manager.row(con, "runs", run_id)
            node = manager.row(con, "nodes", run["node_id"])
            if run["status"] != "NEEDS_INPUT":
                raise ValueError("run is not waiting for input")
            state = runner_call(node, "POST", "/runs/%s/answer" % run_id, p)
            con.execute("UPDATE runs SET status=?,question=NULL,updated_at=? WHERE id=?",
                        (state["status"], now(), run_id))
            con.execute("UPDATE tasks SET status='RUNNING',updated_at=? WHERE id=?", (now(), run["task_id"]))
            return state

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: int):
        with closing(manager.db()) as con, con:
            run = manager.row(con, "runs", run_id)
            node = manager.row(con, "nodes", run["node_id"])
            state = runner_call(node, "POST", "/runs/%s/cancel" % run_id, {})
            con.execute("UPDATE runs SET status=?,commit_sha=?,finished_at=?,cleaned_at=?,updated_at=? WHERE id=?",
                (state["status"], state.get("commit_sha"), state.get("finished_at"), state.get("cleaned_at"), now(), run_id))
            task_status = {"SUCCEEDED": "DONE", "REJECTED": "REJECTED", "CANCELLED": "CANCELLED"}.get(state["status"], state["status"])
            con.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (task_status, now(), run["task_id"]))
            return state

    @app.post("/api/runs/{run_id}/cleanup")
    def cleanup_run(run_id: int):
        with closing(manager.db()) as con, con:
            run = manager.row(con, "runs", run_id)
            node = manager.row(con, "nodes", run["node_id"])
            state = runner_call(node, "POST", "/runs/%s/cleanup" % run_id, {})
            con.execute("UPDATE runs SET status=?,commit_sha=?,finished_at=?,cleaned_at=?,updated_at=? WHERE id=?",
                (state["status"], state.get("commit_sha"), state.get("finished_at"), state.get("cleaned_at"), now(), run_id))
            task_status = {"SUCCEEDED": "DONE", "REJECTED": "REJECTED", "CANCELLED": "CANCELLED"}.get(state["status"], state["status"])
            con.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (task_status, now(), run["task_id"]))
            return state

    @app.post("/api/runs/{run_id}/review")
    async def review_run(run_id: int, request: Request):
        p = await get_payload(request)
        with closing(manager.db()) as con, con:
            run = manager.row(con, "runs", run_id)
            node = manager.row(con, "nodes", run["node_id"])
            control.review_delivery(manager, con, run, node, p)
            state = runner_call(node, "POST", "/runs/%s/review" % run_id, p)
            con.execute("UPDATE runs SET status=?,commit_sha=?,finished_at=?,cleaned_at=?,updated_at=? WHERE id=?",
                (state["status"], state.get("commit_sha"), state.get("finished_at"), state.get("cleaned_at"), now(), run_id))
            task_status = {"SUCCEEDED": "DONE", "REJECTED": "REJECTED", "CANCELLED": "CANCELLED"}.get(state["status"], state["status"])
            con.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (task_status, now(), run["task_id"]))
            return state

    return app


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
        print("%s listening on http://%s:%s" % (args.mode, args.host, args.port), flush=True)
        app = create_manager_app(Manager.db_path)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    else:
        root = Path(args.root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        (root / "runs").mkdir(exist_ok=True)
        (root / "worktrees").mkdir(exist_ok=True)
        (root / "repos").mkdir(exist_ok=True)
        token = Path(args.token_file).read_text().strip() if args.token_file else args.token
        if not token:
            parser.error("runner requires --token or --token-file")
        Runner.root = root
        Runner.token = token
        Runner.agent_access = args.agent_access
        print("%s listening on http://%s:%s" % (args.mode, args.host, args.port), flush=True)
        app = create_runner_app(root, token, args.agent_access)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
