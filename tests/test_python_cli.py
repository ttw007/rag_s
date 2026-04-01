from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import os
from pathlib import Path

from src.permissions import PermissionMode, PermissionPolicy
from src.runtime import ClawRuntime
from src.tools import ToolExecutionContext, execute_tool


class PythonPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tempdir.name)
        self.repo_root = Path(__file__).resolve().parents[1]
        self.base_env = os.environ.copy()
        self.base_env['PYTHONPATH'] = str(self.repo_root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_prompt_creates_managed_session(self) -> None:
        runtime = ClawRuntime(cwd=self.cwd)
        output = runtime.run_prompt('inspect runtime parity')
        self.assertIn('Python compatibility runtime', output)
        self.assertTrue(runtime.state.session_path.exists())

    def test_slash_commands_update_runtime_state(self) -> None:
        runtime = ClawRuntime(cwd=self.cwd)
        self.assertEqual(runtime.run_prompt('/model sonnet'), 'model=sonnet')
        self.assertEqual(runtime.run_prompt('/permissions read-only'), 'permission_mode=read-only')
        status = runtime.run_prompt('/status')
        self.assertIn('Permission mode  read-only', status)

    def test_core_file_tools_execute(self) -> None:
        policy = PermissionPolicy(PermissionMode.DANGER_FULL_ACCESS)
        context = ToolExecutionContext(cwd=self.cwd, permission_policy=policy)
        write_result = execute_tool('write_file', {'path': 'sample.txt', 'content': 'hello\nworld'}, context)
        read_result = execute_tool('read_file', {'path': 'sample.txt'}, context)
        edit_result = execute_tool('edit_file', {'path': 'sample.txt', 'old_string': 'world', 'new_string': 'claw'}, context)
        grep_result = execute_tool('grep_search', {'pattern': 'claw', 'path': '.', 'glob': '*.txt'}, context)
        self.assertTrue(write_result.handled)
        self.assertEqual(read_result.output, 'hello\nworld')
        self.assertIn('edited', edit_result.output)
        self.assertIn('sample.txt:2:claw', grep_result.output)

    def test_permission_policy_blocks_write_in_read_only(self) -> None:
        policy = PermissionPolicy(PermissionMode.READ_ONLY).with_tool_requirement('write_file', PermissionMode.WORKSPACE_WRITE)
        context = ToolExecutionContext(cwd=self.cwd, permission_policy=policy)
        result = execute_tool('write_file', {'path': 'blocked.txt', 'content': 'x'}, context)
        self.assertFalse(result.handled)
        self.assertIn('workspace-write permission', result.output)

    def test_resume_command_loads_existing_session(self) -> None:
        runtime = ClawRuntime(cwd=self.cwd)
        runtime.run_prompt('first turn')
        resumed = ClawRuntime(cwd=self.cwd, session_ref=str(runtime.state.session_path))
        status = resumed.run_prompt('/status')
        self.assertIn(runtime.state.session.id, status)

    def test_cli_prompt_and_resume_work(self) -> None:
        prompt_result = subprocess.run(
            [sys.executable, '-m', 'src.main', 'prompt', 'review', 'workspace'],
            cwd=self.cwd,
            check=True,
            capture_output=True,
            text=True,
            env=self.base_env,
        )
        self.assertIn('Python compatibility runtime', prompt_result.stdout)

        session_files = list((self.cwd / '.claw' / 'sessions').glob('*.json'))
        self.assertTrue(session_files)

        resume_result = subprocess.run(
            [sys.executable, '-m', 'src.main', 'resume', str(session_files[0])],
            cwd=self.cwd,
            check=True,
            capture_output=True,
            text=True,
            env=self.base_env,
        )
        self.assertIn('Session', resume_result.stdout)

    def test_tool_invocation_via_prompt(self) -> None:
        runtime = ClawRuntime(cwd=self.cwd)
        runtime.run_prompt("tool write_file {\"path\":\"todo.json\",\"content\":\"{}\"}")
        result = runtime.run_prompt("tool read_file {\"path\":\"todo.json\"}")
        self.assertEqual(result, '{}')

    def test_doctor_and_init_commands(self) -> None:
        doctor = subprocess.run(
            [sys.executable, '-m', 'src.main', 'doctor'],
            cwd=self.cwd,
            check=True,
            capture_output=True,
            text=True,
            env=self.base_env,
        )
        init = subprocess.run(
            [sys.executable, '-m', 'src.main', 'init'],
            cwd=self.cwd,
            check=True,
            capture_output=True,
            text=True,
            env=self.base_env,
        )
        self.assertIn('anthropic_api_key=', doctor.stdout)
        self.assertIn('initialized', init.stdout)
        self.assertTrue((self.cwd / 'CLAUDE.md').exists())

    def test_export_and_session_listing(self) -> None:
        runtime = ClawRuntime(cwd=self.cwd)
        runtime.run_prompt('review session export')
        export_result = runtime.run_prompt('/export transcript.md')
        listing = runtime.run_prompt('/session list')
        self.assertIn('exported', export_result)
        self.assertTrue((self.cwd / 'transcript.md').exists())
        self.assertIn('.json', listing)


if __name__ == '__main__':
    unittest.main()
