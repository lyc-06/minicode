from __future__ import annotations

import dataclasses
import datetime
import uuid
from typing import Any, Literal


MessageRole = Literal[
    'system', 'user', 'assistant', 'assistant_thinking',
    'assistant_progress', 'assistant_tool_call', 'tool_result',
    'context_summary', 'snip_boundary',
]


@dataclasses.dataclass
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    source: str = ''


@dataclasses.dataclass
class ThinkingBlock:
    type: Literal['thinking', 'redacted_thinking'] = 'thinking'
    data: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ChatMessage:
    role: MessageRole
    content: str = ''
    tool_use_id: str = ''
    tool_name: str = ''
    input: Any = None
    is_error: bool = False
    blocks: list[ThinkingBlock] | None = None
    provider_usage: ProviderUsage | None = None
    usage_stale: bool = False
    message_id: str = ''
    reasoning_content: str | None = None

    def __post_init__(self):
        if not self.message_id:
            self.message_id = uuid.uuid4().hex[:12]


@dataclasses.dataclass
class ToolCall:
    id: str
    tool_name: str
    input: Any


@dataclasses.dataclass
class AgentStep:
    type: Literal['assistant', 'tool_calls']
    content: str = ''
    kind: Literal['final', 'progress'] | None = None
    calls: list[ToolCall] = dataclasses.field(default_factory=list)
    content_kind: Literal['progress'] | None = None
    thinking_blocks: list[ThinkingBlock] | None = None
    diagnostics: dict[str, Any] | None = None
    usage: ProviderUsage | None = None
    reasoning_content: str | None = None


class ModelAdapter:
    """Protocol for model adapters."""

    async def next(self, messages: list[ChatMessage]) -> AgentStep:
        raise NotImplementedError


@dataclasses.dataclass
class CompressionResult:
    messages: list[ChatMessage]
    summary: ChatMessage
    removed_count: int
    tokens_before: int
    tokens_after: int
