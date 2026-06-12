"""CLI entry point — full slash commands, TUI, session management, compression."""

from __future__ import annotations

import os
import shlex
import uuid

from . import __version__
from .agent.loop import run_agent_turn
from .compact.auto_compact import should_auto_compact
from .compact.microcompact import microcompact
from .compact.collapse import collapse_conversation
from .compact.snip import snip_compact
from .config import ensure_dirs, load_runtime_config, save_settings
from .memory.manager import MemoryManager
from .model_adapter import OpenAIStyleAdapter, AnthropicAdapter
from .prompt import build_system_prompt
from .session.store import save_session, list_sessions, load_session, delete_session
from .tools import ToolRegistry
from .tools.ask_user import ask_user_tool
from .tools.list_files import list_files_tool
from .tools.grep_files import grep_files_tool
from .tools.read_file import read_file_tool
from .tools.write_file import write_file_tool
from .tools.run_command import run_command_tool
from .tools.web_fetch import web_fetch_tool
from .tools.web_search import web_search_tool
from .tools.calculator import calculator_tool
from .tools.memory_tools import create_memory_tools
from .tools.delegate_task import create_delegate_tool
from .tools.verify_work import create_verify_tool
from .mcp.client import create_mcp_tools
from .tui import MiniCodeTUI
from .types import ChatMessage


def _make_chat(role: str, **kw) -> ChatMessage:
    return ChatMessage(role=role, **kw)


def _build_registry(cwd: str, model_ref: list, tools_ref: list) -> ToolRegistry:
    r = ToolRegistry()
    r.register_all([
        ask_user_tool, list_files_tool, grep_files_tool,
        read_file_tool, write_file_tool, run_command_tool, web_fetch_tool,
        web_search_tool, calculator_tool,
    ])
    r.register_all(create_memory_tools(cwd))
    # These capture model_ref/tools_ref by reference; checked at call time
    r.register(create_delegate_tool(model_ref, tools_ref))
    r.register(create_verify_tool(model_ref, tools_ref))
    return r


def _render_help() -> str:
    return (
        'Available commands:\n'
        '  /help           Show this help\n'
        '  /tools          List available tools\n'
        '  /status         Show current model and config\n'
        '  /model          Show current model\n'
        '  /model <name>   Set model and save to config\n'
        '  /skills         List discovered skills\n'
        '  /mcp            Show MCP server status\n'
        '  /resume         List saved sessions\n'
        '  /resume <id>    Resume a specific session\n'
        '  /new            Start a new session\n'
        '  /compact        Manually compress context\n'
        '  /collapse       Summarize old segments via LLM\n'
        '  /snip           Snip middle context\n'
        '  /search <kw>    Search across all sessions\n'
        '  /memory         Show memory stats\n'
        '  /ls [path]      List files\n'
        '  /grep <pattern> Search files\n'
        '  /read <path>    Read a file\n'
        '  /cmd <command>  Run a shell command\n'
        '  /exit           Exit MiniCode'
    )


