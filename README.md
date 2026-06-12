<p align="center">
  <h1 align="center">MiniCode</h1>
  <p align="center">从零实现的轻量级终端编码 Agent 框架</p>
  <p align="center"><i>为学习而生，为简洁而建</i></p>
</p>

---

## 这是什么？

**MiniCode** 是一个从零构建的最小可用 Agent 框架，核心 runtime 仅 ~75 行代码。

它不依赖 LangChain、OpenHands 等现成框架，而是**手写了一个完整的 model→tool→model 闭环**——接收用户输入、调用 LLM 判断是直接回答还是使用工具、执行工具、读取结果、继续循环直到给出最终答案。

整个项目 **~2000 行 Python**，每行都清晰可读。它证明了 Agent 的核心思想并不复杂——你完全可以理解它，而不是对着一个黑盒调参。

---

## 解决了什么问题？

| 问题 | MiniCode 的答案 |
|------|----------------|
| **LangChain 太重** | 核心 loop 只有 75 行，你能读完并理解每一行 |
| **Agent 原理被抽象层掩盖** | 没有 AgentExecutor、没有 Chain、没有复杂的回调系统——就是纯代码 |
| **想学 Agent 但找不到合适的入口** | 从 LLM 调用到工具执行到记忆系统，全部自实现，适合学习 |
| **需要一个可定制的轻量 Agent** | 改源码直接生效，不需要透过多层继承和回调 |

---

## 核心亮点

### 🧠 纯手工打造的 Agent 引擎

`minicode/agent/loop.py` — 核心 75 行：

```
用户输入 → model.next() → 判断回复还是调工具
  ├─ assistant: 返回结果，本轮结束
  └─ tool_calls: 执行工具 → 结果放回 messages → 继续循环
```

- 空响应自动重试（模型偶尔抽风时自动追问）
- 最大步数保护（默认 25 步，防止死循环）
- 工具执行日志（每一步都实时显示在 TUI 上）
- 支持 DeepSeek 推理模型的 `reasoning_content` 回传

### 🤝 多 Agent 协作

- **delegate_task**：委派子 Agent 独立运行，深度控制（默认 3 层）
- **verify_work**：子 Agent 自验证工作质量，输出 PASS / MINOR / FAIL
- 每个子 Agent 有独立 system prompt，共享工具集

### 🧠 持久化记忆系统（跨会话）

四层架构，每层各司其职：

```
Agent Tools (memory_remember / memory_recall / memory_stats)
        ↓
MemoryManager (remember / recall / get_stats)
        ↓
MemoryStore (add / query / search / remove)
        ↓
JSONL 文件 (.minicode/memory.jsonl)
```

- 5 种记忆类型：observation / decision / fact / preference / summary
- 关键词搜索 + Tag 过滤
- 上限 500 条，超出自动淘汰最旧

### 📦 上下文压缩系统

三级压缩，防止长对话撑爆上下文窗口：

1. **Snip**：裁剪中间历史（保留头尾）
2. **MicroCompact**：压缩旧工具结果（保留前 200 字符）
3. **Collapse**：LLM 摘要折叠（把老对话用摘要替换）

上下文接近 200K tokens 时自动触发紧急压缩。

### 🔌 MCP 协议支持

- 支持 Stdio 和 Streamable HTTP 两种传输
- 即插即用任何 MCP 服务器
- 通过 `/mcp` 查看连接状态

### 🎨 终端 UI

基于 Rich 构建的 TUI，实时展示：

- 对话转录
- 工具调用状态（running / success / error）
- 当前模型和会话信息

### 🔧 双模型适配器

```
ModelAdapter 接口
  ├── OpenAIStyleAdapter → DeepSeek / OpenAI 等兼容 API
  └── AnthropicAdapter   → Claude API
```

自动检测：model 名含 `claude` 时使用 Anthropic 适配器，其余走 OpenAI 格式。要接入新模型只需实现 `ModelAdapter.next()` 一个方法。

---

## 内置工具（14 个）

| 工具 | 用途 |
|------|------|
| `ask_user` | 向用户提问，等待回复 |
| `list_files` | 列出目录内容 |
| `grep_files` | 搜索文件内容 |
| `read_file` | 读取文件 |
| `write_file` | 写入文件 |
| `run_command` | 执行 shell 命令 |
| `web_fetch` | 抓取网页内容 |
| `web_search` | 搜索网络（Bing） |
| `calculator` | 安全算术求值 |
| `memory_remember` | 保存记忆 |
| `memory_recall` | 检索记忆 |
| `memory_stats` | 记忆统计 |
| `delegate_task` | 委派子 Agent |
| `verify_work` | 验证工作输出 |

