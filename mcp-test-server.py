"""Minimal MCP test server — list tools and echo."""
import json
import sys

def send(msg):
    sys.stdout.write(json.dumps(msg) + '\n')
    sys.stdout.flush()

def handle(msg):
    method = msg.get('method', '')
    msg_id = msg.get('id')

    if method == 'initialize':
        send({'jsonrpc': '2.0', 'id': msg_id, 'result': {
            'protocolVersion': '2024-11-05',
            'capabilities': {'tools': {}},
            'serverInfo': {'name': 'test-server', 'version': '1.0'},
        }})
    elif method == 'notifications/initialized':
        pass
    elif method == 'tools/list':
        send({'jsonrpc': '2.0', 'id': msg_id, 'result': {
            'tools': [
                {
                    'name': 'hello',
                    'description': 'Say hello to someone',
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
                    'description': 'Echo back a message',
                    'inputSchema': {
                        'type': 'object',
                        'properties': {
                            'message': {'type': 'string'},
                        },
                        'required': ['message'],
                    },
                },
            ]
        }})
    elif method == 'tools/call':
        params = msg.get('params', {})
        name = params.get('name', '')
        args = params.get('arguments', {})
        if name == 'hello':
            send({'jsonrpc': '2.0', 'id': msg_id, 'result': {
                'content': [{'type': 'text', 'text': f"Hello, {args.get('name', 'world')}!"}],
            }})
        elif name == 'echo':
            send({'jsonrpc': '2.0', 'id': msg_id, 'result': {
                'content': [{'type': 'text', 'text': f"Echo: {args.get('message', '')}"}],
            }})
        else:
            send({'jsonrpc': '2.0', 'id': msg_id, 'error': {'code': -32601, 'message': f'Unknown tool: {name}'}})

if __name__ == '__main__':
    buffer = ''
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        buffer += line
        if line.strip():
            try:
                msg = json.loads(line.strip())
                handle(msg)
            except json.JSONDecodeError:
                pass
        buffer = ''
