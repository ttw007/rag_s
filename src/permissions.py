from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PermissionMode(str, Enum):
    READ_ONLY = 'read-only'
    WORKSPACE_WRITE = 'workspace-write'
    DANGER_FULL_ACCESS = 'danger-full-access'
    PROMPT = 'prompt'
    ALLOW = 'allow'

    @classmethod
    def parse(cls, value: str) -> 'PermissionMode':
        normalized = value.strip().lower()
        aliases = {
            'default': cls.READ_ONLY,
            'plan': cls.READ_ONLY,
            'acceptedits': cls.WORKSPACE_WRITE,
            'auto': cls.WORKSPACE_WRITE,
            'dontask': cls.DANGER_FULL_ACCESS,
        }
        if normalized in aliases:
            return aliases[normalized]
        for mode in cls:
            if mode.value == normalized:
                return mode
        raise ValueError(f'unsupported permission mode: {value}')

    def rank(self) -> int:
        order = {
            PermissionMode.READ_ONLY: 0,
            PermissionMode.WORKSPACE_WRITE: 1,
            PermissionMode.DANGER_FULL_ACCESS: 2,
            PermissionMode.PROMPT: -1,
            PermissionMode.ALLOW: 99,
        }
        return order[self]


@dataclass(frozen=True)
class PermissionRequest:
    tool_name: str
    input_text: str
    current_mode: PermissionMode
    required_mode: PermissionMode


@dataclass(frozen=True)
class PermissionOutcome:
    allowed: bool
    reason: str = ''


class PermissionPrompter:
    def decide(self, request: PermissionRequest) -> PermissionOutcome:
        raise NotImplementedError


@dataclass(frozen=True)
class ToolPermissionContext:
    deny_names: frozenset[str] = field(default_factory=frozenset)
    deny_prefixes: tuple[str, ...] = ()

    @classmethod
    def from_iterables(
        cls,
        deny_names: list[str] | None = None,
        deny_prefixes: list[str] | None = None,
    ) -> 'ToolPermissionContext':
        return cls(
            deny_names=frozenset(name.lower() for name in (deny_names or [])),
            deny_prefixes=tuple(prefix.lower() for prefix in (deny_prefixes or [])),
        )

    def blocks(self, tool_name: str) -> bool:
        lowered = tool_name.lower()
        return lowered in self.deny_names or any(lowered.startswith(prefix) for prefix in self.deny_prefixes)


@dataclass
class PermissionPolicy:
    active_mode: PermissionMode
    tool_requirements: dict[str, PermissionMode] = field(default_factory=dict)

    def with_tool_requirement(self, tool_name: str, required_mode: PermissionMode) -> 'PermissionPolicy':
        self.tool_requirements[tool_name] = required_mode
        return self

    def required_mode_for(self, tool_name: str) -> PermissionMode:
        return self.tool_requirements.get(tool_name, PermissionMode.DANGER_FULL_ACCESS)

    def authorize(
        self,
        tool_name: str,
        input_text: str,
        prompter: PermissionPrompter | None = None,
    ) -> PermissionOutcome:
        current_mode = self.active_mode
        required_mode = self.required_mode_for(tool_name)
        if current_mode is PermissionMode.ALLOW or current_mode.rank() >= required_mode.rank():
            return PermissionOutcome(True)
        request = PermissionRequest(
            tool_name=tool_name,
            input_text=input_text,
            current_mode=current_mode,
            required_mode=required_mode,
        )
        if current_mode in {PermissionMode.PROMPT, PermissionMode.WORKSPACE_WRITE} and required_mode is PermissionMode.DANGER_FULL_ACCESS:
            if prompter is None:
                return PermissionOutcome(
                    False,
                    f"tool '{tool_name}' requires approval to escalate from {current_mode.value} to {required_mode.value}",
                )
            return prompter.decide(request)
        return PermissionOutcome(
            False,
            f"tool '{tool_name}' requires {required_mode.value} permission; current mode is {current_mode.value}",
        )
