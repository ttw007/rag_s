from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommandSpec:
    name: str
    summary: str
    argument_hint: str | None = None
    resume_supported: bool = True


SLASH_COMMAND_SPECS: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec('help', 'Show available slash commands'),
    SlashCommandSpec('status', 'Show current session status'),
    SlashCommandSpec('compact', 'Compact local session history'),
    SlashCommandSpec('model', 'Show or switch the active model', '[model]', False),
    SlashCommandSpec('permissions', 'Show or switch the active permission mode', '[read-only|workspace-write|danger-full-access]', False),
    SlashCommandSpec('clear', 'Start a fresh local session', '[--confirm]'),
    SlashCommandSpec('cost', 'Show cumulative token usage for this session'),
    SlashCommandSpec('resume', 'Load a saved session into the REPL', '<session-path>', False),
    SlashCommandSpec('config', 'Inspect runtime config', '[env|model|session]'),
    SlashCommandSpec('memory', 'Inspect CLAUDE.md contents'),
    SlashCommandSpec('init', 'Create a starter CLAUDE.md for this repo'),
    SlashCommandSpec('diff', 'Show git diff for current workspace changes'),
    SlashCommandSpec('version', 'Show CLI version and build information'),
    SlashCommandSpec('bughunter', 'Inspect the workspace for likely bugs', '[scope]', False),
    SlashCommandSpec('commit', 'Generate a draft git commit summary', None, False),
    SlashCommandSpec('pr', 'Draft a pull request summary', '[context]', False),
    SlashCommandSpec('issue', 'Draft a GitHub issue summary', '[context]', False),
    SlashCommandSpec('ultraplan', 'Generate a multi-step execution plan', '[task]', False),
    SlashCommandSpec('teleport', 'Jump to a file by searching the workspace', '<symbol-or-path>', False),
    SlashCommandSpec('debug-tool-call', 'Show the last tool execution', None, False),
    SlashCommandSpec('export', 'Export the conversation to a file', '[file]'),
    SlashCommandSpec('session', 'List or switch managed local sessions', '[list|switch <session-id>]', False),
)


def parse_slash_command(text: str) -> tuple[str, str] | None:
    trimmed = text.strip()
    if not trimmed.startswith('/'):
        return None
    body = trimmed[1:]
    name, _, remainder = body.partition(' ')
    if not name:
        return None
    return name, remainder.strip()


def render_slash_command_help() -> str:
    lines = ['Slash commands', '']
    for spec in SLASH_COMMAND_SPECS:
        suffix = f' {spec.argument_hint}' if spec.argument_hint else ''
        lines.append(f'/{spec.name}{suffix}'.rstrip())
        lines.append(f'  {spec.summary}')
    return '\n'.join(lines)


def slash_command_names() -> set[str]:
    return {spec.name for spec in SLASH_COMMAND_SPECS}
