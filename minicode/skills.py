from __future__ import annotations

import os
from pathlib import Path


def discover_skills(cwd: str) -> list[str]:
    """Discover available skills from .minicode/skills directories."""
    roots = [
        Path(cwd) / '.minicode' / 'skills',
        Path.home() / '.minicode' / 'skills',
    ]
    skills = []
    for root in roots:
        if root.exists():
            for d in root.iterdir():
                if d.is_dir() and (d / 'SKILL.md').exists():
                    skills.append(d.name)
    return sorted(set(skills))
