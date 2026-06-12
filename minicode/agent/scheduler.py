"""Multi-agent scheduler: delegate tasks to sub-agents."""

from __future__ import annotations

import os
import time

from ..types import ChatMessage
from ..tools import ToolRegistry
from .loop import run_agent_turn
from .types import DelegatedTaskOutput

DEFAULT_SYSTEM_PROMPT = (
    'You are a focused sub-agent with access to file, search, and command tools. '
    'Complete the delegated task accurately using the tools available to you. '
    'Use read_file or list_files to read files when needed. '
    'Do not ask for clarification — work with available information.'
)


async def delegate_task(
    agent_name: str,
    task: str,
    tools: ToolRegistry,
    model,
    system_prompt: str = '',
    max_steps: int = 25,
    tools_config: list[dict] | None = None,
) -> DelegatedTaskOutput:
    start = time.time()
    messages = [
        ChatMessage(role='system', content=system_prompt or DEFAULT_SYSTEM_PROMPT),
        ChatMessage(role='user', content=task),
    ]

    try:
        result_messages = await run_agent_turn(
            model=model, tools=tools, messages=messages, cwd=os.getcwd(),
            tools_config=tools_config, max_steps=max_steps,
        )
        last = next((m for m in reversed(result_messages) if m.role == 'assistant'), None)
        summary = last.content[:500] if last else '(no output)'
        return DelegatedTaskOutput(
            agent_name=agent_name, summary=summary, status='completed',
            messages=result_messages,
        )
    except Exception as e:
        return DelegatedTaskOutput(
            agent_name=agent_name, summary='', status='failed',
            messages=messages, error=str(e),
        )
