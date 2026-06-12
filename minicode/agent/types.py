from __future__ import annotations

import dataclasses
from typing import Any, Literal

from ..types import ChatMessage


AgentStatus = Literal['idle', 'running', 'completed', 'failed']


@dataclasses.dataclass
class AgentSpec:
    name: str
    system_prompt: str
    model: Any  # ModelAdapter
    tools: Any  # ToolRegistry
    max_steps: int = 25


@dataclasses.dataclass
class AgentResult:
    agent_name: str
    status: AgentStatus
    messages: list[ChatMessage]
    error: str = ''
    summary: str = ''
    duration_ms: float = 0


@dataclasses.dataclass
class DelegatedTaskInput:
    agent_name: str
    task: str
    system_prompt: str = ''
    max_steps: int = 25


@dataclasses.dataclass
class DelegatedTaskOutput:
    agent_name: str
    summary: str
    status: AgentStatus
    messages: list[ChatMessage]
    error: str = ''
