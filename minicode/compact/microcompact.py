from __future__ import annotations

from ..types import ChatMessage


def microcompact(messages: list[ChatMessage], keep_recent: int = 10) -> list[ChatMessage]:
    """Lightweight compression: clear old tool results when history is long."""
    if len(messages) < keep_recent:
        return messages

    modified = False
    result = list(messages)

    for i, msg in enumerate(result):
        if msg.role == 'tool_result' and i < len(result) - keep_recent:
            if msg.content and not getattr(msg, '_compacted', False):
                old_len = len(msg.content)
                if old_len > 200:
                    msg.content = msg.content[:200] + f'\n... [compacted: was {old_len} chars]'
                    msg._compacted = True  # type: ignore
                    modified = True

    return result if modified else messages
