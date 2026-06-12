from __future__ import annotations

import os
from pathlib import Path

from . import ToolContext, ToolDefinition, ToolResult


def _run(input_data: dict, context: ToolContext) -> ToolResult:
    path = input_data.get('path', '.')
    full_path = Path(context.cwd) / path
    try:
        entries = sorted(os.listdir(full_path))
        lines = [f'{e}{"/" if (full_path / e).is_dir() else ""}' for e in entries]
        return ToolResult(ok=True, output='\n'.join(lines) if lines else '(empty directory)')
    except FileNotFoundError:
        return ToolResult(ok=False, output=f"Directory not found: {path}")
    except PermissionError:
        return ToolResult(ok=False, output=f"Permission denied: {path}")
    except Exception as e:
        return ToolResult(ok=False, output=str(e))


list_files_tool = ToolDefinition(
    name='list_files',
    description='List files in a directory relative to the workspace root.',
    input_schema={
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Directory path, defaults to .'},
        },
    },
    run=_run,
)
