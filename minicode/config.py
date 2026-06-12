from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get('MINICODE_HOME', Path.home() / '.minicode'))
CONFIG_FILE = CONFIG_DIR / 'settings.json'
MCP_CONFIG_FILE = CONFIG_DIR / 'mcp.json'
PROJECTS_DIR = CONFIG_DIR / 'projects'


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings(cwd: str = '') -> dict[str, Any]:
    ensure_dirs()
    # Project-level config takes priority
    if cwd:
        project_file = Path(cwd) / '.minicode' / 'settings.json'
        try:
            return json.loads(project_file.read_text(encoding='utf-8-sig'))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    try:
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8-sig'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(updates: dict[str, Any]):
    ensure_dirs()
    current = load_settings()
    current.update(updates)
    CONFIG_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def load_runtime_config(cwd: str = '') -> dict[str, Any]:
    settings = load_settings(cwd)
    env = {**{k: v for k, v in os.environ.items()}, **(settings.get('env', {}))}

    # Support both OpenAI-style and Anthropic-style env vars
    model = (
        os.environ.get('MINICODE_MODEL')
        or settings.get('model')
        or env.get('OPENAI_MODEL', '')
        or env.get('ANTHROPIC_MODEL', '')
    )
    base_url = (
        env.get('OPENAI_BASE_URL', '').strip()
        or settings.get('base_url', '')
        or 'https://api.deepseek.com'
    )
    api_key = (
        os.environ.get('OPENAI_API_KEY', '').strip()
        or os.environ.get('ANTHROPIC_API_KEY', '').strip()
        or settings.get('api_key', '')
    )

    return {
        'model': model,
        'base_url': base_url,
        'api_key': api_key,
        'mcp_servers': load_mcp_config(cwd),
    }


def load_mcp_config(cwd: str = '') -> dict[str, Any]:
    # Project-level .mcp.json takes priority
    if cwd:
        project_mcp = Path(cwd) / '.mcp.json'
        try:
            return json.loads(project_mcp.read_text(encoding='utf-8-sig')).get('mcpServers', {})
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    # Fall back to user-level mcp.json
    try:
        return json.loads(MCP_CONFIG_FILE.read_text(encoding='utf-8-sig')).get('mcpServers', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
