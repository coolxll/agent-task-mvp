"""The Manager planner uses PydanticAI and validates executable plans."""
import asyncio
import json
import tempfile
from pathlib import Path
import subprocess
import unittest

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

import native_planner
from native_planner import plan_task
from unittest.mock import patch


class NativePlannerTests(unittest.TestCase):
    def test_pi_provider_config_is_reused_without_copying_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'models.json').write_text(json.dumps({'providers': {'test-pi': {
                'api': 'openai-completions', 'baseUrl': 'http://127.0.0.1:9999/v1',
                'models': [{'id': 'deepseek-flash'}]}}}))
            (root / 'auth.json').write_text(json.dumps({'test-pi': {'type': 'api_key', 'key': 'fixture-secret'}}))
            with patch.object(native_planner, 'PI_AGENT_CONFIG_DIR', root):
                model = native_planner.resolve_model('pi:test-pi/deepseek-flash')
                self.assertEqual(model.model_name, 'deepseek-flash')
                with self.assertRaisesRegex(ValueError, 'not configured'):
                    native_planner.resolve_model('pi:test-pi/missing')

    def test_typed_plan_with_repository_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
            (repo / 'calc.py').write_text('def add(a,b): return a-b\n')
            subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
            subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@local',
                            'commit', '-qm', 'fixture'], cwd=repo, check=True)
            seen = []

            def model(messages, info):
                seen.extend(tool.name for tool in info.function_tools)
                return ModelResponse(parts=[ToolCallPart(tool_name='final_result', args={
                    'summary': 'Fix add', 'steps': [{'id': 'fix', 'title': 'Fix add',
                    'instructions': 'Return a+b', 'depends_on': []}],
                    'acceptance_criteria': ['add(2,3)==5'], 'gates': ['python3 -m unittest']})])

            project = {'name': 'calc', 'local_path': str(repo), 'repo_url': '', 'gates': '[]'}
            result = asyncio.run(plan_task('Fix add', project, {'id': 1, 'name': 'x13'}, FunctionModel(model)))
            self.assertEqual(result['steps'][0]['id'], 'fix')
            self.assertIn('list_repository_files', seen)
            self.assertIn('read_repository_file', seen)

    def test_invalid_dependency_is_rejected(self):
        project = {'name': 'calc', 'local_path': '', 'repo_url': '', 'gates': '[]'}
        with self.assertRaisesRegex(ValueError, 'cycle'):
            asyncio.run(plan_task('Fix add', project, {'id': 1, 'name': 'x13'}, TestModel()))


if __name__ == '__main__':
    unittest.main()
