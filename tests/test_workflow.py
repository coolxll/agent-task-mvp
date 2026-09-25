import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app
import control
import git_io
import pipeline

FAKE_CODEX = '''#!/usr/bin/env python3
import json,sys,time
from pathlib import Path
prompt=sys.stdin.read()
output=Path(sys.argv[sys.argv.index('--output-last-message')+1])
name=output.name
if 'PLANNING'.lower() in name:
    if 'ASK_USER' in prompt and 'The user answered your question:' not in prompt:
        output.write_text('NEEDS_INPUT: Which Python version should the change support?')
        print(json.dumps({'type':'thread.started','thread_id':'fixture-session'}))
        sys.exit(0)
    value={'summary':'Fix addition and cover it', 'steps':[
      {'id':'fix','title':'Fix addition','instructions':'Fix add','depends_on':[]},
      {'id':'test','title':'Cover addition','instructions':'Add test','depends_on':['fix']}],
      'acceptance_criteria':['Addition returns a sum'],
      'gates':['python3 -c "exit(1)"'] if 'FAIL_GATE' in prompt else ['python3 -m unittest -v']}
elif 'implementing' in name:
    if 'ASK_USER' in prompt and 'Previously answered questions' not in prompt:
        output.write_text('NEEDS_INPUT: Which Python version should the change support?')
        print(json.dumps({'type':'thread.started','thread_id':'fixture-session'}))
        sys.exit(0)
    if 'SLOW' in prompt: time.sleep(60)
    Path('calculator.py').write_text('def add(a, b):\\n    return a + b\\n')
    Path('test_calculator.py').write_text('import unittest\\nfrom calculator import add\\nclass TestAdd(unittest.TestCase):\\n    def test_add(self): self.assertEqual(add(2, 3), 5)\\n')
    value='Fixed addition and added test'
elif 'code_review' in name:
    value={'passed':True,'summary':'Checked diff','findings':[]}
else:
    value={'passed':'FAIL_GATE' not in prompt,'summary':'Checked implementation and tests',
      'criteria':[{'criterion':'Addition returns sum','passed':True,'evidence':'test_add passed'}]}
output.write_text(json.dumps(value) if isinstance(value,dict) else value)
print(json.dumps({'type':'thread.started','thread_id':'fixture-session'}))
'''


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.repo = cls.root / 'source'
        cls.repo.mkdir()
        git_io.git('init', '-b', 'main', cwd=cls.repo)
        (cls.repo / 'calculator.py').write_text('def add(a, b):\n    return a - b\n')
        (cls.repo / '.gitignore').write_text('__pycache__/\n')
        git_io.git('add', '.', cwd=cls.repo)
        git_io.git('-c','user.name=Test','-c','user.email=test@local','commit','-m','fixture',cwd=cls.repo)
        cls.base = git_io.git('rev-parse','HEAD',cwd=cls.repo)
        bindir = cls.root / 'bin'; bindir.mkdir()
        codex = bindir / 'codex'; codex.write_text(FAKE_CODEX); codex.chmod(0o755)
        env = {**os.environ, 'PATH': str(bindir) + os.pathsep + os.environ['PATH']}
        cls.runner_port, cls.manager_port = port(), port()
        cls.logs = (cls.root / 'service.log').open('w')
        cls.db = cls.root / 'manager.sqlite3'
        cls.processes = [subprocess.Popen([sys.executable,str(ROOT/'app.py'),'runner','--root',str(cls.root/'runner'),
            '--token','test-secret','--port',str(cls.runner_port)],env=env,stdout=cls.logs,stderr=cls.logs),
            subprocess.Popen([sys.executable,str(ROOT/'app.py'),'manager','--db',str(cls.db),'--port',str(cls.manager_port)],
            env=env,stdout=cls.logs,stderr=cls.logs)]
        for _ in range(60):
            try:
                cls.api('/projects'); break
            except Exception: time.sleep(.1)
        else: raise AssertionError('Manager failed to start')
        cls.node = cls.api('/nodes', {'name':'fixture','endpoint':'http://127.0.0.1:'+str(cls.runner_port),'token':'test-secret'})['id']
        cls.project = cls.api('/projects/import', {'path':str(cls.repo)})['id']

    @classmethod
    def tearDownClass(cls):
        for process in cls.processes:
            process.terminate(); process.wait(timeout=10)
        cls.logs.close(); cls.tmp.cleanup()

    @classmethod
    def api(cls, path, payload=None):
        request = urllib.request.Request('http://127.0.0.1:%s/api%s' % (cls.manager_port,path),
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response: return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ValueError(exc.read().decode()) from exc

    def wait(self, run_id, predicate):
        for _ in range(150):
            run=self.api('/runs/'+str(run_id))
            if predicate(run): return run
            time.sleep(.1)
        self.fail('Run did not finish: '+json.dumps(run)+'\n'+(self.root/'service.log').read_text())

    def submit(self, requirement):
        return self.api('/submit', {'project_id':self.project,'node_id':self.node,
                                    'agent_kind':'codex','requirement':requirement})['id']

    def test_01_complete_workflow_and_result_import(self):
        run_id=self.submit('Fix addition and test it')
        run=self.wait(run_id, lambda r:r['status']=='FAILED' or r['delivery_status'] in ('ready','failed'))
        self.__class__.completed_run = run
        self.assertEqual(run['status'],'REVIEW',run)
        self.assertEqual(run['agent_kind'],'codex')
        self.assertEqual(self.api('/runs/%s/package'%run_id)['agent_kind'],'codex')
        self.assertEqual(run['delivery_status'],'ready',run)
        art=run['artifacts']
        self.assertTrue(art['ready_to_merge'])
        self.assertEqual(len(art['steps']),2)
        self.assertEqual([x['name'] for x in art['stages']],['PLANNING','IMPLEMENTING_1','IMPLEMENTING_2','CODE_REVIEW','ACCEPTANCE'])
        self.assertEqual(self.api('/runs/%s/package'%run_id)['source']['commit'],self.base)
        self.assertIn('return a + b',git_io.git('show',art['commit_sha']+':calculator.py',cwd=run['delivery_repo']))
        self.assertEqual(git_io.git('rev-parse','HEAD',cwd=self.repo),self.base)
        self.assertEqual(git_io.git('status','--porcelain',cwd=self.repo),'')
        result=self.api('/runs/%s/review'%run_id,{'decision':'approve'})
        self.assertEqual(result['status'],'SUCCEEDED')
        self.assertFalse(Path(run['workspace']).exists())
        self.assertTrue(Path(run['delivery_repo']).exists())

    def test_02_failed_gate_blocks_approval_but_keeps_results(self):
        run_id=self.submit('Fix addition FAIL_GATE')
        run=self.wait(run_id, lambda r:r['status']=='FAILED' or r['delivery_status'] in ('ready','failed'))
        self.assertEqual(run['status'],'REVIEW',run)
        self.assertFalse(run['artifacts']['ready_to_merge'])
        with self.assertRaisesRegex(ValueError,'must all pass'):
            self.api('/runs/%s/review'%run_id,{'decision':'approve'})
        result=self.api('/runs/%s/review'%run_id,{'decision':'reject'})
        self.assertEqual(result['status'],'REJECTED')
        self.assertFalse(Path(run['workspace']).exists())

    def test_02a_agent_question_answer_resumes_same_run(self):
        run_id=self.submit('Fix addition ASK_USER')
        waiting=self.wait(run_id,lambda r:r['status'] in ('NEEDS_INPUT','FAILED'))
        self.assertEqual(waiting['status'],'NEEDS_INPUT',waiting)
        self.assertIn('Python version',waiting['question'])
        self.assertEqual(waiting['agent_session_id'],'fixture-session')
        answer=self.api('/runs/%s/answer'%run_id,{'answer':'Python 3.11 and newer'})
        self.assertEqual(answer['status'],'RUNNING')
        finished=self.wait(run_id,lambda r:r['status']=='FAILED' or r['delivery_status'] in ('ready','failed'))
        self.assertEqual(finished['status'],'REVIEW',finished)
        self.assertEqual(finished['delivery_status'],'ready',finished)
        self.assertEqual([x['name'] for x in finished['artifacts']['stages']].count('PLANNING'),1)
        self.assertEqual(finished['artifacts']['stages'][0]['answer'],'Python 3.11 and newer')
        self.assertFalse(any(x['status']=='NEEDS_INPUT' for x in finished['artifacts']['stages']))
        self.api('/runs/%s/review'%run_id,{'decision':'reject'})

    def test_02b_waiting_question_can_be_cancelled(self):
        run_id=self.submit('Fix addition ASK_USER')
        waiting=self.wait(run_id,lambda r:r['status']=='NEEDS_INPUT')
        self.assertTrue(Path(waiting['workspace']).exists())
        self.api('/runs/%s/cancel'%run_id,{})
        cleaned=self.api('/runs/%s/cleanup'%run_id,{})
        self.assertEqual(cleaned['status'],'CANCELLED')
        self.assertFalse(Path(waiting['workspace']).exists())

    def test_03_dirty_directory_is_not_silently_ignored(self):
        file=self.repo/'uncommitted.txt'; file.write_text('keep me')
        try:
            with self.assertRaises(ValueError): self.submit('No silent omissions')
            self.assertEqual(file.read_text(),'keep me')
        finally: file.unlink()

    def test_03a_only_registered_agent_kinds_are_accepted(self):
        self.assertEqual(self.api('/agents'), ['antigravity', 'claude', 'codex'])
        with self.assertRaisesRegex(ValueError,'unsupported agent kind'):
            self.api('/submit',{'project_id':self.project,'node_id':self.node,
                                'agent_kind':'unknown','requirement':'Fix addition'})

    def test_04_cancel_stops_agent_and_allows_cleanup(self):
        run_id=self.submit('Fix addition SLOW')
        self.wait(run_id,lambda r:r.get('stage')=='IMPLEMENTING_1')
        self.api('/runs/%s/cancel'%run_id,{})
        for _ in range(30):
            try: result=self.api('/runs/%s/cleanup'%run_id,{}); break
            except ValueError: time.sleep(.1)
        else: self.fail('Cancelled worker did not stop')
        self.assertEqual(result['status'],'CANCELLED')
        self.assertFalse(Path(result['workspace']).exists())

    def test_05_source_bundle_validation(self):
        value={'data':base64.b64encode(b'bad').decode(),'sha256':'wrong'}
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            git_io.decode_bundle(value,self.root/'bad.bundle')

    def test_06_dependency_validation(self):
        with self.assertRaisesRegex(ValueError,'cycle'):
            pipeline.ordered_steps({'steps':[{'id':'a','depends_on':['b']},{'id':'b','depends_on':['a']}],'gates':['true']})

    def test_07_pr_merge_is_pinned_and_requires_merged_state(self):
        # Exercise Manager's real approval adapter with a fixture remote API.
        art={'pipeline_version':1,'ready_to_merge':True,'commit_sha':'a'*40}
        package={'source':{'repo_url':'https://github.com/owner/repo.git','base_branch':'main'},'delivery':'github'}
        con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
        con.executescript(app.SCHEMA);control.migrate(con)
        con.execute("INSERT INTO runs(id,task_id,node_id,agent_kind,status,created_at,updated_at,artifacts,package,delivery_status,pr_number) VALUES(1,1,1,'codex','REVIEW','','',?,?,'ready',42)", (json.dumps(art),json.dumps(package)))
        manager=object.__new__(app.Manager)
        run=manager.row(con,'runs',1)
        calls=[]
        def fake_gh(args,cwd=None):
            calls.append(args)
            if args[:2]==['pr','merge']: return ''
            if 'headRefOid,baseRefName' in args[-1]:
                return json.dumps({'state':'OPEN','headRefOid':'a'*40,'baseRefName':'main'})
            return json.dumps({'state':'MERGED'})
        with patch('control.gh',side_effect=fake_gh),patch('app.runner_call',return_value={'commit_sha':'a'*40}):
            control.review_delivery(manager,con,run,{}, {'decision':'approve'})
        self.assertEqual(manager.row(con,'runs',1)['delivery_status'],'merged')
        self.assertIn(['pr','merge','42','--repo','owner/repo','--squash','--match-head-commit','a'*40],calls)
        con.close()

    def test_07a_publish_pushes_exact_commit_and_creates_pr(self):
        successful = self.completed_run
        art = successful['artifacts']
        branch = art['branch']
        upstream = self.root / 'github-fixture.git'
        git_io.command(['git','init','--bare',str(upstream)])
        con = sqlite3.connect(':memory:'); con.row_factory=sqlite3.Row
        con.executescript(app.SCHEMA); control.migrate(con)
        con.execute("INSERT INTO tasks(id,project_id,title,description,acceptance_criteria,status,created_at,updated_at) VALUES(1,1,'Fix addition','','','REVIEW','','')")
        package = {'source':{'repo_url':'https://github.com/owner/repo.git','base_branch':'main'},'delivery':'github', 'requirement':'Fix addition'}
        con.execute("INSERT INTO runs(id,task_id,node_id,agent_kind,status,created_at,updated_at,artifacts,package,delivery_status) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (successful['id'],1,1,'codex','REVIEW','','',json.dumps(art),json.dumps(package),'pending'))
        real_git = git_io.git
        def local_push(*args,cwd):
            if args[0] == 'push':
                return real_git('push',str(upstream),*args[2:],cwd=cwd)
            return real_git(*args,cwd=cwd)
        calls=[]
        def fake_gh(args,cwd=None):
            calls.append(args)
            if args[:2]==['pr','list']: return '[]'
            if args[:2]==['pr','create']: return 'https://github.com/owner/repo/pull/101'
            if args[:2]==['pr','view']: return json.dumps({'number':101,'url':'https://github.com/owner/repo/pull/101'})
            raise AssertionError(args)
        node={'endpoint':'http://127.0.0.1:'+str(self.runner_port),'token':'test-secret'}
        with patch('control.gh',side_effect=fake_gh), patch('git_io.git',side_effect=local_push):
            control.publish(con,self.root/'pr-delivery.sqlite3',successful['id'],node)
        run=dict(con.execute('SELECT * FROM runs WHERE id=?',(successful['id'],)).fetchone())
        self.assertEqual(run['delivery_status'],'ready',run.get('delivery_error'))
        self.assertEqual(run['pr_number'],101)
        self.assertEqual(real_git('rev-parse','refs/heads/'+branch,cwd=upstream),art['commit_sha'])
        self.assertTrue(any(x[:2]==['pr','create'] for x in calls))
        con.close()

    def test_08_pr_head_change_blocks_merge(self):
        con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row
        con.executescript(app.SCHEMA);control.migrate(con)
        art={'pipeline_version':1,'ready_to_merge':True,'commit_sha':'a'*40}
        pkg={'source':{'repo_url':'https://github.com/owner/repo','base_branch':'main'},'delivery':'github'}
        con.execute("INSERT INTO runs(id,task_id,node_id,agent_kind,status,created_at,updated_at,artifacts,package,delivery_status,pr_number) VALUES(1,1,1,'codex','REVIEW','','',?,?,'ready',42)",(json.dumps(art),json.dumps(pkg)))
        manager=object.__new__(app.Manager);run=manager.row(con,'runs',1)
        with patch('control.gh',return_value=json.dumps({'state':'OPEN','headRefOid':'b'*40,'baseRefName':'main'})) as gh,patch('app.runner_call',return_value={'commit_sha':'a'*40}):
            with self.assertRaisesRegex(ValueError,'head or base changed'):
                control.review_delivery(manager,con,run,{}, {'decision':'approve'})
            self.assertEqual(gh.call_count,1)
        con.close()


if __name__=='__main__': unittest.main()
