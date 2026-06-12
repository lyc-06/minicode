from __future__ import annotations

from pathlib import Path

from . import ToolContext, ToolDefinition, ToolResult


def _run(input_data: dict, context: ToolContext) -> ToolResult:
    question = input_data.get('question', '').strip()
    if not question:
        return ToolResult(ok=False, output="Question is required")
    return ToolResult(ok=True, output=question, await_user=True)


ask_user_tool = ToolDefinition(
    name='ask_user',
    description='Ask the user a question and wait for a reply.',
    input_schema={
        'type': 'object',
        'properties': {
            'question': {'type': 'string', 'description': 'Question to ask'},
        },
        'required': ['question'],
    },
    run=_run,
)
