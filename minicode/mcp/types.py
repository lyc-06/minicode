from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class McpServerConfig:
    command: str = ''
    args: list[str] = dataclasses.field(default_factory=list)
    env: dict[str, str] = dataclasses.field(default_factory=dict)
    url: str = ''
    enabled: bool = True
    protocol: str = 'auto'


@dataclasses.dataclass
class McpServerSummary:
    name: str
    status: str  # 'connecting' | 'connected' | 'error' | 'disabled'
    tool_count: int = 0
    error: str = ''
