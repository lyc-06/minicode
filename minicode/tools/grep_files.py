from __future__ import annotations

import os
from pathlib import Path

from . import ToolContext, ToolDefinition, ToolResult


def _run(input_data: dict, context: ToolContext) -> ToolResult:
    pattern = input_data.get('pattern', '')
    path = input_data.get('path', context.cwd)
    root = Path(context.cwd) / path

    if not pattern:
        return ToolResult(ok=False, output="Pattern is required")

    try:
        import subprocess
        result = subprocess.run(
            ['rg', '-n', pattern, '--max-depth', '20', str(root)],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout.strip() or '(no matches)'
        return ToolResult(ok=result.returncode == 0, output=output)
    except FileNotFoundError:
        return ToolResult(ok=False, output="rg (ripgrep) not found. Install ripgrep or use grep.")
    except Exception as e:
        return ToolResult(ok=False, output=str(e))


grep_files_tool = ToolDefinition(
    name='grep_files',
    description='Search for text in files using ripgrep.',
    input_schema={
        'type': 'object',
        'properties': {
            'pattern': {'type': 'string', 'description': 'Search pattern'},
            'path': {'type': 'string', 'description': 'Search path'},
        },
        'required': ['pattern'],
    },
    run=_run,
)
