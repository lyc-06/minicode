from __future__ import annotations

from pathlib import Path
from typing import Any


def build_system_prompt(cwd: str, tool_descriptions: list[str]) -> str:
    has_memory = any('memory_recall' in d for d in tool_descriptions)
    memory_section = (
        '',
        'Memory system:',
        '- You have a persistent project memory system (memory_recall / memory_remember tools).',
        '- At the start of each turn, relevant memories from previous sessions are automatically injected as context.',
        '- Use memory_remember to save important facts, decisions, or task progress so they persist across sessions.',
        '- Example: when starting a multi-step task, save a "task started" memory with status. When the user asks about progress later, recall it.',
    ) if has_memory else ()

    parts = [
        'You are MiniCode, a terminal coding assistant.',
        'You help users by reading files, searching code, running commands, and making code changes.',
        f'Current working directory: {cwd}',
        '',
        'You have access to the following tools:',
        *[f'  - {d}' for d in tool_descriptions],
        '',
        *memory_section,
        '',
        'Rules:',
        '- Use tools to accomplish tasks step by step.',
        '- When you need clarification, use ask_user with one concise question.',
        '- When still working on a task, keep going until it is complete.',
        '- Verify your work by checking results before reporting completion.',
    ]
    return '\n'.join(parts)
