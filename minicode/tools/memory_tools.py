from __future__ import annotations

from ..memory.manager import MemoryManager
from . import ToolContext, ToolDefinition, ToolResult


def create_memory_tools(cwd: str) -> list[ToolDefinition]:
    manager = MemoryManager(cwd)

    async def _remember(input_data: dict, _ctx: ToolContext) -> ToolResult:
        entry = await manager.remember(
            mem_type=input_data.get('type', 'observation'),
            content=input_data.get('content', ''),
            tags=input_data.get('tags', []),
            source='agent',
        )
        return ToolResult(
            ok=True,
            output=f"Memory saved (id: {entry.id}, type: {entry.type}, tags: {', '.join(entry.tags)})."
        )

    async def _recall(input_data: dict, _ctx: ToolContext) -> ToolResult:
        entries, formatted = await manager.recall(
            query=input_data.get('query', ''),
            limit=input_data.get('limit', 10),
        )
        if not entries:
            return ToolResult(ok=True, output='No relevant memories found.')
        return ToolResult(ok=True, output=f"Found {len(entries)} memories:\n\n{formatted}")

    async def _stats(_input_data: dict, _ctx: ToolContext) -> ToolResult:
        s = await manager.get_stats()
        return ToolResult(ok=True, output=f"Total entries: {s['total_entries']}\nBy type: {s['by_type']}")

    return [
        ToolDefinition(
            name='memory_remember',
            description='Save an item to long-term project memory.',
            input_schema={
                'type': 'object',
                'properties': {
                    'type': {
                        'type': 'string',
                        'enum': ['observation', 'decision', 'fact', 'preference', 'summary'],
                        'description': 'Type of memory.',
                    },
                    'content': {'type': 'string', 'description': 'Memory content.'},
                    'tags': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Tags.'},
                },
                'required': ['type', 'content', 'tags'],
            },
            run=_remember,
        ),
        ToolDefinition(
            name='memory_recall',
            description='Search project memory for relevant information.',
            input_schema={
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'Search query.'},
                    'limit': {'type': 'number', 'description': 'Max results.'},
                },
                'required': ['query'],
            },
            run=_recall,
        ),
        ToolDefinition(
            name='memory_stats',
            description='Show memory statistics.',
            input_schema={'type': 'object', 'properties': {}},
            run=_stats,
        ),
    ]
