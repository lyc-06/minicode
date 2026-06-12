from __future__ import annotations

from pathlib import Path

from . import ToolContext, ToolDefinition, ToolResult


def _run(input_data: dict, context: ToolContext) -> ToolResult:
    rel_path = input_data.get('path', '')
    offset = input_data.get('offset', 0)
    limit = input_data.get('limit', 0)

    full_path = Path(context.cwd) / rel_path
    try:
        text = full_path.read_text(encoding='utf-8')
        lines = text.split('\n')
        if offset > 0:
            lines = lines[offset:]
        if limit > 0:
            lines = lines[:limit]
        output = '\n'.join(lines)
        if not output.strip():
            return ToolResult(ok=True, output='(empty file)')

        info = f"File: {rel_path} ({len(lines)} lines shown)"
        return ToolResult(ok=True, output=f"{info}\n{output}")
    except FileNotFoundError:
        return ToolResult(ok=False, output=f"File not found: {rel_path}")
    except PermissionError:
        return ToolResult(ok=False, output=f"Permission denied: {rel_path}")
    except Exception as e:
        return ToolResult(ok=False, output=str(e))


read_file_tool = ToolDefinition(
    name='read_file',
    description='Read a UTF-8 text file relative to the workspace root.',
    input_schema={
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'File path'},
            'offset': {'type': 'number', 'description': 'Line offset'},
            'limit': {'type': 'number', 'description': 'Max lines'},
        },
        'required': ['path'],
    },
    run=_run,
)
