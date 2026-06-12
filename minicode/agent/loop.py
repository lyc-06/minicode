"""Agent loop: the core model -> tool -> model execution loop."""

from __future__ import annotations

from typing import Callable

from ..types import ChatMessage, ModelAdapter
from ..tools import ToolContext, ToolRegistry

EMPTY_RESPONSE_MAX_RETRIES = 2


async def run_agent_turn(
    model: ModelAdapter,
    tools: ToolRegistry,
    messages: list[ChatMessage],
    cwd: str,
    tools_config: list[dict] | None = None,
    max_steps: int = 25,
    on_tool_start: Callable | None = None,
    on_tool_result: Callable | None = None,
    on_assistant_message: Callable | None = None,
) -> list[ChatMessage]:
    empty_retry_count = 0
    context = ToolContext(cwd=cwd)

    for step in range(max_steps):
        step_result = await model.next(messages, tools_config)

        if step_result.type == 'assistant':
            content = step_result.content.strip()
            if not content and empty_retry_count < EMPTY_RESPONSE_MAX_RETRIES:
                empty_retry_count += 1
                messages.append(ChatMessage(role='user', content='Your response was empty. Continue.'))
                continue

            if on_assistant_message:
                on_assistant_message(content)

            messages.append(ChatMessage(
                role='assistant', content=content,
                provider_usage=step_result.usage,
                reasoning_content=step_result.reasoning_content,
            ))
            return messages

        if step_result.type == 'tool_calls':
            if step_result.content and on_assistant_message:
                on_assistant_message(step_result.content)

            for call in step_result.calls:
                if on_tool_start:
                    on_tool_start(call.tool_name, call.input)

                result = await tools.execute(call.tool_name, call.input or {}, context)

                if on_tool_result:
                    on_tool_result(call.tool_name, result.output, not result.ok)

                msg_kw = {}
                if step_result.reasoning_content:
                    msg_kw['reasoning_content'] = step_result.reasoning_content

                if result.await_user:
                    messages.append(ChatMessage(role='assistant_tool_call', tool_use_id=call.id, tool_name=call.tool_name, input=call.input, **msg_kw))
                    messages.append(ChatMessage(role='tool_result', tool_use_id=call.id, tool_name=call.tool_name, content=result.output, is_error=not result.ok))
                    messages.append(ChatMessage(role='assistant', content=result.output))
                    return messages

                messages.append(ChatMessage(role='assistant_tool_call', tool_use_id=call.id, tool_name=call.tool_name, input=call.input, **msg_kw))
                messages.append(ChatMessage(role='tool_result', tool_use_id=call.id, tool_name=call.tool_name, content=result.output, is_error=not result.ok))

    messages.append(ChatMessage(role='assistant', content=f'Reached max steps ({max_steps}).'))
    return messages
