"""Manager-side task packages, local folders, and reviewed delivery."""
import json
import agent_drivers
import os
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlparse
import git_io

DELIVERY_LOCK = threading.RLock()


def migrate(con):
    fields = {
        'projects': {'local_path': "TEXT NOT NULL DEFAULT ''", 'delivery': "TEXT NOT NULL DEFAULT 'branch'"},
        'runs': {'package': "TEXT NOT NULL DEFAULT '{}'", 'stage': 'TEXT',
                 'delivery_status': "TEXT NOT NULL DEFAULT 'pending'", 'delivery_error': 'TEXT',
                 'delivery_error_kind': 'TEXT', 'error_kind': 'TEXT',
                 'pr_url': 'TEXT', 'pr_number': 'INTEGER', 'delivery_repo': 'TEXT'},
    }
    for table, columns in fields.items():
        present = {x[1] for x in con.execute('PRAGMA table_info(%s)' % table)}
        for name, declaration in columns.items():
            if name not in present:
                con.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, name, declaration))


def data_root(db_path):
    path = Path(str(db_path) + '.data')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def route(manager, con, method, path):
    from app import now
    if path == '/api/folders' and method == 'GET':
        query = parse_qs(urlparse(manager.path).query)
        folder = Path(query.get('path', [str(Path.home() / 'workspace')])[0]).expanduser().resolve(strict=True)
        if not folder.is_dir():
            raise ValueError('Not a directory')
        directories = []
        for child in sorted(folder.iterdir()):
            if not child.name.startswith('.') and child.is_dir():
                directories.append({'name': child.name, 'path': str(child), 'git': (child / '.git').exists()})
        manager.reply(200, {'path': str(folder), 'parent': str(folder.parent), 'directories': directories})
        return True
    if path == '/api/projects/import' and method == 'POST':
        info = git_io.inspect_repo(manager.payload()['path'])
        existing = con.execute('SELECT id FROM projects WHERE local_path=?', (info['local_path'],)).fetchone()
        if existing:
            project_id = existing['id']
        else:
            cur = con.execute('INSERT INTO projects(name,source_path,repo_url,base_ref,gates,created_at,local_path,delivery) VALUES(?,?,?,?,?,?,?,?)',
                (info['name'], '', info['repo_url'], info['base_ref'], '[]', now(), info['local_path'],
                 'local'))
            project_id = cur.lastrowid
        manager.reply(200, {**info, 'id': project_id})
        return True
    if path.startswith('/api/projects/') and method == 'POST':
        parts = path.split('/')
        if len(parts) == 5 and parts[4] == 'settings':
            project = manager.row(con, 'projects', int(parts[3]))
            body = manager.payload()
            delivery = body.get('delivery', project['delivery'])
            if delivery not in ('github', 'branch', 'local'):
                raise ValueError('Invalid delivery method')
            if delivery == 'github' and not git_io.github_repo(project['repo_url']):
                raise ValueError('GitHub delivery requires a github.com repository remote')
            if delivery == 'local' and not project['local_path']:
                raise ValueError('Local merge requires an imported Git folder on Manager')
            gates = body.get('gates', json.loads(project['gates']))
            if not isinstance(gates, list) or not all(isinstance(x, str) and x.strip() for x in gates):
                raise ValueError('Invalid gates')
            base = body.get('base_ref', project['base_ref']).strip()
            if not base or base.startswith('-'):
                raise ValueError('Invalid base branch')
            con.execute('UPDATE projects SET delivery=?,gates=?,base_ref=? WHERE id=?',
                        (delivery, json.dumps(gates), base, project['id']))
            manager.reply(200, {'ok': True})
            return True
    if path == '/api/submit' and method == 'POST':
        p = manager.payload()
        requirement = p.get('requirement', '').strip()
        if not requirement or len(requirement) > 100000:
            raise ValueError('Requirement must contain 1–100000 characters')
        project = manager.row(con, 'projects', p['project_id'])
        manager.row(con, 'nodes', p['node_id'])
        # Validate before creating a Task; snapshot repeats the check at dispatch.
        if project['local_path'] and git_io.inspect_repo(project['local_path'])['dirty']:
            raise ValueError('工作目录有未提交改动，请先提交后再运行；系统不会自动修改或忽略这些改动。')
        title = requirement.splitlines()[0][:100]
        cur = con.execute('INSERT INTO tasks(project_id,title,description,acceptance_criteria,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (project['id'], title, requirement, '', 'TODO', now(), now()))
        result = start_run(manager, con, {'task_id': cur.lastrowid, 'node_id': p['node_id'],
                                          'agent_kind': p.get('agent_kind', agent_drivers.default_kind())})
        manager.reply(201, result)
        return True
    if path.startswith('/api/runs/'):
        parts = path.split('/')
        if len(parts) == 5:
            run = manager.row(con, 'runs', int(parts[3]))
            if method == 'GET' and parts[4] == 'package':
                manager.reply(200, json.loads(run['package']))
                return True
            if method == 'POST' and parts[4] == 'publish':
                if run['status'] != 'REVIEW':
                    raise ValueError('Run is not ready for delivery')
                con.execute("UPDATE runs SET delivery_status='pending',delivery_error=NULL,delivery_error_kind=NULL WHERE id=? AND delivery_status='failed'", (run['id'],))
                manager.reply(200, {'ok': True})
                return True
    return False


def start_run(manager, con, p):
    from app import now, runner_call, atomic_json
    agent_kind = p.get('agent_kind', agent_drivers.default_kind())
    agent_drivers.get_driver(agent_kind)
    task = manager.row(con, 'tasks', p['task_id'])
    project = manager.row(con, 'projects', task['project_id'])
    git_io.validate_remote(project['repo_url'])
    if project['delivery'] == 'local' and not project['local_path']:
        raise ValueError('Local merge requires an imported Git folder on Manager')
    if task['status'] not in ('TODO', 'FAILED', 'REJECTED', 'CANCELLED'):
        raise ValueError('Task is not runnable')
    if p.get('workspace_id'):
        selected = manager.row(con, 'workspaces', p['workspace_id'])
        if selected['project_id'] != project['id']:
            raise ValueError('Workspace does not belong to project')
    else:
        node_id = p['node_id']
        manager.row(con, 'nodes', node_id)
        kind = 'managed' if project['repo_url'] or project['local_path'] else 'existing'
        name = 'Local snapshot' if project['local_path'] else 'Project default'
        selected = con.execute('SELECT * FROM workspaces WHERE project_id=? AND node_id=? AND name=?',
                               (project['id'], node_id, name)).fetchone()
        if not selected:
            cur = con.execute('INSERT INTO workspaces(project_id,node_id,name,source_kind,source_path,created_at) VALUES(?,?,?,?,?,?)',
                (project['id'], node_id, name, kind, project['source_path'] if kind == 'existing' else '', now()))
            selected = manager.row(con, 'workspaces', cur.lastrowid)
    node = manager.row(con, 'nodes', selected['node_id'])
    base_branch = project['base_ref']
    if project['delivery'] == 'github' and base_branch == 'HEAD':
        owner_repo = git_io.github_repo(project['repo_url'])
        if not owner_repo:
            raise ValueError('GitHub delivery requires a github.com repository URL')
        result = json.loads(gh(['repo', 'view', owner_repo, '--json', 'defaultBranchRef']))
        base_branch = result['defaultBranchRef']['name']
    cur = con.execute('INSERT INTO runs(task_id,node_id,workspace_id,agent_kind,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
        (task['id'], node['id'], selected['id'], agent_kind, 'PENDING', now(), now()))
    run_id = cur.lastrowid
    root = data_root(manager.db_path) / 'runs' / str(run_id)
    root.mkdir(parents=True, exist_ok=True)
    con.execute("UPDATE tasks SET status='RUNNING',updated_at=? WHERE id=?", (now(), task['id']))
    package = {'version': 1, 'task_id': task['id'], 'run_id': run_id, 'requirement': task['description'],
        'agent_kind': agent_kind,
        'planner': p.get('planner', 'remote'), 'manager_plan': p.get('manager_plan'),
        'source': {'repo_url': project['repo_url'], 'base_branch': base_branch, 'commit': None},
        'node': {'id': node['id'], 'name': node['name']},
        'workflow': ['plan', 'implement', 'code_review', 'test', 'acceptance'],
        'gates': json.loads(project['gates']), 'delivery': project['delivery'],
        'created_at': now()}
    try:
        bundle = None
        if project['local_path']:
            info, bundle = git_io.snapshot(project['local_path'], root / 'input.bundle')
            package['source']['commit'] = info['base_sha']
            package['source']['local_branch'] = info['branch']
            package['source']['bundle_sha256'] = bundle['sha256']
        atomic_json(root / 'package.json', package)
        con.execute('UPDATE runs SET package=? WHERE id=?', (json.dumps(package), run_id))
        # Durable intent before making a network request.
        con.commit()
        payload = {'id': run_id, 'task_id': task['id'], 'title': task['title'],
            'agent_kind': agent_kind,
            'description': task['description'], 'acceptance_criteria': task['acceptance_criteria'],
            'source_kind': 'managed' if bundle else selected['source_kind'],
            'source_path': selected['source_path'], 'workspace_id': selected['id'],
            'repo_url': project['repo_url'], 'base_ref': project['base_ref'], 'gates': package['gates'],
            'package': package}
        if bundle:
            payload['source_bundle'] = bundle
        health = runner_call(node, 'GET', '/health')
        if health.get('api_version') != 2:
            raise ValueError('Runner is outdated; deploy the current Runner files')
        if agent_kind not in health.get('agent_kinds', []):
            raise ValueError('Runner does not support agent kind: ' + agent_kind)
        runner_call(node, 'POST', '/runs', payload, timeout=180)
    except Exception as exc:
        con.execute("UPDATE runs SET status='FAILED',error=?,error_kind=?,package=?,updated_at=? WHERE id=?",
                    (str(exc), getattr(exc, 'kind', None), json.dumps(package), now(), run_id))
        con.execute("UPDATE tasks SET status='FAILED',updated_at=? WHERE id=?", (now(), task['id']))
        return {'id': run_id, 'task_id': task['id'], 'status': 'FAILED', 'error': str(exc)}
    return {'id': run_id, 'task_id': task['id'], 'status': 'PENDING'}


def gh(args, cwd=None):
    return git_io.command(['gh', *args], cwd=cwd)


def merge_local_result(con, run, package, artifacts):
    """Fast-forward only the exact clean branch submitted by the user."""
    project = con.execute('SELECT p.local_path FROM projects p JOIN tasks t ON t.project_id=p.id '
                          'WHERE t.id=?', (run['task_id'],)).fetchone()
    if not project or not project['local_path']:
        raise ValueError('The original local Git folder is no longer configured')
    path = project['local_path']
    info = git_io.inspect_repo(path)
    branch = package['source'].get('local_branch')
    base = package['source'].get('commit')
    reviewed = artifacts['commit_sha']
    if not branch or not base or base != artifacts['base_sha']:
        raise ValueError('Task package has no valid local branch and base commit')
    if info['branch'] != branch:
        raise ValueError('The local project is on another branch; switch back before approval')
    if info['base_sha'] == reviewed:
        return  # A previous approval merged the reviewed commit before recording success.
    if info['dirty']:
        raise ValueError('The local project has uncommitted changes; approval did not modify it')
    if info['base_sha'] != base:
        raise ValueError('The local branch moved since task submission; review and integrate manually')
    repo = run['delivery_repo']
    if not repo or not Path(repo).is_dir():
        raise ValueError('Reviewed result is not available on Manager')
    branch_ref = 'refs/heads/' + artifacts['branch']
    if git_io.git('rev-parse', branch_ref, cwd=repo) != reviewed:
        raise ValueError('Reviewed result branch changed')
    git_io.git('fetch', '--no-tags', repo, branch_ref, cwd=path)
    if git_io.git('rev-parse', 'FETCH_HEAD', cwd=path) != reviewed:
        raise ValueError('Fetched result differs from the reviewed commit')
    # Git itself checks for concurrent local edits before updating the checkout.
    git_io.git('merge', '--ff-only', 'FETCH_HEAD', cwd=path)
    if git_io.git('rev-parse', 'HEAD', cwd=path) != reviewed:
        raise ValueError('Local merge did not reach the reviewed commit')


def publish(con, db_path, run_id, node):
    from app import runner_call
    with DELIVERY_LOCK:
        run = dict(con.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone())
        if run['delivery_status'] not in ('pending', 'publishing') or run['status'] != 'REVIEW':
            return
        with con:
            con.execute("UPDATE runs SET delivery_status='publishing' WHERE id=?", (run_id,))
        try:
            package = json.loads(run['package'])
            artifacts = json.loads(run['artifacts'])
            root = data_root(db_path) / 'runs' / str(run_id)
            root.mkdir(parents=True, exist_ok=True)
            bundle = root / 'result.bundle'
            git_io.decode_bundle(runner_call(node, 'GET', '/runs/%s/bundle' % run_id, timeout=180), bundle)
            repo = root / 'result.git'
            if not repo.exists():
                git_io.command(['git', 'init', '--bare', str(repo)])
            git_io.git('fetch', str(bundle), artifacts['branch'] + ':refs/heads/' + artifacts['branch'], cwd=repo)
            head = git_io.git('rev-parse', artifacts['branch'], cwd=repo)
            if head != artifacts['commit_sha']:
                raise ValueError('Result bundle commit does not match reviewed commit')
            git_io.git('merge-base', '--is-ancestor', artifacts['base_sha'], head, cwd=repo)
            with con:
                con.execute('UPDATE runs SET delivery_repo=? WHERE id=?', (str(repo), run_id))
            if package.get('delivery') == 'github' and artifacts.get('ready_to_merge'):
                owner_repo = git_io.github_repo(package['source']['repo_url'])
                if not owner_repo:
                    raise ValueError('Unsupported GitHub repository URL')
                if not artifacts.get('changed_files'):
                    raise ValueError('No changes to create a PR')
                branch = artifacts['branch']
                base = package['source']['base_branch']
                git_io.git('push', package['source']['repo_url'], 'refs/heads/' + branch + ':refs/heads/' + branch, cwd=repo)
                prs = json.loads(gh(['pr', 'list', '--repo', owner_repo, '--head', branch, '--base', base, '--state', 'open', '--json', 'number,url']))
                if prs:
                    pr = prs[0]
                else:
                    body = root / 'pr-body.md'
                    body.write_text('## Task\n\n' + package['requirement'] + '\n\n## Validation\n\n'
                        + artifacts['code_review']['summary'] + '\n\n' + artifacts['acceptance']['summary']
                        + '\n\n' + '\n'.join('- `%s`: exit %s' % (g['command'], g['exit_code']) for g in artifacts['gates']))
                    task = con.execute('SELECT title FROM tasks WHERE id=?', (run['task_id'],)).fetchone()
                    url = gh(['pr', 'create', '--repo', owner_repo, '--head', branch, '--base', base,
                              '--title', task['title'], '--body-file', str(body)])
                    pr = json.loads(gh(['pr', 'view', url, '--repo', owner_repo, '--json', 'number,url']))
                with con:
                    con.execute('UPDATE runs SET pr_url=?,pr_number=? WHERE id=?', (pr['url'], pr['number'], run_id))
            with con:
                con.execute("UPDATE runs SET delivery_status='ready',delivery_error=NULL WHERE id=?", (run_id,))
        except Exception as exc:
            with con:
                con.execute("UPDATE runs SET delivery_status='failed',delivery_error=? WHERE id=?", (str(exc), run_id))


PROTECTION_MARKERS = ('required status check', 'branch protection', 'protected branch',
                      'base branch policy', 'not mergeable', 'approving review',
                      'review required', 'code owner', 'merge blocked')


def merge_failure_kind(detail):
    lowered = detail.lower()
    if any(marker in lowered for marker in PROTECTION_MARKERS):
        return 'merge_protection'
    return 'merge_failed'


def review_delivery(manager, con, run, node, payload):
    from app import CodedError, runner_call
    if payload.get('decision') not in ('approve', 'reject') or run['status'] != 'REVIEW':
        raise ValueError('Run is not ready for review')
    with DELIVERY_LOCK:
        # Re-read after waiting for a concurrent publish.
        run = manager.row(con, 'runs', run['id'])
        artifacts = json.loads(run['artifacts'])
        if not artifacts.get('pipeline_version'):
            return
        package = json.loads(run['package'])
        owner_repo = git_io.github_repo(package['source']['repo_url'])
        if payload['decision'] == 'reject':
            if run['delivery_status'] == 'merged':
                raise ValueError('Result is already merged; retry approval to finish cleanup')
            if run['pr_number']:
                gh(['pr', 'close', str(run['pr_number']), '--repo', owner_repo])
            return
        if not artifacts.get('ready_to_merge'):
            raise ValueError('Code review, tests and acceptance must all pass')
        if run['delivery_status'] not in ('ready', 'merged'):
            raise ValueError('Result delivery is incomplete; retry delivery first')
        if package['delivery'] == 'local' and run['delivery_status'] != 'merged':
            state = runner_call(node, 'GET', '/runs/%s' % run['id'])
            if state.get('commit_sha') != artifacts['commit_sha']:
                raise ValueError('Runner result changed')
            merge_local_result(con, run, package, artifacts)
            con.execute("UPDATE runs SET delivery_status='merged',delivery_error=NULL,delivery_error_kind=NULL WHERE id=?", (run['id'],))
            con.commit()
        if package['delivery'] == 'github':
            if run['delivery_status'] != 'merged':
                if not run['pr_number']:
                    raise ValueError('PR has not been created')
                # Runner freezes its commit after review; verify it again before merge.
                state = runner_call(node, 'GET', '/runs/%s' % run['id'])
                if state.get('commit_sha') != artifacts['commit_sha']:
                    raise ValueError('Runner result changed')
                pr = json.loads(gh(['pr', 'view', str(run['pr_number']), '--repo', owner_repo,
                    '--json', 'state,headRefOid,baseRefName']))
                if pr['headRefOid'] != artifacts['commit_sha'] or pr['baseRefName'] != package['source']['base_branch']:
                    raise ValueError('PR head or base changed; review the new changes before merging')
                if pr['state'] != 'MERGED':
                    if pr['state'] != 'OPEN':
                        raise ValueError('PR is not open')
                    failure = None
                    try:
                        gh(['pr', 'merge', str(run['pr_number']), '--repo', owner_repo, '--squash',
                            '--match-head-commit', artifacts['commit_sha']])
                        result = json.loads(gh(['pr', 'view', str(run['pr_number']), '--repo', owner_repo, '--json', 'state']))
                        if result['state'] != 'MERGED':
                            failure = ValueError('PR was not merged; required checks or branch protection may be pending')
                    except ValueError as exc:
                        failure = exc
                        # The merge command failed, but it may still have taken effect.
                        try:
                            if json.loads(gh(['pr', 'view', str(run['pr_number']), '--repo', owner_repo,
                                    '--json', 'state']))['state'] == 'MERGED':
                                failure = None
                        except ValueError:
                            pass
                    if failure is not None:
                        kind = merge_failure_kind(str(failure))
                        con.execute("UPDATE runs SET delivery_error=?,delivery_error_kind=? WHERE id=?",
                                    (str(failure), kind, run['id']))
                        con.commit()
                        raise CodedError(kind, str(failure))
                con.execute("UPDATE runs SET delivery_status='merged',delivery_error=NULL,delivery_error_kind=NULL WHERE id=?", (run['id'],))
                con.commit()
            # The merge is confirmed; remove the system-created remote task branch.
            branch = artifacts.get('branch') or ''
            if branch.startswith('agent/task-'):
                try:
                    gh(['api', '-X', 'DELETE', 'repos/%s/git/refs/heads/%s' % (owner_repo, branch)])
                except ValueError as exc:
                    if 'Reference does not exist' not in str(exc):
                        con.execute("UPDATE runs SET delivery_error=?,delivery_error_kind=? WHERE id=?",
                                    (str(exc), 'branch_delete_failed', run['id']))
                        con.commit()
                        raise CodedError('branch_delete_failed',
                                         'Result is merged, but deleting the remote task branch failed; retry approval to finish cleanup')
                con.execute("UPDATE runs SET delivery_error=NULL,delivery_error_kind=NULL WHERE id=?", (run['id'],))
                con.commit()
