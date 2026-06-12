from __future__ import annotations

import dataclasses
import inspect
from typing import Any, Callable, Coroutine


@dataclasses.dataclass
class ToolContext:
    cwd: str
    permissions: Any = None


@dataclasses.dataclass
class ToolResult:
    ok: bool
    output: str
    background_task: Any = None
    await_user: bool = False


class ToolDefinition:
    """Definition of a single tool that the agent can call."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        run: Callable[[dict[str, Any], ToolContext], ToolResult | Any],
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self._run = run

    async def run(self, input_data: dict[str, Any], context: ToolContext) -> ToolResult:
        result = self._run(input_data, context)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ToolResult):
            return result
        return ToolResult(ok=True, output=str(result))

    def validate_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return input_data


class ToolRegistry:
    """Central registry for all tools available to the agent."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def register_all(self, tools: list[ToolDefinition]):
        for t in tools:
            self.register(t)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def has(self, name: str) -> bool:
        return name in self._tools

    async def execute(
        self, name: str, input_data: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(ok=False, output=f"Unknown tool: {name}")
        try:
            validated = tool.validate_input(input_data)
            return await tool.run(validated, context)
        except Exception as e:
            return ToolResult(ok=False, output=str(e))
