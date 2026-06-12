from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .types import MemoryEntry, MemoryStats, MemoryType

MAX_ENTRIES = 500
MEMORY_FILE = 'memory.jsonl'


def _get_file_path(cwd: str) -> Path:
    return Path(cwd) / '.minicode' / MEMORY_FILE


def _entry_matches(entry: MemoryEntry, **filters) -> bool:
    if 'types' in filters and filters['types']:
        if entry.type not in filters['types']:
            return False
    if 'tags' in filters and filters['tags']:
        if not any(t in entry.tags for t in filters['tags']):
            return False
    if 'keywords' in filters and filters['keywords']:
        content = entry.content.lower()
        if not any(kw.lower() in content for kw in filters['keywords']):
            return False
    return True


class MemoryStore:
    def __init__(self, cwd: str):
        self._file_path = _get_file_path(cwd)
        self._cache: list[MemoryEntry] | None = None

    def _ensure_dir(self):
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> list[MemoryEntry]:
        if self._cache is not None:
            return self._cache
        try:
            text = self._file_path.read_text(encoding='utf-8')
            self._cache = [MemoryEntry(**json.loads(line)) for line in text.strip().split('\n') if line]
        except (FileNotFoundError, json.JSONDecodeError):
            self._cache = []
        return self._cache

    def _persist_all(self, entries: list[MemoryEntry]):
        self._ensure_dir()
        lines = '\n'.join(json.dumps(e.__dict__, ensure_ascii=False) for e in entries) + '\n'
        self._file_path.write_text(lines, encoding='utf-8')
        self._cache = entries

    def add(self, entry: MemoryEntry) -> MemoryEntry:
        entries = self.load_all()
        entries.append(entry)
        if len(entries) > MAX_ENTRIES:
            entries.sort(key=lambda e: e.timestamp, reverse=True)
            entries = entries[:MAX_ENTRIES]
            self._persist_all(entries)
        else:
            self._ensure_dir()
            with open(self._file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry.__dict__, ensure_ascii=False) + '\n')
        return entry

    def query(self, limit: int = 10, **filters) -> list[MemoryEntry]:
        entries = self.load_all()
        matched = [e for e in entries if _entry_matches(e, **filters)]
        matched.sort(key=lambda e: e.timestamp, reverse=True)
        return matched[:limit]

    def search(self, keywords: list[str], limit: int = 10) -> list[MemoryEntry]:
        return self.query(keywords=keywords, limit=limit)

    def remove(self, entry_id: str) -> bool:
        entries = self.load_all()
        filtered = [e for e in entries if e.id != entry_id]
        if len(filtered) == len(entries):
            return False
        self._persist_all(filtered)
        return True

    def clear(self):
        self._cache = []
        self._ensure_dir()
        self._file_path.write_text('', encoding='utf-8')

    def get_recent(self, count: int = 10) -> list[MemoryEntry]:
        entries = self.load_all()
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:count]

    def get_stats(self) -> MemoryStats:
        entries = self.load_all()
        by_type: dict[MemoryType, int] = {}
        for e in entries:
            by_type[e.type] = by_type.get(e.type, 0) + 1
        timestamps = [e.timestamp for e in entries]
        return MemoryStats(
            total_entries=len(entries),
            by_type=by_type,
            oldest_entry=min(timestamps) if timestamps else 0,
            newest_entry=max(timestamps) if timestamps else 0,
        )
