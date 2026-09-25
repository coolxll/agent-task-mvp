"""Optional Manager-side planning agent. Execution remains deterministic."""
import json
import os
from pathlib import Path
import subprocess

from pydantic_ai import Agent

from pipeline import Plan, ordered_steps


async def plan_task(requirement, project, node, model_name=None):
    model_name = model_name or os.environ.get('MANAGER_PLANNER_MODEL')
    if not model_name:
        raise ValueError('Manager Planner needs MANAGER_PLANNER_MODEL and model credentials')

    agent = Agent(model_name, output_type=Plan, system_prompt=(
        'You are the Manager-side development task planner. Produce 1–8 concrete, '
        'dependency-ordered implementation steps and acceptance criteria. '
        'The selected Node executes all steps in one Git worktree. '
        'Use repository inspection tools when available. Never claim a test passed. '
        'Do not execute, merge, push, or change files. Include executable Gate commands.'))
    repo = Path(project.get('local_path') or '')
    if project.get('local_path') and repo.is_dir():
        def git(*args):
            return subprocess.run(['git', *args], cwd=repo, check=True,
                                  capture_output=True, text=True, timeout=10).stdout

        @agent.tool_plain
        def list_repository_files() -> list[str]:
            """List tracked files in the selected project."""
            return git('ls-files').splitlines()[:300]

        @agent.tool_plain
        def read_repository_file(path: str) -> str:
            """Read one tracked file at HEAD (at most 16 KiB)."""
            if path not in set(list_repository_files()):
                raise ValueError('File is not tracked by this project')
            return git('show', 'HEAD:' + path)[:16_384]

    prompt = json.dumps({
        'requirement': requirement,
        'project': {'name': project['name'], 'repo_url': project.get('repo_url'),
                    'gates': json.loads(project['gates']) if isinstance(project['gates'], str) else project['gates']},
        'selected_node': {'id': node['id'], 'name': node['name']},
    }, ensure_ascii=False)
    result = await agent.run(prompt)
    plan = result.output.model_dump()
    ordered_steps(plan)
    return plan
