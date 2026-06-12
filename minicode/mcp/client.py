"""MCP (Model Context Protocol) client — stdio and Streamable HTTP."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import httpx


class StdioMcpClient:
    """MCP client over stdio transport."""

    def __init__(self, server_name: str, config: dict):
        self.server_name = server_name
        self.command = config.get('command', '')
        self.args = config.get('args', [])
        self.env = {**config.get('env', {})}
        self._proc: subprocess.Popen | None = None
        self._next_id = 1

    async def start(self):
        if not self.command:
            raise ValueError(f'MCP server "{self.server_name}" has no command.')
        self._proc = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**__import__('os').environ, **self.env},
        )
        # Initialize
        await self._request('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'minicode-python', 'version': '0.2.0'},
        })

    async def list_tools(self) -> list[dict]:
        result = await self._request('tools/list', {})
        return result.get('tools', [])

    async def call_tool(self, name: str, args: dict) -> dict:
        result = await self._request('tools/call', {'name': name, 'arguments': args})
        return result

    async def close(self):
        if self._proc:
            self._proc.kill()
            self._proc = None

    async def _request(self, method: str, params: dict) -> dict:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError('MCP client not started')
        req_id = self._next_id
        self._next_id += 1
        body = json.dumps({'jsonrpc': '2.0', 'id': req_id, 'method': method, 'params': params})
        self._proc.stdin.write((body + '\n').encode())
        self._proc.stdin.flush()

        response_line = self._proc.stdout.readline() if self._proc.stdout else b''
        if not response_line:
            raise RuntimeError(f'MCP {self.server_name}: no response')
        resp = json.loads(response_line.decode())
        if 'error' in resp:
            raise RuntimeError(f'MCP {self.server_name}: {resp["error"]["message"]}')
        return resp.get('result', {})


class HttpMcpClient:
    """MCP client over Streamable HTTP transport."""

    def __init__(self, server_name: str, config: dict):
        self.server_name = server_name
        self.url = config.get('url', '')
        self._client = httpx.AsyncClient(timeout=30)
        self._next_id = 1

    async def start(self):
        if not self.url:
            raise ValueError(f'MCP server "{self.server_name}" has no URL.')
        await self._request('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'minicode-python', 'version': '0.2.0'},
        })

    async def list_tools(self) -> list[dict]:
        result = await self._request('tools/list', {})
        return result.get('tools', [])

    async def call_tool(self, name: str, args: dict) -> dict:
        return await self._request('tools/call', {'name': name, 'arguments': args})

    async def close(self):
        await self._client.aclose()

    async def _request(self, method: str, params: dict) -> dict:
        req_id = self._next_id
        self._next_id += 1
        resp = await self._client.post(
            self.url,
            json={'jsonrpc': '2.0', 'id': req_id, 'method': method, 'params': params},
            headers={'content-type': 'application/json'},
        )
        resp.raise_for_status()
        data = resp.json()
        if 'error' in data:
            raise RuntimeError(f'MCP {self.server_name}: {data["error"]["message"]}')
        return data.get('result', {})


async def create_mcp_tools(mcp_servers: dict) -> tuple[list[Any], list[dict]]:
    """Create tools from MCP server configurations."""
    from ..tools import ToolDefinition, ToolResult

    tools = []
    summaries = []

    for name, config in mcp_servers.items():
        if config.get('enabled') is False:
            summaries.append({'name': name, 'status': 'disabled', 'tool_count': 0})
            continue

        try:
            if config.get('url'):
                client = HttpMcpClient(name, config)
            else:
                client = StdioMcpClient(name, config)

            await client.start()
            descriptors = await client.list_tools()

            for desc in descriptors:
                t_name = f'mcp__{name}__{desc["name"]}'
                t_desc = desc.get('description', f'MCP tool from {name}')
                t_schema = desc.get('inputSchema', {})

                async def make_call(tool_client=client, tool_name=desc['name']):
                    async def _call(input_data: dict, _ctx=None):
                        result = await tool_client.call_tool(tool_name, input_data)
                        return ToolResult(ok=True, output=str(result))
                    return _call

                tools.append(ToolDefinition(
                    name=t_name,
                    description=t_desc,
                    input_schema=t_schema,
                    run=await make_call(),
                ))

            summaries.append({
                'name': name,
                'status': 'connected',
                'tool_count': len(descriptors),
            })
        except Exception as e:
            summaries.append({
                'name': name,
                'status': 'error',
                'tool_count': 0,
                'error': str(e),
            })

    return tools, summaries
