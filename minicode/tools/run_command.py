from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from . import ToolContext, ToolDefinition, ToolResult


def _run(input_data: dict, context: ToolContext) -> ToolResult:
    cmd = input_data.get('command', '')
    args = input_data.get('args', [])
    cwd = input_data.get('cwd', context.cwd)

    if args:
        parts = [cmd] + args
    else:
        parts = shlex.split(cmd)

    try:
        result = subprocess.run(
            parts,
            cwd=Path(cwd).resolve(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + '\n' + result.stderr).strip()
        return ToolResult(ok=result.returncode == 0, output=output or '(no output)')
    except FileNotFoundError:
        return ToolResult(ok=False, output=f"Command not found: {parts[0]}")
    except subprocess.TimeoutExpired:
        return ToolResult(ok=False, output="Command timed out (120s)")
    except Exception as e:
        return ToolResult(ok=False, output=str(e))


run_command_tool = ToolDefinition(
    name='run_command',
    description='Run a shell command. Returns stdout and stderr.',
    input_schema={
        'type': 'object',
        'properties': {
            'command': {'type': 'string', 'description': 'Command to run'},
            'args': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional arguments'},
            'cwd': {'type': 'string', 'description': 'Working directory'},
        },
        'required': ['command'],
    },
    run=_run,
)
