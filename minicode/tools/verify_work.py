from __future__ import annotations

from ..agent.scheduler import delegate_task as _delegate
from . import ToolContext, ToolDefinition, ToolResult

VERIFIER_PROMPT = (
    'You are a verification agent. Critically review the work done by another agent.\n\n'
    '1. Read relevant files to check correctness.\n'
    '2. Run tests if applicable.\n'
    '3. Check for edge cases, security issues, and errors.\n\n'
    'Output format:\n'
    '- PASS if correct.\n'
    '- MINOR if there are small issues.\n'
    '- FAIL if there are significant problems.\n'
    'List specific issues with file paths.'
)


def create_verify_tool(model_ref: list, tools_ref: list) -> ToolDefinition:

    async def _run(input_data: dict, _ctx: ToolContext) -> ToolResult:
        model = model_ref[0]
        tools = tools_ref[0]

        task = input_data.get('task', '')
        work_summary = input_data.get('work_summary', '')
        verify_task = f'Original task: {task}\n\nWork summary: {work_summary}\n\nReview thoroughly.'

        result = await _delegate(
            agent_name='verifier',
            task=verify_task,
            tools=tools,
            model=model,
            system_prompt=VERIFIER_PROMPT,
            max_steps=20,
        )

        verdict = 'FAILED'
        summary = result.summary or ''
        if summary.startswith('PASS'):
            verdict = 'PASS'
        elif summary.startswith('MINOR'):
            verdict = 'PASSED_WITH_MINOR_ISSUES'

        return ToolResult(
            ok=verdict.startswith('PASS'),
            output=f'[Verification report]\nVerdict: {verdict}\n\n{summary}',
        )

    return ToolDefinition(
        name='verify_work',
        description='Verify completed work using a verification sub-agent.',
        input_schema={
            'type': 'object',
            'properties': {
                'task': {'type': 'string', 'description': 'Original task description.'},
                'work_summary': {'type': 'string', 'description': 'What was done.'},
            },
            'required': ['task'],
        },
        run=_run,
    )
