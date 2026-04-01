# rag_S

The current Python implementation focuses on the core local harness behaviors:

- CLI entrypoints for `prompt`, `resume`, `init`, `doctor`, and interactive REPL mode
- slash commands such as `/help`, `/status`, `/model`, `/permissions`, `/compact`, `/export`, and `/session`
- local tool execution for `bash`, `read_file`, `write_file`, `edit_file`, `glob_search`, and `grep_search`
- local session persistence under `.claw/sessions`
- permission-mode enforcement for `read-only`, `workspace-write`, and `danger-full-access`

## Quickstart

```bash
python -m src.main --version
python -m src.main prompt "review this workspace"
python -m src.main init
python -m unittest discover -s tests -v
```

## Tool Invocation

The runtime supports direct tool-style prompts:

```bash
python -m src.main prompt "tool write_file {\"path\":\"notes.txt\",\"content\":\"hello\"}"
python -m src.main prompt "tool read_file {\"path\":\"notes.txt\"}"
```

## Sessions

Each runtime instance writes session state to `.claw/sessions/<id>.json`.

```bash
python -m src.main resume <session-path>
```

Inside REPL mode:

```text
/status
/session list
/session switch <session-id>
/export transcript.md
```

## Status

This is not yet a full network-capable replacement for every upstream runtime feature. Network-backed tools such as web search/fetch and OAuth flows are still stubbed in the offline Python port.
