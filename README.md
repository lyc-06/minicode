# MiniCode (Python)

<h2 align="center">MiniCode — Python</h2>

<p align="center">
  基于 Python 的轻量级终端编码 Agent 框架。为学习而生，为简洁而建。
</p>

一个面向本地开发工作流的轻量级终端编码助手，完整移植自 TypeScript 版本的 MiniCode 架构设计。

## 项目简介

MiniCode 围绕一个实用的 terminal-first agent loop 构建：

- 接收用户请求
- 调用工具（读文件、搜索代码、执行命令等）
- 多轮 model→tool→model 闭环直到任务完成
- 支持多 Agent 委派与自验证
- 支持持久化记忆和跨会话上下文

## 功能特性

### 核心工作流

- Agent tool-use 主循环，支持多步工具执行
- 多 Agent 协作：`delegate_task` 委附子任务、`verify_work` 自验证
- 分层的持久化记忆系统（observation / decision / fact / preference / summary）
- 会话持久化（JSONL 格式，按项目隔离）
- 上下文压缩（裁剪压缩 + 微压缩 + 紧急自动压缩）
- MCP 协议客户端（stdio + Streamable HTTP）
- Rich 终端 UI（TUI）展示 transcript 与工具状态

### 内置工具

- `list_files` — 列出目录
- `grep_files` — 搜索文件内容
- `read_file` — 读文件
- `write_file` — 写文件
- `run_command` — 执行命令
- `web_fetch` — 抓取网页
- `ask_user` — 询问用户
- `delegate_task` — 委派子 Agent
- `verify_work` — 验证工作输出
- `memory_remember` — 保存记忆
- `memory_recall` — 检索记忆
- `memory_stats` — 记忆统计

## 安装

```bash
cd MiniCode-Python
pip install -e .
```

依赖：`httpx`、`rich`

## 快速开始

### 配置 API Key

```bash
# 环境变量
export ANTHROPIC_API_KEY="sk-your-key"

# 或配置文件 ~/.minicode/settings.json
# {"model": "claude-sonnet-4-20250514"}
```

### 启动

```bash
python -m minicode
```

### 命令

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
| `/collapse` | LLM 摘要折叠（保留核心信息） |
| `/search <kw>` | 跨会话搜索 |
| `/memory` | 查看记忆统计 |
| `/ls [path]` | 列出目录文件 |
| `/grep <pattern>` | 搜索文件内容 |
| `/read <path>` | 读取文件 |
| `/cmd <command>` | 执行命令 |
| `/exit` | 退出 |

在 `>` 提示符后输入自然语言即可让 Agent 执行任务。

## 项目结构

```
minicode/
├── agent/
│   ├── loop.py        # Agent 主循环 (model→tool→model)
│   ├── scheduler.py   # 多 Agent 调度委派
│   └── types.py       # Agent 类型定义
├── tools/
│   ├── __init__.py     # ToolDefinition + ToolRegistry
│   ├── list_files.py   # 列出文件
│   ├── grep_files.py   # 搜索文件
│   ├── read_file.py    # 读文件
│   ├── write_file.py   # 写文件
│   ├── run_command.py  # 执行命令
│   ├── web_fetch.py    # 网页抓取
│   ├── ask_user.py     # 询问用户
│   ├── delegate_task.py    # 子 Agent 委派
│   ├── verify_work.py      # 工作验证
│   └── memory_tools.py     # 记忆工具
├── memory/
│   ├── store.py        # 记忆持久化 (JSONL)
│   ├── manager.py      # 记忆高层接口
│   └── types.py        # 记忆类型定义
├── compact/
│   ├── snip.py         # 裁剪压缩
│   ├── microcompact.py # 微压缩
│   ├── collapse.py     # 摘要折叠
│   └── auto_compact.py # 自动紧急压缩
├── mcp/
│   └── client.py       # MCP 协议客户端
├── session/
│   └── store.py        # 会话持久化
├── cli.py              # CLI 入口 (含 TUI)
├── tui.py              # 终端 UI
├── model_adapter.py    # Anthropic API 适配器
├── config.py           # 配置加载
├── prompt.py           # 系统提示词构建
└── types.py            # 核心类型定义
```

## 代码规模

当前核心实现约 **1,900 行 Python**。

统计口径：全部 `minicode/` 源码，不含测试和外部依赖。

## 版本说明

Python 版本是 TypeScript 架构设计的完整移植，保持核心功能对等的同时利用了 Python 生态优势（Rich TUI、httpx 异步、简单项目结构）。
