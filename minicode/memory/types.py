from __future__ import annotations

import dataclasses
from typing import Literal

MemoryType = Literal['observation', 'decision', 'fact', 'preference', 'summary']


@dataclasses.dataclass
class MemoryEntry:
    id: str
    type: MemoryType
    content: str
    timestamp: float
    tags: list[str]
    source: str
    session_id: str = ''


@dataclasses.dataclass
class MemoryStats:
    total_entries: int
    by_type: dict[MemoryType, int]
    oldest_entry: float
    newest_entry: float
