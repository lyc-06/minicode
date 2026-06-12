# MiniCode Python 亮点测试指南

## 前置条件

```powershell
cd C:\Users\lyc\Desktop\MiniCode-Python
python -m minicode
```

启动后在 `>` 提示符后输入以下命令进行测试。

---

## 1. Agent Loop 引擎 — 核心循环

验证 Agent 能够接收请求、调用工具、返回结果。

### 测试 1.1：文件操作

```text
帮我列出当前目录的文件
```

**预期**：Agent 调用 `list_files` 工具，返回文件列表。TUI 显示 `[list_files] running` → `[list_files] success`。

### 测试 1.2：读文件

```text
读一下 README.md
```

**预期**：Agent 调用 `read_file` 工具，返回 README 内容。

### 测试 1.3：执行命令

```text
运行 python --version
```

**预期**：Agent 调用 `run_command` 工具，返回 Python 版本号。

### 测试 1.4：连续多步

```text
先列出当前目录，然后读 README.md 的前 5 行
```

**预期**：Agent 依次调用 `list_files` → `read_file`，展示多步工具调用能力。

---

## 2. 多 Agent 协作与自验证

验证 `delegate_task`（委派子任务）和 `verify_work`（自验证）功能。

### 测试 2.1：委派子任务

```text
用 delegate_task 创建一个子 agent，让它读 README.md 并总结前三行
```

**预期**：主 Agent 创建 Sub-Agent，Sub-Agent 独立执行任务后返回总结。

### 测试 2.2：创建文件 + 验证

```text
帮我写一个 Python 脚本 hello.py，输出 "Hello MiniCode"。然后用 verify_work 验证这个脚本是否正确
```

**预期**：Agent 先调用 `write_file` 创建脚本，再调用 `verify_work` 启动验证 Agent 审查。

---

## 3. 统一工具协议

验证所有工具通过统一的 `ToolRegistry` 注册和管理。

### 测试 3.1：查看工具列表

```text
/tools
```

**预期**：列出所有注册的工具，每个工具包含名称和描述。

预期输出示例：

```
Available tools:
  ask_user: Ask the user a question...
  list_files: List files in a directory...
  grep_files: Search for text in files...
  read_file: Read a UTF-8 text file...
  write_file: Write a UTF-8 text file...
  run_command: Run a shell command...
  web_fetch: Fetch a web page...
  delegate_task: Delegate a sub-task to a sub-agent...
  verify_work: Verify completed work...
  memory_remember: Save an item to long-term memory...
  memory_recall: Search project memory...
  memory_stats: Show memory statistics...
```

---

## 4. 持久化记忆系统

验证 Memory 系统的存储、检索、统计功能。

### 测试 4.1：保存记忆

```text
用 memory_remember 记一条：类型是 fact，内容为 "MiniCode Python 版本已完成 Tier 2 开发"，标签为 ["project", "python"]
```

**预期**：返回：

```
Memory saved (id: a1b2c3d4e5f6, type: fact, tags: project, python).
```

### 测试 4.2：检索记忆

```text
用 memory_recall 搜索 "MiniCode"
```

**预期**：返回刚才保存的记忆条目。

### 测试 4.3：查看记忆统计

```text
/memory
```

**预期**：显示记忆统计信息，包含总条目数和按类型分布。

---

## 5. MCP 协议集成

验证 MCP 客户端模块的可用性。

### 测试 5.1：查看 MCP 状态

```text
/mcp
```

**预期**：显示当前 MCP 服务器配置状态。如果没有配置，显示 `No MCP servers configured.`。

### 测试 5.2：配置并连接 MCP（可选）

如果需要实际测试 MCP 连接，先退出 minicode，在 PowerShell 中：

```powershell
pip install mcp-server-filesystem
echo '{"mcpServers":{"filesystem":{"command":"python","args":["-m","mcp_server_filesystem","."]}}}' > .mcp.json
```

然后重启 `python -m minicode`，再次输入 `/mcp` 查看状态。

---

## 6. 上下文压缩系统

验证 Snip Compact 和 Microcompact 功能。

### 测试 6.1：手动压缩

```text
/compact
```

**预期**：显示 `Compact: removed N messages`。

### 测试 6.2：裁剪中间历史

```text
/snip
```

**预期**：显示 `Snip: removed N messages`。

---

## 一键快速验证（无需启动 CLI）

```powershell
cd C:\Users\lyc\Desktop\MiniCode-Python

# 工具注册
python -c "from minicode.tools import ToolRegistry; r=ToolRegistry(); print('1. ToolRegistry OK')"

# 记忆系统
python -c "import asyncio; from minicode.memory.manager import MemoryManager; asyncio.run(MemoryManager('.').remember('fact', 'test', ['t'], 'manual')); print('2. Memory OK')"

# 会话存储
python -c "from minicode.session.store import save_session, list_sessions; save_session('.', 'test', [{'role':'user','content':'hi'}]); print(f'3. Sessions: {len(list_sessions(\".\"))}')"

# 上下文压缩
python -c "from minicode.types import ChatMessage; from minicode.compact import snip_compact; msgs=[ChatMessage(role='system',content='x')]+[ChatMessage(role='user',content='x') for _ in range(30)]; r=snip_compact(msgs,3,10); print(f'4. Compact: {\"OK\" if r else \"nothing\"}')"

# Agent 类型
python -c "from minicode.agent.types import AgentSpec, AgentResult, DelegatedTaskOutput; print('5. Agent types OK')"

# MCP 客户端
python -c "from minicode.mcp.client import StdioMcpClient, HttpMcpClient; print('6. MCP client OK')"
```

## 全部命令速查

| 命令 | 作用 |
|------|------|
| `/help` | 显示所有可用命令 |
| `/tools` | 查看所有可用工具 |
| `/status` | 查看当前模型和会话状态 |
| `/model` | 显示当前模型 |
| `/model <name>` | 切换模型并保存到配置 |
| `/skills` | 列出已发现的 skills |
| `/mcp` | 查看 MCP 服务器状态 |
| `/resume` | 列出已保存的会话 |
| `/resume <id>` | 恢复指定会话 |
| `/new` | 开始新会话 |
| `/compact` | 手动压缩上下文 |
| `/snip` | 裁剪中间历史 |
| `/search <kw>` | 跨会话搜索 |
| `/memory` | 查看记忆统计 |
| `/ls [path]` | 列出目录文件 |
| `/grep <pattern>` | 搜索文件内容 |
| `/read <path>` | 读取文件 |
| `/cmd <command>` | 执行命令 |
| `/exit` | 退出 |
