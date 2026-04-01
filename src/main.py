from __future__ import annotations

import argparse
from pathlib import Path

from .permissions import PermissionMode
from .runtime import ClawRuntime, DEFAULT_MODEL, VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='claw-python', description='Python port of the Claw Code compatibility CLI')
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--output-format', choices=('text', 'json'), default='text')
    parser.add_argument('--permission-mode', default='danger-full-access')
    parser.add_argument('--dangerously-skip-permissions', action='store_true')
    parser.add_argument('--allowedTools', action='append', default=[])
    parser.add_argument('--version', '-V', action='store_true')
    parser.add_argument('-p', dest='inline_prompt')
    parser.add_argument('--print', dest='print_mode', action='store_true')

    subparsers = parser.add_subparsers(dest='command')
    prompt_parser = subparsers.add_parser('prompt')
    prompt_parser.add_argument('text', nargs='+')

    resume_parser = subparsers.add_parser('resume')
    resume_parser.add_argument('session_ref')
    resume_parser.add_argument('commands', nargs='*')

    subparsers.add_parser('login')
    subparsers.add_parser('logout')
    subparsers.add_parser('init')
    subparsers.add_parser('doctor')
    subparsers.add_parser('self-update')
    return parser


def runtime_from_args(args: argparse.Namespace, session_ref: str | None = None) -> ClawRuntime:
    permission_mode = PermissionMode.DANGER_FULL_ACCESS if args.dangerously_skip_permissions else PermissionMode.parse(args.permission_mode)
    return ClawRuntime(cwd=Path.cwd(), model=args.model, permission_mode=permission_mode, session_ref=session_ref)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f'claw-python {VERSION}')
        return 0

    if args.inline_prompt:
        runtime = runtime_from_args(args)
        print(runtime.run_prompt(args.inline_prompt))
        return 0

    if args.command == 'prompt':
        runtime = runtime_from_args(args)
        print(runtime.run_prompt(' '.join(args.text)))
        return 0
    if args.command == 'resume':
        runtime = runtime_from_args(args, session_ref=args.session_ref)
        if args.commands:
            print(runtime.run_prompt(' '.join(args.commands)))
        else:
            print(runtime.state.session.summary())
        return 0
    if args.command == 'login':
        print('OAuth login flow is not implemented in the offline Python port yet')
        return 0
    if args.command == 'logout':
        print('OAuth logout flow is not implemented in the offline Python port yet')
        return 0
    if args.command == 'init':
        runtime = runtime_from_args(args)
        print(runtime.handle_slash_command('init', ''))
        return 0
    if args.command == 'doctor':
        print(ClawRuntime.doctor(Path.cwd()))
        return 0
    if args.command == 'self-update':
        print('self-update is not implemented in the Python port')
        return 0

    runtime = runtime_from_args(args)
    return runtime.repl()


if __name__ == '__main__':
    raise SystemExit(main())
