from __future__ import annotations

import contextvars

from ..agent.scheduler import delegate_task as _delegate
from . import ToolContext, ToolDefinition, ToolResult

# 嵌套深度追踪。每层 delegate_task 调用 +1，返回时 -1
# contextvars 保证 asyncio 并发安全
_delegate_depth: contextvars.ContextVar[int] = contextvars.ContextVar('delegate_depth', default=0)
MAX_DELEGATE_DEPTH = 3


def create_delegate_tool(model_ref: list, tools_ref: list) -> ToolDefinition:

    async def _run(input_data: dict, _ctx: ToolContext) -> ToolResult:
        # 检查嵌套深度
        current_depth = _delegate_depth.get()
        if current_depth >= MAX_DELEGATE_DEPTH:
            return ToolResult(
                ok=False,
                output=f'Cannot delegate: max nesting depth ({MAX_DELEGATE_DEPTH}) reached. '
                       f'Current depth: {current_depth}. The sub-agent cannot create further sub-agents.',
            )

        model = model_ref[0]
        tools = tools_ref[0]
        agent_name = input_data.get('agent_name', 'sub-agent')
        task = input_data.get('task', '')

        tools_config = model.get_tools_config(tools) if model and tools else None

        # 深度 +1 后执行
        token = _delegate_depth.set(current_depth + 1)
        try:
            result = await _delegate(
                agent_name=agent_name,
                task=task,
                tools=tools,
                model=model,
                system_prompt=input_data.get('system_prompt', ''),
                max_steps=input_data.get('max_steps', 25),
                tools_config=tools_config,
            )
        finally:
            _delegate_depth.reset(token)

        return ToolResult(
            ok=result.status == 'completed',
            output=f'[Sub-agent: {agent_name}]\nStatus: {"SUCCESS" if result.status == "completed" else "FAILED"}\nSummary: {result.summary}',
        )

    return ToolDefinition(
        name='delegate_task',
        description='Delegate a sub-task to a sub-agent that runs independently.',
        input_schema={
            'type': 'object',
            'properties': {
                'agent_name': {'type': 'string', 'description': 'Name for this sub-agent.'},
                'task': {'type': 'string', 'description': 'Task description.'},
                'system_prompt': {'type': 'string', 'description': 'Optional custom system prompt.'},
                'max_steps': {'type': 'number', 'description': 'Max tool-use steps.'},
            },
            'required': ['agent_name', 'task'],
        },
        run=_run,
    )
