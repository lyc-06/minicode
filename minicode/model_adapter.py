from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .types import AgentStep, ChatMessage, ModelAdapter, ProviderUsage, ToolCall


class OpenAIStyleAdapter(ModelAdapter):
    """Adapter for OpenAI-compatible APIs (DeepSeek, OpenAI, etc.)."""

    def __init__(self, api_key: str, base_url: str = 'https://api.deepseek.com', model: str = ''):
        self._api_key = api_key
        self._base_url = base_url.rstrip('/')
        self._model = model or os.environ.get('OPENAI_MODEL', 'deepseek-chat')
        self._client = httpx.AsyncClient(timeout=120, trust_env=False)

    async def close(self):
        await self._client.aclose()

    async def next(self, messages: list[ChatMessage], tools_config: list[dict] | None = None) -> AgentStep:
        openai_messages = _convert_to_openai(messages)
        system_content = _get_system_content(messages)

        body: dict[str, Any] = {
            'model': self._model,
            'max_tokens': 8192,
            'messages': openai_messages,
        }
        if tools_config:
            body['tools'] = [
                {
                    'type': 'function',
                    'function': {
                        'name': t['name'],
                        'description': t.get('description', ''),
                        'parameters': t.get('input_schema', {}),
                    },
                }
                for t in tools_config
            ]

        # Retry once on transient failures
        for attempt in range(2):
            try:
                resp = await self._client.post(
                    f'{self._base_url}/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {self._api_key}',
                        'content-type': 'application/json',
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPStatusError as e:
                if attempt == 0 and e.response.status_code in (408, 429, 500, 502, 503):
                    continue  # retry
                detail = e.response.text[:300] if e.response else str(e)
                return AgentStep(type='assistant', content=f'API HTTP error {e.response.status_code}: {detail}')
            except httpx.RequestError as e:
                if attempt == 0:
                    continue  # retry
                return AgentStep(type='assistant', content=f'API request failed: {e}')
            except (UnicodeEncodeError, UnicodeDecodeError) as e:
                return AgentStep(type='assistant', content=f'Encoding error: {e}. Try avoiding emoji in responses.')
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                return AgentStep(type='assistant', content=f'API error: {e}')

        choice = data.get('choices', [{}])[0] or {}
        message = choice.get('message', {}) or {}
        content = message.get('content', '') or ''
        tool_calls_raw = message.get('tool_calls', [])
        reasoning_content = message.get('reasoning_content', None)

        usage_data = data.get('usage', {}) or {}
        usage = ProviderUsage(
            input_tokens=usage_data.get('prompt_tokens', 0),
            output_tokens=usage_data.get('completion_tokens', 0),
            total_tokens=usage_data.get('total_tokens', 0),
            source='api',
        )

        if tool_calls_raw:
            calls = []
            for tc in tool_calls_raw:
                func = tc.get('function', {}) or {}
                calls.append(ToolCall(
                    id=tc.get('id', ''),
                    tool_name=func.get('name', ''),
                    input=_parse_json_safe(func.get('arguments', '{}')),
                ))
            return AgentStep(type='tool_calls', content=content, calls=calls, usage=usage, reasoning_content=reasoning_content)

        return AgentStep(type='assistant', content=content, usage=usage, reasoning_content=reasoning_content)

    def get_tools_config(self, registry) -> list[dict]:
        return [{
            'name': t.name, 'description': t.description, 'input_schema': t.input_schema,
        } for t in registry.list()]


def _parse_json_safe(text: str) -> dict:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _get_system_content(messages: list[ChatMessage]) -> str:
    """Collect all system messages and concatenate them."""
    parts = []
    for m in messages:
        if m.role == 'system' and m.content:
            parts.append(m.content)
    return '\n\n'.join(parts)


def _convert_to_openai(messages: list[ChatMessage]) -> list[dict]:
    result = []
    system = _get_system_content(messages)
    if system:
        result.append({'role': 'system', 'content': system})

    for msg in messages:
        if msg.role == 'system':
            continue
        elif msg.role == 'user':
            result.append({'role': 'user', 'content': msg.content})
        elif msg.role in ('assistant', 'assistant_progress'):
            entry: dict[str, Any] = {'role': 'assistant', 'content': msg.content}
            if msg.reasoning_content:
                entry['reasoning_content'] = msg.reasoning_content
            result.append(entry)
        elif msg.role == 'assistant_tool_call':
            entry: dict[str, Any] = {
                'role': 'assistant',
                'tool_calls': [{
                    'id': msg.tool_use_id,
                    'type': 'function',
                    'function': {
                        'name': msg.tool_name,
                        'arguments': json.dumps(msg.input or {}, ensure_ascii=True),
                    },
                }],
            }
            if msg.reasoning_content:
                entry['reasoning_content'] = msg.reasoning_content
            result.append(entry)
        elif msg.role == 'tool_result':
            result.append({
                'role': 'tool',
                'tool_call_id': msg.tool_use_id,
                'content': msg.content,
            })
    return result


# ---------------------------------------------------------------------------
# Anthropic / Claude adapter
# ---------------------------------------------------------------------------

class AnthropicAdapter(ModelAdapter):
    """Adapter for Anthropic's Messages API (Claude models)."""

    def __init__(self, api_key: str, model: str = ''):
        self._api_key = api_key
        self._model = model or os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
        self._client = httpx.AsyncClient(timeout=120, trust_env=False)

    async def close(self):
        await self._client.aclose()

    async def next(self, messages: list[ChatMessage], tools_config: list[dict] | None = None) -> AgentStep:
        system_content = _get_system_content(messages)
        anthropic_messages = _convert_to_anthropic(messages)

        body: dict[str, Any] = {
            'model': self._model,
            'max_tokens': 8192,
            'messages': anthropic_messages,
        }
        if system_content:
            body['system'] = system_content
        if tools_config:
            # Anthropic tool format: no "type": "function" wrapper
            body['tools'] = [
                {
                    'name': t['name'],
                    'description': t.get('description', ''),
                    'input_schema': t.get('input_schema', {}),
                }
                for t in tools_config
            ]

        for attempt in range(2):
            try:
                resp = await self._client.post(
                    'https://api.anthropic.com/v1/messages',
                    headers={
                        'x-api-key': self._api_key,
                        'anthropic-version': '2023-06-01',
                        'content-type': 'application/json',
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPStatusError as e:
                if attempt == 0 and e.response.status_code in (408, 429, 500, 502, 503):
                    continue
                detail = e.response.text[:300] if e.response else str(e)
                return AgentStep(type='assistant', content=f'API HTTP error {e.response.status_code}: {detail}')
            except httpx.RequestError as e:
                if attempt == 0:
                    continue
                return AgentStep(type='assistant', content=f'API request failed: {e}')
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                return AgentStep(type='assistant', content=f'API error: {e}')

        # Parse Anthropic response
        content_blocks = data.get('content', [])
        usage_data = data.get('usage', {}) or {}
        usage = ProviderUsage(
            input_tokens=usage_data.get('input_tokens', 0),
            output_tokens=usage_data.get('output_tokens', 0),
            total_tokens=usage_data.get('input_tokens', 0) + usage_data.get('output_tokens', 0),
            source='api',
        )

        # Extract text and tool_use blocks
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in content_blocks:
            block_type = block.get('type', '')
            if block_type == 'text':
                text_parts.append(block.get('text', ''))
            elif block_type == 'tool_use':
                tool_calls.append(ToolCall(
                    id=block.get('id', ''),
                    tool_name=block.get('name', ''),
                    input=block.get('input', {}),
                ))
            elif block_type == 'thinking':
                # Claude thinking blocks — store as reasoning_content
                pass

        content = ''.join(text_parts)

        if tool_calls:
            return AgentStep(type='tool_calls', content=content, calls=tool_calls, usage=usage)

        return AgentStep(type='assistant', content=content, usage=usage)

    def get_tools_config(self, registry) -> list[dict]:
        return [{
            'name': t.name, 'description': t.description, 'input_schema': t.input_schema,
        } for t in registry.list()]


def _convert_to_anthropic(messages: list[ChatMessage]) -> list[dict]:
    """Convert MiniCode ChatMessage list to Anthropic Messages API format.

    Anthropic requires alternating user/assistant messages. Tool results are
    represented as content blocks within a 'user' message.
    """
    result: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == 'system':
            continue  # system is a top-level field, not a message
        elif msg.role == 'user':
            result.append({'role': 'user', 'content': msg.content})
        elif msg.role in ('assistant', 'assistant_progress'):
            entry: dict[str, Any] = {'role': 'assistant', 'content': msg.content}
            result.append(entry)
        elif msg.role == 'assistant_tool_call':
            # Anthropic represents tool calls as content blocks
            block = {
                'type': 'tool_use',
                'id': msg.tool_use_id,
                'name': msg.tool_name,
                'input': msg.input or {},
            }
            entry = {'role': 'assistant', 'content': [block]}
            result.append(entry)
        elif msg.role == 'tool_result':
            # Anthropic tool results are content blocks in a user message
            block = {
                'type': 'tool_result',
                'tool_use_id': msg.tool_use_id,
                'content': msg.content,
            }
            result.append({'role': 'user', 'content': [block]})

    return result
