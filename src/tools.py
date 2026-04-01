from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .permissions import PermissionMode, PermissionPolicy


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    required_permission: PermissionMode


@dataclass
class ToolExecutionContext:
    cwd: Path
    permission_policy: PermissionPolicy


@dataclass(frozen=True)
class ToolExecutionResult:
    name: str
    handled: bool
    output: str


def mvp_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec('bash', 'Execute a shell command in the current workspace.', {'required': ['command']}, PermissionMode.DANGER_FULL_ACCESS),
        ToolSpec('read_file', 'Read a text file from the workspace.', {'required': ['path']}, PermissionMode.READ_ONLY),
        ToolSpec('write_file', 'Write a text file in the workspace.', {'required': ['path', 'content']}, PermissionMode.WORKSPACE_WRITE),
        ToolSpec('edit_file', 'Replace text in a workspace file.', {'required': ['path', 'old_string', 'new_string']}, PermissionMode.WORKSPACE_WRITE),
        ToolSpec('glob_search', 'Find files by glob pattern.', {'required': ['pattern']}, PermissionMode.READ_ONLY),
        ToolSpec('grep_search', 'Search file contents with a regex pattern.', {'required': ['pattern']}, PermissionMode.READ_ONLY),
        ToolSpec('WebFetch', 'Fetch a URL and summarize it.', {'required': ['url', 'prompt']}, PermissionMode.READ_ONLY),
        ToolSpec('WebSearch', 'Search the web for current information.', {'required': ['query']}, PermissionMode.READ_ONLY),
        ToolSpec('TodoWrite', 'Update the structured task list for the current session.', {'required': ['todos']}, PermissionMode.WORKSPACE_WRITE),
        ToolSpec('Skill', 'Load a local skill definition and its instructions.', {'required': ['skill']}, PermissionMode.READ_ONLY),
        ToolSpec('Agent', 'Launch a specialized agent task.', {'required': ['description', 'prompt']}, PermissionMode.DANGER_FULL_ACCESS),
        ToolSpec('ToolSearch', 'Search for supported tools by name or keyword.', {'required': ['query']}, PermissionMode.READ_ONLY),
        ToolSpec('NotebookEdit', 'Replace, insert, or delete a cell in a Jupyter notebook.', {'required': ['notebook_path']}, PermissionMode.WORKSPACE_WRITE),
        ToolSpec('Sleep', 'Wait for a specified duration.', {'required': ['duration_ms']}, PermissionMode.READ_ONLY),
        ToolSpec('SendUserMessage', 'Send a message to the user.', {'required': ['message', 'status']}, PermissionMode.READ_ONLY),
    )


def tool_specs_by_name() -> dict[str, ToolSpec]:
    return {spec.name: spec for spec in mvp_tool_specs()}


def tool_search(query: str, max_results: int = 10) -> list[ToolSpec]:
    needle = query.lower()
    ranked = [
        spec
        for spec in mvp_tool_specs()
        if needle in spec.name.lower() or needle in spec.description.lower()
    ]
    return ranked[:max_results]


def execute_tool(name: str, payload: str | dict[str, Any], context: ToolExecutionContext) -> ToolExecutionResult:
    spec = tool_specs_by_name().get(name)
    if spec is None:
        return ToolExecutionResult(name=name, handled=False, output=f'Unknown tool: {name}')
    payload_data = payload if isinstance(payload, dict) else json.loads(payload or '{}')
    decision = context.permission_policy.authorize(name, json.dumps(payload_data, ensure_ascii=True))
    if not decision.allowed:
        return ToolExecutionResult(name=name, handled=False, output=decision.reason)
    handlers = {
        'bash': _exec_bash,
        'read_file': _read_file,
        'write_file': _write_file,
        'edit_file': _edit_file,
        'glob_search': _glob_search,
        'grep_search': _grep_search,
        'TodoWrite': _todo_write,
        'Skill': _skill_read,
        'ToolSearch': _tool_search_exec,
        'Sleep': _sleep_exec,
        'SendUserMessage': _send_user_message,
        'WebFetch': _unsupported_network_tool,
        'WebSearch': _unsupported_network_tool,
        'Agent': _agent_stub,
        'NotebookEdit': _notebook_stub,
    }
    output = handlers[name](payload_data, context)
    return ToolExecutionResult(name=name, handled=True, output=output)


