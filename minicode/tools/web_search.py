"""Web search tool — scrapes search results from Bing (accessible from China)."""

from __future__ import annotations

import re
import urllib.parse

import httpx

from . import ToolContext, ToolDefinition, ToolResult

BING_URL = 'https://www.bing.com/search'


def _parse_bing_results(html: str) -> list[dict]:
    """Parse Bing HTML search results into structured items."""
    results = []

    # Bing result blocks: <li class="b_algo"> ... </li>
    algo_blocks = re.findall(r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL)

    for block in algo_blocks[:5]:
        url = ''
        title = ''
        snippet = ''

        # --- Extract URL ---
        # Find the <h2> section which contains the actual result link
        h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.DOTALL)
        if not h2_match:
            continue
        h2_content = h2_match.group(1)

        # Extract href from the <a> inside h2 (skip favicon <a class="tilk">)
        url_match = re.search(r'<a[^>]*href="(https?://[^"]+)"[^>]*>', h2_content, re.DOTALL)
        if url_match:
            url = _unescape(url_match.group(1))

        # --- Extract title ---
        title_match = re.search(r'<a[^>]*>(.*?)</a>', h2_content, re.DOTALL)
        if title_match:
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
            title = _unescape(title)

        if not url and not title:
            continue

        # --- Extract snippet ---
        # Try <p> inside b_caption, or <div class="b_caption"> <p>
        caption_match = re.search(r'<div[^>]*class="b_caption"[^>]*>(.*?)</div>', block, re.DOTALL)
        if caption_match:
            p_match = re.search(r'<p[^>]*>(.*?)</p>', caption_match.group(1), re.DOTALL)
            if p_match:
                snippet = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
                snippet = _unescape(snippet)

        results.append({
            'title': title,
            'url': url,
            'snippet': snippet,
        })

    return results


def _unescape(text: str) -> str:
    """Simple HTML entity unescaping."""
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#x27;', "'")
    text = text.replace('&#x2F;', '/')
    return text


def _run(input_data: dict, _context: ToolContext) -> ToolResult:
    query = input_data.get('query', '')
    if not query:
        return ToolResult(ok=False, output='Search query is required')

    try:
        resp = httpx.get(
            BING_URL,
            params={'q': query, 'setlang': 'zh-Hans'},
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            },
            follow_redirects=True,
            timeout=15,
            trust_env=False,
        )
        resp.raise_for_status()

        results = _parse_bing_results(resp.text)

        if not results:
            return ToolResult(ok=True, output=f'No search results found for "{query}".')

        lines = [f'Search results for "{query}":']
        for i, r in enumerate(results, 1):
            lines.append(f'\n{i}. {r["title"]}')
            lines.append(f'   URL: {r["url"]}')
            if r['snippet']:
                lines.append(f'   {r["snippet"]}')
        return ToolResult(ok=True, output='\n'.join(lines))

    except httpx.TimeoutException:
        return ToolResult(ok=False, output='Search request timed out. The service may be blocked from your network.')
    except httpx.HTTPError as e:
        return ToolResult(ok=False, output=f'Search request failed: {e}')
    except Exception as e:
        return ToolResult(ok=False, output=f'Search error: {e}')


web_search_tool = ToolDefinition(
    name='web_search',
    description='Search the web using Bing. Returns top results with titles, URLs, and snippets.',
    input_schema={
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search query'},
        },
        'required': ['query'],
    },
    run=_run,
)