async def main():
    ensure_dirs()
    cwd = os.getcwd()
    config = load_runtime_config(cwd)

    model_name = config.get('model') or os.environ.get('OPENAI_MODEL') or os.environ.get('ANTHROPIC_MODEL', 'deepseek-chat')

    # Auto-detect adapter based on model name
    is_anthropic = 'claude' in model_name.lower()

    if is_anthropic:
        # For Claude, prefer ANTHROPIC_API_KEY directly from env over the
        # config resolver (which prefers OPENAI_API_KEY first)
        api_key = (os.environ.get('ANTHROPIC_API_KEY')
                   or config.get('api_key')
                   or os.environ.get('OPENAI_API_KEY'))
    else:
        api_key = (config.get('api_key')
                   or os.environ.get('OPENAI_API_KEY')
                   or os.environ.get('ANTHROPIC_API_KEY'))

    if not api_key:
        import sys
        print('MiniCode: No API key configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY')
        sys.exit(1)

    session_id = uuid.uuid4().hex[:8]
    tui = MiniCodeTUI(session_id, model_name or 'deepseek-chat')
    memory = MemoryManager(cwd)

    model_ref: list = [None]
    tools_ref: list = [None]

    if is_anthropic:
        model = AnthropicAdapter(
            api_key=api_key,
            model=model_name or 'claude-sonnet-4-20250514',
        )
    else:
        model = OpenAIStyleAdapter(
            api_key=api_key,
            base_url=config.get('base_url', 'https://api.deepseek.com'),
            model=model_name or 'deepseek-chat',
        )
    model_ref[0] = model
    registry = _build_registry(cwd, model_ref, tools_ref)
    tools_ref[0] = registry

    # Connect MCP servers
    mcp_servers_config = config.get('mcp_servers', {})
    mcp_tools_list = []
    mcp_server_summaries: list[dict] = []
    if mcp_servers_config:
        try:
            mcp_tools_list, mcp_server_summaries = await create_mcp_tools(mcp_servers_config)
            registry.register_all(mcp_tools_list)
            tui.add_entry('status', f'MCP: connected {sum(1 for s in mcp_server_summaries if s["status"]=="connected")} server(s)')
        except Exception as e:
            tui.add_entry('status', f'MCP connection error: {e}')

    tools_config = model.get_tools_config(registry)
    messages: list[ChatMessage] = [
        _make_chat('system', content=build_system_prompt(
            cwd, [f'{t.name}: {t.description}' for t in registry.list()],
        )),
    ]

    tui.add_entry('status', f'MiniCode v{__version__} | Model: {model_name} | Session: {session_id}')
    tui.show()

    while True:
        user_input = await tui.get_input()
        if user_input is None:
            print('\nGoodbye!')
            break

        if not user_input:
            continue

        # === Slash commands ===
        if user_input == '/exit':
            print('\nGoodbye!')
            break

        if user_input == '/help' or user_input == '/':
            tui.add_entry('assistant', _render_help())
            tui.show()
            continue

        if user_input == '/tools':
            lines = ['Available tools:']
            for t in registry.list():
                lines.append(f'  {t.name}: {t.description}')
            tui.add_entry('assistant', '\n'.join(lines))
            tui.show()
            continue

        if user_input == '/status':
            lines = [
                f'Model: {model_name}',
                f'Session: {session_id}',
                f'Messages: {len(messages)}',
                f'Tools: {len(registry.list())}',
            ]
            tui.add_entry('assistant', '\n'.join(lines))
            tui.show()
            continue

        if user_input == '/model':
            tui.add_entry('assistant', f'Current model: {model_name}')
            tui.show()
            continue

        if user_input.startswith('/model '):
            new_model = user_input[7:].strip()
            if new_model:
                save_settings({'model': new_model})
                model_name = new_model
                tui.add_entry('assistant', f'Model saved: {new_model}')
            tui.show()
            continue

        if user_input == '/skills':
            from .skills import discover_skills
            skills = discover_skills(cwd)
            if skills:
                tui.add_entry('assistant', 'Discovered skills:\n' + '\n'.join(f'  {s}' for s in skills))
            else:
                tui.add_entry('assistant', 'No skills discovered.')
            tui.show()
            continue

        if user_input == '/mcp':
            if mcp_server_summaries:
                lines = ['MCP servers:']
                for s in mcp_server_summaries:
                    status = s.get('status', 'unknown')
                    name = s.get('name', '?')
                    tc = s.get('tool_count', 0)
                    err = f'  error={s["error"]}' if s.get('error') else ''
                    lines.append(f'  {name}: {status} ({tc} tools){err}')
                tui.add_entry('assistant', '\n'.join(lines))
            elif mcp_servers_config:
                tui.add_entry('assistant', 'MCP servers configured but connection not yet established. Restart to retry.')
            else:
                tui.add_entry('assistant', 'No MCP servers configured. Create a .mcp.json file to add one.')
            tui.show()
            continue

        if user_input == '/new':
            session_id = uuid.uuid4().hex[:8]
            messages = [_make_chat('system', content=messages[0].content)]
            tui.add_entry('status', f'Session cleared. New session: {session_id}')
            tui.show()
            continue

        if user_input == '/resume':
            sessions = list_sessions(cwd)
            if sessions:
                lines = ['Saved sessions:']
                for s in sessions:
                    lines.append(f'  {s["id"]}: {s["title"][:50]} ({s["message_count"]} msgs)')
                tui.add_entry('assistant', '\n'.join(lines))
            else:
                tui.add_entry('assistant', 'No saved sessions.')
            tui.show()
            continue

        if user_input.startswith('/resume '):
            sid = user_input[8:].strip()
            loaded = load_session(cwd, sid)
            if loaded and len(loaded) > 1:
                session_id = sid
                messages = [_make_chat('system', content=messages[0].content)]
                for evt in loaded[1:]:
                    messages.append(ChatMessage(
                        role=evt.get('role', 'user'),
                        content=evt.get('content', ''),
                        tool_use_id=evt.get('tool_use_id', ''),
                        tool_name=evt.get('tool_name', ''),
                        input=evt.get('input'),
                        is_error=evt.get('is_error', False),
                        reasoning_content=evt.get('reasoning_content'),
                    ))
                tui.add_entry('status', f'Resumed session: {sid} ({len(loaded)} events)')
            else:
                tui.add_entry('assistant', f'Session {sid} not found.')
            tui.show()
            continue

        if user_input.startswith('/search '):
            keyword = user_input[8:].strip()
            if not keyword:
                tui.add_entry('assistant', 'Usage: /search <keyword>')
                tui.show()
                continue
            from .session.store import search_sessions
            results = search_sessions(keyword)
            if results:
                lines = [f'Found {len(results)} session(s) matching "{keyword}":']
                for sid, project, matches in results:
                    lines.append(f'  [{sid}] {project}: {matches} match(es)')
                tui.add_entry('assistant', '\n'.join(lines))
            else:
                tui.add_entry('assistant', f'No matches for "{keyword}".')
            tui.show()
            continue

        if user_input == '/collapse':
            model = model_ref[0]
            if not model:
                tui.add_entry('assistant', 'No model available for collapse.')
                tui.show()
                continue
            tui.set_status('Collapsing...')
            tui.show()
            result = await collapse_conversation(messages, model.next)
            if result:
                messages, collapsed = result
                tui.add_entry('status', f'Collapse: summarized {collapsed} segment(s)')
            else:
                tui.add_entry('assistant', 'Nothing safe to collapse.')
            tui.show()
            continue

        if user_input == '/compact':
            result = snip_compact(messages)
            if result:
                messages, removed = result
                tui.add_entry('status', f'Compact: removed {removed} messages')
            else:
                tui.add_entry('assistant', 'Nothing to compact.')
            tui.show()
            continue

        if user_input == '/snip':
            result = snip_compact(messages, keep_head=2, keep_tail=10)
            if result:
                messages, removed = result
                tui.add_entry('status', f'Snip: removed {removed} messages')
            else:
                tui.add_entry('assistant', 'Nothing to snip.')
            tui.show()
            continue

        if user_input == '/memory':
            stats = await memory.get_stats()
            tui.add_entry('assistant', f'Memory stats: {stats["total_entries"]} entries\nBy type: {stats["by_type"]}')
            tui.show()
            continue

        if user_input.startswith('/ls'):
            parts = shlex.split(user_input)
            path = parts[1] if len(parts) > 1 else '.'
            import subprocess
            try:
                r = subprocess.run(['ls', path] if os.name != 'nt' else ['cmd', '/c', 'dir', path],
                                   capture_output=True, text=True, timeout=10)
                tui.add_entry('assistant', (r.stdout or r.stderr).strip()[:1000])
            except Exception as e:
                tui.add_entry('assistant', f'ls failed: {e}')
            tui.show()
            continue

        if user_input.startswith('/read '):
            path = user_input[6:].strip()
            try:
                text = open(os.path.join(cwd, path), encoding='utf-8').read()
                tui.add_entry('assistant', text[:2000])
            except Exception as e:
                tui.add_entry('assistant', f'read failed: {e}')
            tui.show()
            continue

        if user_input.startswith('/cmd '):
            cmd = user_input[5:].strip()
            import subprocess
            try:
                r = subprocess.run(cmd if os.name != 'nt' else ['cmd', '/c', cmd],
                                   capture_output=True, text=True, timeout=30, shell=(os.name == 'nt'))
                tui.add_entry('assistant', (r.stdout or r.stderr).strip()[:1000])
            except Exception as e:
                tui.add_entry('assistant', f'command failed: {e}')
            tui.show()
            continue

        if user_input.startswith('/grep '):
            pattern = user_input[6:].strip()
            import subprocess
            try:
                r = subprocess.run(['rg', '-n', pattern, '.'], capture_output=True, text=True, timeout=15, cwd=cwd)
                output = r.stdout.strip()[:1000] or '(no matches)'
                tui.add_entry('assistant', output)
            except FileNotFoundError:
                tui.add_entry('assistant', 'rg (ripgrep) not found')
            except Exception as e:
                tui.add_entry('assistant', f'grep failed: {e}')
            tui.show()
            continue

        if user_input.startswith('/'):
            tui.add_entry('assistant', f'Unknown command: {user_input}. Type /help for available commands.')
            tui.show()
            continue

        # === Normal conversation ===
        if should_auto_compact(messages):
            result = snip_compact(messages)
            if result:
                messages, removed = result
                tui.add_entry('status', f'Auto-compact: snipped {removed} messages')
                tui.show()

        # Auto recall: inject relevant memories as context before the user message
        try:
            _, memory_text = await memory.recall(user_input, limit=5)
            if memory_text and '(no relevant memories found)' not in memory_text:
                messages.append(_make_chat('system', content=f'[Relevant memories from previous sessions]\n{memory_text}'))
        except Exception:
            pass

        messages.append(_make_chat('user', content=user_input))
        tui.add_entry('user', user_input)
        tui.set_status('Thinking...')
        tui.show()

        try:
            def on_tool_start(name: str, inp):
                tui.set_tool(name)
                tui.set_status(f'Running {name}...')
                tui.show()

            def on_tool_result(name: str, output: str, is_error: bool):
                status = 'error' if is_error else 'success'
                tui.update_tool(name, status)
                tui.set_status('Thinking...')
                tui.show()

            messages = await run_agent_turn(
                model=model, tools=registry, messages=messages, cwd=cwd,
                tools_config=tools_config,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
            )

            messages = microcompact(messages)

        except Exception as e:
            tui.add_entry('assistant', f'Error: {e}')
            tui.set_status('')
            tui.show()
            import traceback
            traceback.print_exc()
            continue

        last_content = ''
        for msg in reversed(messages):
            if msg.role == 'assistant' and msg.content:
                last_content = msg.content
                tui.add_entry('assistant', msg.content)
                break

        tui.set_status('')

        if last_content:
            try:
                await memory.remember(
                    'summary',
                    f'User: {user_input[:200]}\nAssistant: {last_content[:500]}',
                    ['auto-consolidated', 'session'],
                    source=f'session:{session_id}',
                )
            except Exception:
                pass

        tui.show()

        try:
            events = [
                {
                    'role': m.role,
                    'content': m.content,
                    'tool_use_id': m.tool_use_id,
                    'tool_name': m.tool_name,
                    'input': m.input,
                    'is_error': m.is_error,
                    'reasoning_content': m.reasoning_content,
                }
                for m in messages if m.role != 'system'
            ]
            save_session(cwd, session_id, events, append=False)
        except Exception:
            pass

    await model.close()
