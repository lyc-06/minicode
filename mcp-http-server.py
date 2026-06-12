"""Minimal MCP server over Streamable HTTP transport."""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

TOOLS = [
    {
        'name': 'hello',
        'description': 'Say hello (via HTTP)',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Name to greet'},
            },
            'required': ['name'],
        },
    },
    {
        'name': 'echo',
        'description': 'Echo back a message (via HTTP)',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'},
            },
            'required': ['message'],
        },
    },
]


def handle(msg: dict) -> dict:
    method = msg.get('method', '')
    rid = msg.get('id')
    if method == 'initialize':
        return {'jsonrpc': '2.0', 'id': rid, 'result': {
            'protocolVersion': '2024-11-05',
            'capabilities': {'tools': {}},
            'serverInfo': {'name': 'http-test-server', 'version': '1.0'},
        }}
    if method == 'tools/list':
        return {'jsonrpc': '2.0', 'id': rid, 'result': {'tools': TOOLS}}
    if method == 'tools/call':
        params = msg.get('params', {})
        name = params.get('name', '')
        args = params.get('arguments', {})
        if name == 'hello':
            text = f"Hello, {args.get('name', 'world')}! (via HTTP)"
        elif name == 'echo':
            text = f"Echo: {args.get('message', '')} (via HTTP)"
        else:
            return {'jsonrpc': '2.0', 'id': rid,
                    'error': {'code': -32601, 'message': f'Unknown tool: {name}'}}
        return {'jsonrpc': '2.0', 'id': rid,
                'result': {'content': [{'type': 'text', 'text': text}]}}
    return {'jsonrpc': '2.0', 'id': rid,
            'error': {'code': -32601, 'message': f'Unknown method: {method}'}}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        msg = json.loads(self.rfile.read(length))
        resp = handle(msg)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

    def log_message(self, fmt, *args):
        pass  # keep it quiet


if __name__ == '__main__':
    port = int(__import__('sys').argv[1]) if len(__import__('sys').argv) > 1 else 9876
    srv = HTTPServer(('', port), Handler)
    print(f'MCP HTTP server running on http://localhost:{port}')
    srv.serve_forever()
