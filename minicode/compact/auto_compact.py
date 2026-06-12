"""Auto compact: emergency compression when context is near the limit."""

from __future__ import annotations

import json

from ..types import ChatMessage
from .collapse import estimate_tokens

CONTEXT_LIMIT = 200_000
SAFETY_MARGIN = 0.85
TRIGGER_THRESHOLD = int(CONTEXT_LIMIT * SAFETY_MARGIN)


def estimate_total_tokens(messages: list[ChatMessage]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(m.content)
        if m.input:
            total += estimate_tokens(json.dumps(m.input))
    return total


def should_auto_compact(messages: list[ChatMessage]) -> bool:
    if len(messages) < 10:
        return False
    return estimate_total_tokens(messages) > TRIGGER_THRESHOLD
