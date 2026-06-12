from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ..config import PROJECTS_DIR


def _project_dir(cwd: str) -> Path:
    name = cwd.replace(':', '').replace('\\', '-').replace('/', '-')
    return PROJECTS_DIR / name


def _session_path(cwd: str, session_id: str) -> Path:
    return _project_dir(cwd) / f'{session_id}.jsonl'


def save_session(cwd: str, session_id: str, events: list[dict[str, Any]], append: bool = True):
    path = _session_path(cwd, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e, ensure_ascii=False) for e in events]
    content = '\n'.join(lines) + '\n'
    if append and path.exists():
        path.write_text(path.read_text(encoding='utf-8') + content, encoding='utf-8')
    else:
        path.write_text(content, encoding='utf-8')


def load_session(cwd: str, session_id: str) -> list[dict[str, Any]] | None:
    path = _session_path(cwd, session_id)
    try:
        text = path.read_text(encoding='utf-8')
        return [json.loads(line) for line in text.strip().split('\n') if line]
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def list_sessions(cwd: str) -> list[dict[str, Any]]:
    project_path = _project_dir(cwd)
    try:
        files = sorted(project_path.glob('*.jsonl'), key=lambda f: f.stat().st_mtime, reverse=True)
        results = []
        for f in files:
            sid = f.stem
            lines = [l.strip() for l in f.read_text(encoding='utf-8').split('\n') if l.strip()]
            if not lines:
                continue
            try:
                first_line = json.loads(lines[0])
            except json.JSONDecodeError:
                continue
            results.append({
                'id': sid,
                'title': first_line.get('content', sid)[:60],
                'message_count': len(lines),
                'updated_at': f.stat().st_mtime,
            })
        return results
    except FileNotFoundError:
        return []


def delete_session(cwd: str, session_id: str):
    path = _session_path(cwd, session_id)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def search_sessions(keyword: str, max_results: int = 20) -> list[tuple[str, str, int]]:
    """Search across all projects' sessions. Returns [(session_id, project_name, match_count)]."""
    results = []
    kw = keyword.lower()

    try:
        projects = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]
    except FileNotFoundError:
        return results

    for project_dir in projects:
        try:
            for f in project_dir.glob('*.jsonl'):
                sid = f.stem
                try:
                    text = f.read_text(encoding='utf-8')
                    if kw in text.lower():
                        count = sum(1 for line in text.split('\n') if kw in line.lower())
                        if count > 0:
                            results.append((sid, project_dir.name, count))
                except Exception:
                    continue
        except Exception:
            continue

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:max_results]
