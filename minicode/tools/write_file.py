from __future__ import annotations

from pathlib import Path

from . import ToolContext, ToolDefinition, ToolResult


def _run(input_data: dict, context: ToolContext) -> ToolResult:
    rel_path = input_data.get('path', '')
    content = input_data.get('content', '')
    full_path = Path(context.cwd) / rel_path

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        return ToolResult(ok=True, output=f"Written {len(content)} bytes to {rel_path}")
    except PermissionError:
        return ToolResult(ok=False, output=f"Permission denied: {rel_path}")
    except Exception as e:
        return ToolResult(ok=False, output=str(e))


write_file_tool = ToolDefinition(
    name='write_file',
    description='Write a UTF-8 text file relative to the workspace root.',
    input_schema={
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'File path'},
            'content': {'type': 'string', 'description': 'File content'},
        },
        'required': ['path', 'content'],
    },
    run=_run,
)
