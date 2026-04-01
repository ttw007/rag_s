from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


MANAGED_SESSION_DIR = Path('.claw') / 'sessions'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, prompt: str, output: str) -> 'TokenUsage':
        return TokenUsage(
            input_tokens=self.input_tokens + len(prompt.split()),
            output_tokens=self.output_tokens + len(output.split()),
        )


@dataclass(frozen=True)
class ContentBlock:
    type: str
    text: str


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    blocks: tuple[ContentBlock, ...]
    created_at: str

    @classmethod
    def text(cls, role: str, text: str) -> 'ConversationMessage':
        return cls(role=role, blocks=(ContentBlock(type='text', text=text),), created_at=utc_now())

    def text_content(self) -> str:
        return '\n'.join(block.text for block in self.blocks)


@dataclass
class Session:
    version: int = 1
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    model: str = 'claude-opus-4-6'
    permission_mode: str = 'danger-full-access'
    messages: list[ConversationMessage] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)

    def add_exchange(self, prompt: str, output: str) -> None:
        self.messages.append(ConversationMessage.text('user', prompt))
        self.messages.append(ConversationMessage.text('assistant', output))
        self.usage = self.usage.add(prompt, output)
        self.updated_at = utc_now()

    def save_to_path(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding='utf-8')
        return path

    @classmethod
    def load_from_path(cls, path: Path) -> 'Session':
        data = json.loads(path.read_text(encoding='utf-8'))
        return cls(
            version=data['version'],
            id=data['id'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
            model=data['model'],
            permission_mode=data['permission_mode'],
            messages=[
                ConversationMessage(
                    role=message['role'],
                    blocks=tuple(ContentBlock(**block) for block in message['blocks']),
                    created_at=message['created_at'],
                )
                for message in data['messages']
            ],
            usage=TokenUsage(**data['usage']),
        )

    def summary(self) -> str:
        return (
            f'Session {self.id}\n'
            f'  Model            {self.model}\n'
            f'  Permission mode  {self.permission_mode}\n'
            f'  Messages         {len(self.messages)}\n'
            f'  Input tokens     {self.usage.input_tokens}\n'
            f'  Output tokens    {self.usage.output_tokens}'
        )


def managed_session_dir(base_dir: Path | None = None) -> Path:
    return (base_dir or Path.cwd()) / MANAGED_SESSION_DIR


def managed_session_path(session_id: str, base_dir: Path | None = None) -> Path:
    return managed_session_dir(base_dir) / f'{session_id}.json'


def create_managed_session(model: str, permission_mode: str, base_dir: Path | None = None) -> tuple[Session, Path]:
    session = Session(model=model, permission_mode=permission_mode)
    path = managed_session_path(session.id, base_dir)
    session.save_to_path(path)
    return session, path


def load_session(reference: str, base_dir: Path | None = None) -> tuple[Session, Path]:
    candidate = Path(reference)
    if candidate.exists():
        return Session.load_from_path(candidate), candidate
    path = managed_session_path(reference, base_dir)
    return Session.load_from_path(path), path


def list_sessions(base_dir: Path | None = None) -> list[tuple[str, Path]]:
    directory = managed_session_dir(base_dir)
    if not directory.exists():
        return []
    return sorted(
        ((path.stem, path) for path in directory.glob('*.json')),
        key=lambda item: item[1].stat().st_mtime,
        reverse=True,
    )
