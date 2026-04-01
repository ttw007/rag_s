from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .commands import parse_slash_command, render_slash_command_help
from .permissions import PermissionMode, PermissionPolicy
from .session_store import Session, create_managed_session, list_sessions, load_session, managed_session_dir
from .tools import ToolExecutionContext, execute_tool, mvp_tool_specs, tool_search


VERSION = '0.1.0-python'
DEFAULT_MODEL = 'claude-opus-4-6'


@dataclass
class RuntimeState:
    cwd: Path
    model: str
    permission_mode: PermissionMode
    session: Session
    session_path: Path
    last_tool_output: str = ''


class ClawRuntime:
    def __init__(
        self,
        cwd: Path,
        model: str = DEFAULT_MODEL,
        permission_mode: PermissionMode = PermissionMode.DANGER_FULL_ACCESS,
        session_ref: str | None = None,
    ) -> None:
        if session_ref:
            session, session_path = load_session(session_ref, cwd)
            model = session.model
            permission_mode = PermissionMode.parse(session.permission_mode)
        else:
            session, session_path = create_managed_session(model=model, permission_mode=permission_mode.value, base_dir=cwd)
        self.state = RuntimeState(
            cwd=cwd,
            model=model,
            permission_mode=permission_mode,
            session=session,
            session_path=session_path,
        )

    def permission_policy(self) -> PermissionPolicy:
        policy = PermissionPolicy(self.state.permission_mode)
        for spec in mvp_tool_specs():
            policy.with_tool_requirement(spec.name, spec.required_permission)
        return policy

    def run_prompt(self, prompt: str) -> str:
        if command := parse_slash_command(prompt):
            response = self.handle_slash_command(*command)
        else:
            response = self._generate_response(prompt)
        self.state.session.model = self.state.model
        self.state.session.permission_mode = self.state.permission_mode.value
        self.state.session.add_exchange(prompt, response)
        self.state.session.save_to_path(self.state.session_path)
        return response

    def _generate_response(self, prompt: str) -> str:
        lowered = prompt.lower()
        if lowered.startswith('tool '):
            _, _, remainder = prompt.partition(' ')
            name, _, payload = remainder.partition(' ')
            result = execute_tool(
                name,
                payload or '{}',
                ToolExecutionContext(cwd=self.state.cwd, permission_policy=self.permission_policy()),
            )
            self.state.last_tool_output = result.output
            return result.output
        matches = tool_search(prompt, max_results=5)
        lines = [
            'Python compatibility runtime',
            f'cwd={self.state.cwd}',
            f'model={self.state.model}',
            f'permission_mode={self.state.permission_mode.value}',
            f'session={self.state.session.id}',
        ]
        if matches:
            lines.append('suggested_tools=' + ', '.join(spec.name for spec in matches))
            lines.append("invoke with: tool <name> '{\"key\":\"value\"}'")
        else:
            lines.append('suggested_tools=none')
        return '\n'.join(lines)

    def handle_slash_command(self, name: str, arg: str) -> str:
        if name == 'help':
            return render_slash_command_help()
        if name == 'status':
            return self.state.session.summary() + f'\n  Session file     {self.state.session_path}'
        if name == 'cost':
            usage = self.state.session.usage
            return f'input_tokens={usage.input_tokens}\noutput_tokens={usage.output_tokens}'
        if name == 'model':
            if arg:
                self.state.model = arg
                return f'model={self.state.model}'
            return self.state.model
        if name == 'permissions':
            if arg:
                self.state.permission_mode = PermissionMode.parse(arg)
                return f'permission_mode={self.state.permission_mode.value}'
            return self.state.permission_mode.value
        if name == 'compact':
            if len(self.state.session.messages) > 6:
                self.state.session.messages = self.state.session.messages[-6:]
            return f'compacted_messages={len(self.state.session.messages)}'
        if name == 'clear':
            session, path = create_managed_session(self.state.model, self.state.permission_mode.value, self.state.cwd)
            self.state.session = session
            self.state.session_path = path
            return f'Session cleared\n  Session          {self.state.session.id}'
        if name == 'config':
            section = arg or 'all'
            env = f"ANTHROPIC_API_KEY={'set' if os.getenv('ANTHROPIC_API_KEY') else 'unset'}"
            return f'section={section}\nmodel={self.state.model}\npermission_mode={self.state.permission_mode.value}\n{env}'
        if name == 'memory':
            memory_path = self.state.cwd / 'CLAUDE.md'
            if not memory_path.exists():
                return 'CLAUDE.md not found'
            return memory_path.read_text(encoding='utf-8')
        if name == 'init':
            target = self.state.cwd / 'CLAUDE.md'
            if not target.exists():
                target.write_text('# CLAUDE.md\n\nProject instructions go here.\n', encoding='utf-8')
            return f'initialized {target}'
        if name == 'diff':
            result = subprocess.run(['git', 'diff', '--', '.'], cwd=self.state.cwd, capture_output=True, text=True, check=False)
            return result.stdout.strip() or 'no diff'
        if name == 'version':
            return f'claw-python {VERSION}'
        if name == 'export':
            target = Path(arg) if arg else self.state.cwd / f'claw-export-{self.state.session.id}.md'
            if not target.is_absolute():
                target = self.state.cwd / target
            lines = []
            for message in self.state.session.messages:
                lines.append(f'## {message.role}')
                lines.append(message.text_content())
                lines.append('')
            target.write_text('\n'.join(lines), encoding='utf-8')
            return f'exported {target}'
        if name == 'session':
            if not arg or arg == 'list':
                sessions = list_sessions(self.state.cwd)
                if not sessions:
                    return 'no sessions'
                return '\n'.join(f'{session_id}\t{path}' for session_id, path in sessions)
            if arg.startswith('switch '):
                target = arg.split(' ', 1)[1].strip()
                session, path = load_session(target, self.state.cwd)
                self.state.session = session
                self.state.session_path = path
                self.state.model = session.model
                self.state.permission_mode = PermissionMode.parse(session.permission_mode)
                return f'Session switched\n  Active session   {session.id}\n  File             {path}'
            return 'usage: /session [list|switch <session-id>]'
        if name == 'resume':
            if not arg:
                return 'usage: /resume <session-path>'
            session, path = load_session(arg, self.state.cwd)
            self.state.session = session
            self.state.session_path = path
            return f'Session resumed\n  Session file     {path}'
        if name == 'teleport':
            target = arg or ''
            matches = sorted(self.state.cwd.rglob(f'*{target}*'))
            return '\n'.join(str(path.relative_to(self.state.cwd)) for path in matches[:25]) or 'no matches'
        if name == 'debug-tool-call':
            return self.state.last_tool_output or 'no tool call recorded'
        if name == 'ultraplan':
            task = arg or 'current task'
            return f'1. Inspect workspace for {task}\n2. Implement the smallest correct change\n3. Verify with tests and CLI smoke checks'
        if name == 'bughunter':
            scope = arg or '.'
            return f'bughunter scope={scope}\n- Review tests\n- Search for TODO/FIXME\n- Check unsafe shell/file operations'
        if name == 'commit':
            return 'Draft commit message:\nfeat: port claw runtime to executable Python CLI'
        if name == 'pr':
            context = arg or 'Python runtime port'
            return f'PR draft:\nTitle: feat: Python port for claw runtime\nBody: Implements executable Python compatibility harness.\nContext: {context}'
        if name == 'issue':
            context = arg or 'Follow-up parity work'
            return f'Issue draft:\nTitle: Track remaining parity gaps in Python port\nBody: {context}'
        return f'unknown slash command: /{name}'

    def repl(self) -> int:
        while True:
            try:
                line = input('claw> ').strip()
            except EOFError:
                return 0
            if line in {'exit', 'quit'}:
                return 0
            if not line:
                continue
            print(self.run_prompt(line))

    @staticmethod
    def doctor(cwd: Path) -> str:
        checks = [
            f'cwd={cwd}',
            f'git={"yes" if (cwd / ".git").exists() else "no"}',
            f'claude_md={"yes" if (cwd / "CLAUDE.md").exists() else "no"}',
            f'anthropic_api_key={"set" if os.getenv("ANTHROPIC_API_KEY") else "unset"}',
            f'session_dir={managed_session_dir(cwd)}',
        ]
        return '\n'.join(checks)