def _resolve_workspace_path(context: ToolExecutionContext, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = context.cwd / path
    return path.resolve()


def _exec_bash(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    completed = subprocess.run(
        payload['command'],
        cwd=context.cwd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=int(payload.get('timeout', 30)),
    )
    return '\n'.join(
        [
            f'exit_code={completed.returncode}',
            completed.stdout.rstrip(),
            completed.stderr.rstrip(),
        ]
    ).strip()


def _read_file(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    path = _resolve_workspace_path(context, payload['path'])
    lines = path.read_text(encoding='utf-8').splitlines()
    offset = int(payload.get('offset', 0))
    limit = int(payload.get('limit', max(1, len(lines) - offset or 1)))
    window = lines[offset : offset + limit]
    return '\n'.join(window)


def _write_file(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    path = _resolve_workspace_path(context, payload['path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload['content'], encoding='utf-8')
    return f'wrote {path}'


def _edit_file(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    path = _resolve_workspace_path(context, payload['path'])
    text = path.read_text(encoding='utf-8')
    old_string = payload['old_string']
    new_string = payload['new_string']
    replace_all = bool(payload.get('replace_all', False))
    if old_string not in text:
        return f'pattern not found in {path}'
    updated = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)
    path.write_text(updated, encoding='utf-8')
    return f'edited {path}'


def _glob_search(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    root = _resolve_workspace_path(context, payload.get('path', '.'))
    matches = sorted(path for path in root.glob(payload['pattern']))
    return '\n'.join(str(path.relative_to(context.cwd)) for path in matches[:200])


def _grep_search(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    pattern = re.compile(payload['pattern'], re.IGNORECASE if payload.get('-i') else 0)
    root = _resolve_workspace_path(context, payload.get('path', '.'))
    glob_pattern = payload.get('glob', '**/*')
    results: list[str] = []
    head_limit = int(payload.get('head_limit', 50))
    for path in root.glob(glob_pattern):
        if not path.is_file():
            continue
        try:
            for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
                if pattern.search(line):
                    results.append(f'{path.relative_to(context.cwd)}:{line_number}:{line}')
                    if len(results) >= head_limit:
                        return '\n'.join(results)
        except UnicodeDecodeError:
            continue
    return '\n'.join(results)


def _todo_write(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    path = context.cwd / '.claw' / 'todos.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload['todos'], indent=2), encoding='utf-8')
    return f'wrote {path}'


def _skill_read(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    skill = payload['skill']
    candidate_paths = [
        Path(skill),
        context.cwd / skill,
        Path.home() / '.codex' / 'skills' / skill / 'SKILL.md',
    ]
    for candidate in candidate_paths:
        if candidate.exists():
            return candidate.read_text(encoding='utf-8')
    return f'skill not found: {skill}'


def _tool_search_exec(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    del context
    matches = tool_search(payload['query'], int(payload.get('max_results', 10)))
    return '\n'.join(f'{spec.name}: {spec.description}' for spec in matches)


def _sleep_exec(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    del context
    duration_ms = max(0, min(int(payload['duration_ms']), 2000))
    time.sleep(duration_ms / 1000)
    return f'slept {duration_ms}ms'


def _send_user_message(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    del context
    return f"[{payload['status']}] {payload['message']}"


def _unsupported_network_tool(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    del payload, context
    return 'network-backed tool is not implemented in the offline Python port yet'


def _agent_stub(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    del context
    return f"queued agent task: {payload['description']}"


def _notebook_stub(payload: dict[str, Any], context: ToolExecutionContext) -> str:
    del context
    return f"NotebookEdit is not implemented yet for {payload['notebook_path']}"
