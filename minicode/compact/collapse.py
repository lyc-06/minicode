"""Context collapse: LLM-generated summaries replace long conversation segments."""

from __future__ import annotations

from typing import Any, Callable

from ..types import ChatMessage

COLLAPSE_PROMPT = (
    'Summarize the following conversation segment concisely. '
    'Focus on: what was asked, what tools were used, what decisions were made, and what the outcome was. '
    'Keep the summary under 200 words.'
)


def estimate_tokens(text: str) -> int:
    """Token 估算，区分中英文。

    中文平均 1 字 ≈ 2 token，英文/数字/符号平均 4 字符 ≈ 1 token。
    MiniCode 主要面向中文用户，混合估算比纯 len//4 更准确。
    """
    chinese = sum(1 for c in text if '一' <= c <= '鿿')
    other = len(text) - chinese
    return chinese * 2 + other // 4


def find_collapse_candidates(
    messages: list[ChatMessage],
    min_segment_length: int = 6,
    max_segment_length: int = 40,
) -> list[tuple[int, int]]:
    """找出适合折叠的对话段。返回 [(start, end), ...]"""
    if len(messages) < min_segment_length + 5:
        return []

    keep_tail = 10
    max_i = len(messages) - keep_tail
    candidates = []
    i = 1  # 跳过 system 消息

    while i < max_i:
        if messages[i].role == 'user':
            seg_end = min(i + max_segment_length, max_i)

            # 调整末尾，确保不拆散 tool_call/tool_result 对
            actual_end = seg_end
            for j in range(i, seg_end):
                if messages[j].role == 'assistant_tool_call':
                    actual_end = max(actual_end, j + 2)
                if messages[j].role == 'tool_result' and j + 1 > actual_end:
                    actual_end = j + 1
            actual_end = min(actual_end, max_i + 2)

            if actual_end - i >= min_segment_length:
                candidates.append((i, actual_end))
                i = actual_end  # 跳过已折叠的段
                continue

        i += 1

    return candidates


def build_collapse_prompt(segment: list[ChatMessage]) -> str:
    """为指定段构造摘要请求。"""
    lines = [f'[{m.role}] {m.content[:200]}' for m in segment]
    return f'{COLLAPSE_PROMPT}\n\nConversation segment:\n' + '\n'.join(lines)


async def collapse_segment(
    segment: list[ChatMessage],
    model_next: Callable,
) -> str | None:
    """调模型生成一段对话的摘要。返回摘要文本，失败返回 None。"""
    from ..types import ChatMessage as CM

    prompt = build_collapse_prompt(segment)
    msgs = [
        CM(role='user', content=prompt),
    ]

    try:
        step = await model_next(msgs, None)
        if step.type == 'assistant' and step.content.strip():
            return step.content.strip()
    except Exception:
        pass
    return None


async def collapse_conversation(
    messages: list[ChatMessage],
    model_next: Callable,
    min_segment_length: int = 6,
) -> tuple[list[ChatMessage], int] | None:
    """找到适合折叠的段，逐个生成摘要并替换。

    返回 (new_messages, collapsed_count) 或 None。
    """
    candidates = find_collapse_candidates(messages, min_segment_length)
    if not candidates:
        return None

    result = list(messages)
    collapsed = 0

    # 从后往前折叠，避免下标变化
    for start, end in reversed(candidates):
        segment = result[start:end]
        summary = await collapse_segment(segment, model_next)
        if not summary:
            continue

        summary_msg = ChatMessage(
            role='context_summary',
            content=f'[Collapsed] {summary}',
        )
        result = result[:start] + [summary_msg] + result[end:]
        collapsed += 1

    if collapsed == 0:
        return None
    return (result, collapsed)
