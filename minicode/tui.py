"""TUI module — rich terminal UI with input loop."""

from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from . import __version__

console = Console()


class MiniCodeTUI:
    """Terminal UI for MiniCode."""

    def __init__(self, session_id: str, model_name: str):
        self.session_id = session_id
        self.model_name = model_name
        self.transcript: list[dict] = []
        self.scroll_offset = 0
        self.status = ''
        self.active_tool = ''

    def _render_header(self) -> Panel:
        info = Text()
        info.append(' MiniCode ', style='bold cyan')
        info.append(f'v{__version__}', style='cyan')
        info.append(f'  Model: {self.model_name}', style='green')
        info.append(f'  Session: {self.session_id}', style='yellow')
        return Panel(info, box=box.ASCII, style='blue')

    def _render_body(self) -> Panel:
        if not self.transcript:
            return Panel('Welcome to MiniCode. Type a message to start.', box=box.ASCII, title='Transcript')

        lines = []
        start = max(0, len(self.transcript) - 20 - self.scroll_offset)
        visible = self.transcript[start:]

        for entry in visible:
            kind = entry.get('kind', '')
            body = entry.get('body', '')

            if kind == 'user':
                lines.append(Text(f'> {body[:200]}', style='bold green'))
            elif kind == 'assistant':
                lines.append(Markdown(body[:500]))
            elif kind == 'tool':
                s = entry.get('status', '')
                tn = entry.get('tool_name', '')
                sc = 'green' if s == 'success' else ('red' if s == 'error' else 'yellow')
                lines.append(Text(f'  [{tn}] {s}', style=sc))
            elif kind == 'progress':
                lines.append(Text(f'  {body[:100]}', style='dim'))
            elif kind == 'status':
                lines.append(Text('  ' + ('-' * 40), style='dim'))
                lines.append(Text(f'  {body[:100]}', style='dim white'))

        content = Group(*lines) if lines else Text('(empty)')
        return Panel(content, box=box.ASCII, title=f'Transcript ({len(self.transcript)} events)')

    def _render_footer(self) -> Panel:
        if self.active_tool:
            return Panel(Text(f'Running: {self.active_tool}', style='yellow'), box=box.ASCII, style='dim')
        if self.status:
            return Panel(Text(self.status, style='dim'), box=box.ASCII, style='dim')
        return Panel(Text('/exit to quit', style='dim'), box=box.ASCII, style='dim')

    def show(self):
        console.clear()
        console.print(self._render_header())
        console.print()
        console.print(self._render_body())
        console.print()
        console.print(self._render_footer())

    def add_entry(self, kind: str, body: str, **kw):
        self.transcript.append({'kind': kind, 'body': body, **kw})
        self.scroll_offset = 0

    def update_tool(self, tool_name: str, status: str, body: str = ''):
        self.transcript.append({'kind': 'tool', 'tool_name': tool_name, 'status': status, 'body': body})

    def set_status(self, s: str):
        self.status = s

    def set_tool(self, name: str):
        self.active_tool = name

    async def get_input(self) -> str | None:
        try:
            raw = input('> ')
            return raw.strip()
        except (EOFError, KeyboardInterrupt):
            return None
