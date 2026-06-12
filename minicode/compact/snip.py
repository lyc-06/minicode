"""Snip compact: rule-based removal of safe middle-context segments."""

from __future__ import annotations

from ..types import ChatMessage

# Roles that must not be snipped
PROTECTED_ROLES = {'system', 'snip_boundary', 'context_summary'}


def find_snip_interval(
    messages: list[ChatMessage],
    keep_head: int = 3,
    keep_tail: int = 15,
) -> tuple[int, int] | None:
    """Find a safe interval [start, end) to remove from the middle.

    Rules:
    - Keep first `keep_head` messages (usually system + intro)
    - Keep last `keep_tail` messages (recent context)
    - Do not split tool_call/tool_result pairs
    - Do not remove protected roles
    """
    if len(messages) <= keep_head + keep_tail + 2:
        return None

    start = keep_head
    end = len(messages) - keep_tail

    # Expand to avoid splitting tool_call/tool_result pairs
    for i in range(start, min(end + 1, len(messages))):
        if messages[i].role == 'tool_result':
            start = i + 1
        if messages[i].role == 'assistant_tool_call':
            end = max(end, i + 1)

    if start >= end:
        return None

    # Check no protected messages in interval
    for i in range(start, end):
        if messages[i].role in PROTECTED_ROLES:
            return None

    return (start, end)


def snip_compact(
    messages: list[ChatMessage],
    keep_head: int = 3,
    keep_tail: int = 15,
) -> tuple[list[ChatMessage], int] | None:
    """Remove a safe middle segment. Returns (new_messages, removed_count) or None."""
    interval = find_snip_interval(messages, keep_head, keep_tail)
    if not interval:
        return None

    start, end = interval
    removed = end - start

    result = messages[:start] + messages[end:]
    return (result, removed)
