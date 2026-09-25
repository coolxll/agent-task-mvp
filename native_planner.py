"""Optional Manager-side planning agent. Execution remains deterministic."""
import json
import os
from pathlib import Path
import subprocess

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from pipeline import Plan, ordered_steps

PI_AGENT_CONFIG_DIR = Path.home() / '.pi' / 'agent'


def resolve_model(name):
    """Use Pi's existing OpenAI-compatible provider without copying its key."""
    if not isinstance(name, str) or not name.startswith('pi:'):
        return name
    try:
        provider_name, model_id = name[3:].split('/', 1)
        provider = json.loads((PI_AGENT_CONFIG_DIR / 'models.json').read_text())['providers'][provider_name]
        auth = json.loads((PI_AGENT_CONFIG_DIR / 'auth.json').read_text())[provider_name]
        if provider['api'] != 'openai-completions':
            raise ValueError('Pi provider is not OpenAI-compatible')
        if model_id not in {model['id'] for model in provider['models']}:
            raise ValueError('Model is not configured in Pi')
        return OpenAIChatModel(model_id, provider=OpenAIProvider(
            base_url=provider['baseUrl'], api_key=auth['key']))
    except (KeyError, OSError, ValueError) as exc:
        raise ValueError('Cannot resolve Pi model ' + name + ': ' + str(exc)) from exc


async def plan_task(requirement, project, node, model_name=None):
    model_name = model_name or os.environ.get('MANAGER_PLANNER_MODEL')
    if not model_name:
        raise ValueError('Manager Planner needs MANAGER_PLANNER_MODEL and model credentials')

    agent = Agent(resolve_model(model_name), output_type=Plan, system_prompt=(
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
