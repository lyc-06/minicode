from __future__ import annotations

import httpx

from . import ToolContext, ToolDefinition, ToolResult


def _run(input_data: dict, context: ToolContext) -> ToolResult:
    url = input_data.get('url', '')
    if not url:
        return ToolResult(ok=False, output="URL is required")

    try:
        resp = httpx.get(url, follow_redirects=True, timeout=15, trust_env=False)
        resp.raise_for_status()
        text = resp.text[:10000]
        return ToolResult(ok=True, output=f"URL: {url}\n\n{text}")
    except httpx.HTTPError as e:
        return ToolResult(ok=False, output=f"HTTP error: {e}")
    except Exception as e:
        return ToolResult(ok=False, output=str(e))


web_fetch_tool = ToolDefinition(
    name='web_fetch',
    description='Fetch a web page and return its text content.',
    input_schema={
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'URL to fetch'},
        },
        'required': ['url'],
    },
    run=_run,
)