---

## 快速开始

### 前置要求

- Python >= 3.11
- pip

### 安装

```bash
git clone https://github.com/lyc-06/minicode.git
cd minicode
pip install -e .
```

### 配置 API Key

**方式一：配置文件**（推荐）

复制模板并根据你的模型修改：

```bash
cp settings.example.json .minicode/settings.json
# 然后编辑 .minicode/settings.json，填入你的 API Key
```

**方式二：环境变量**

```bash
# DeepSeek / OpenAI
export OPENAI_API_KEY="sk-your-key"
export OPENAI_BASE_URL="https://api.deepseek.com"
export OPENAI_MODEL="deepseek-chat"

# 或 Anthropic Claude（二选一）
export ANTHROPIC_API_KEY="sk-ant-your-key"
export ANTHROPIC_MODEL="claude-sonnet-4-20250514"
```

### 启动

```bash
python -m minicode
```

看到 `>` 提示符后即可输入自然语言与 Agent 对话。

---

## 使用示例

### 基础对话

```
> 这个项目用什么语言写的？

MiniCode 使用 Python 编写，核心运行时约 2000 行。你可以在 minicode/ 目录下查看完整源码。
```

### 多步工具调用

```
> 帮我统计一下这个项目有多少个 Python 文件

Agent → 调用 grep_files 搜索 .py 文件
Agent → 调用 run_command 执行 wc -l
Agent → 返回统计结果
```

### 跨会话记忆

```
> 帮我记住：项目依赖 httpx 和 rich
（Agent 调用 memory_remember 保存）

> /new
（开启新会话）

> 这个项目依赖哪些库？
（Agent 自动调用 memory_recall 查到了之前保存的记忆）
```

### Session 持久化

```
（第一轮对话后）
> /resume
→ 列出所有已保存的 session

> /resume abc12345
→ 恢复 session，Agent 能继续之前的任务
```

---

## 命令参考

| 命令 | 作用 |
|------|------|
| `/help` | 显示所有可用命令 |
| `/tools` | 查看所有可用工具 |
| `/status` | 查看当前模型和会话状态 |
| `/model <name>` | 切换模型并保存到配置 |
| `/mcp` | 查看 MCP 服务器状态 |
| `/resume` | 列出已保存的会话 |
| `/resume <id>` | 恢复指定会话 |
| `/new` | 开始新会话 |
| `/compact` | 手动压缩上下文 |
| `/collapse` | LLM 摘要折叠 |
| `/memory` | 查看记忆统计 |
| `/search <kw>` | 跨会话搜索 |
| `/exit` | 退出 |

---

## 项目结构

```
minicode/
├── agent/
│   ├── loop.py        # Agent 主循环（核心 75 行）
│   ├── scheduler.py   # 子 Agent 调度
│   └── types.py       # Agent 类型定义
├── tools/
│   ├── __init__.py     # 工具注册表
│   └── *.py           # 14 个工具实现
├── memory/
│   ├── store.py        # 记忆持久化（JSONL）
│   ├── manager.py      # 记忆高层接口
│   └── types.py        # 记忆类型定义
├── compact/
│   ├── snip.py         # 裁剪压缩
│   ├── microcompact.py # 微压缩
│   ├── collapse.py     # 摘要折叠
│   └── auto_compact.py # 自动压缩
├── mcp/
│   └── client.py       # MCP 协议客户端
├── session/
│   └── store.py        # 会话持久化
├── cli.py              # CLI 入口
├── tui.py              # 终端 UI
├── model_adapter.py    # LLM 适配器
├── prompt.py           # 系统提示词
├── config.py           # 配置加载
└── types.py            # 核心类型
```

---

## 代码规模

| 模块 | 行数 |
|------|------|
| agent/ | ~120 |
| tools/ | ~350 |
| memory/ | ~160 |
| compact/ | ~130 |
| mcp/ | ~150 |
| session/ | ~100 |
| 其他 | ~1000 |
| **合计** | **~2000** |

---

## License

MIT
