from __future__ import annotations

import uuid
import time

from .types import MemoryEntry, MemoryType
from .store import MemoryStore


class MemoryManager:
    def __init__(self, cwd: str):
        self._store = MemoryStore(cwd)

    async def remember(
        self,
        mem_type: MemoryType,
        content: str,
        tags: list[str],
        source: str = 'agent',
        session_id: str = '',
    ) -> MemoryEntry:
        entry = MemoryEntry(
            id=uuid.uuid4().hex[:12],
            type=mem_type,
            content=content,
            timestamp=time.time(),
            tags=tags,
            source=source,
            session_id=session_id,
        )
        return self._store.add(entry)

    async def recall(self, query: str, limit: int = 10) -> tuple[list[MemoryEntry], str]:
        keywords = [w for w in query.split() if len(w) > 1]
        entries = self._store.search(keywords, limit)
        if not entries:
            return [], '(no relevant memories found)'
        formatted = '\n'.join(
            f'[{e.timestamp:.0f}] [{e.type}] [{", ".join(e.tags)}] {e.content}'
            for e in entries
        )
        return entries, formatted

    async def get_recent_context(self, count: int = 10) -> str:
        entries = self._store.get_recent(count)
        if not entries:
            return ''
        lines = ['Recent project memories:']
        for e in entries:
            lines.append(f'  [{e.type}] {e.content[:200]}')
        return '\n'.join(lines)

    async def get_stats(self) -> dict:
        stats = self._store.get_stats()
        return {
            'total_entries': stats.total_entries,
            'by_type': stats.by_type,
        }

    async def remove(self, entry_id: str) -> bool:
        return self._store.remove(entry_id)

    async def clear(self):
        self._store.clear()
