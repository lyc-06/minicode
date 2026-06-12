#!/usr/bin/env python3
"""benchmark_ab_test.py — 三层上下文压缩 A/B 对照测试

真实调用 LLM API，对比开启压缩 vs 不开启压缩的 Token 消耗和响应耗时。

前置条件:
    - 已配置 API Key（从 minicode 配置中自动读取）
    - pip install tiktoken

用法:
    python benchmark_ab_test.py

注意:
    - 会消耗约 2 次 API 调用（约 $0.01-0.05）
    - 默认使用与 minicode 相同的模型配置
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time

import requests
import tiktoken

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from minicode.types import ChatMessage
from minicode.compact.microcompact import microcompact
from minicode.compact.snip import snip_compact
from minicode.compact.auto_compact import should_auto_compact

ENCODING = tiktoken.get_encoding("cl100k_base")


def count_text_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


def count_messages_tokens(messages: list[ChatMessage]) -> int:
    total = 0
    for m in messages:
        total += count_text_tokens(m.content or "")
        if m.input:
            total += count_text_tokens(json.dumps(m.input))
    return total


def apply_compression(messages: list[ChatMessage]) -> list[ChatMessage]:
    """模拟 cli.py 中的三层压缩流程。"""
    result = copy.deepcopy(messages)
    if should_auto_compact(result):
        r = snip_compact(result)
        if r:
            result, _ = r
    result = microcompact(result)
    return result


def load_config() -> dict:
    """从 .minicode/settings.json 和 env 中读取 API 配置。"""
    config = {}
    settings_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        ".minicode", "settings.json",
    )
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            config.update(json.load(f))

    api_key = (
        config.get("api_key")
        or config.get("auth_token")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    base_url = config.get("base_url") or os.environ.get(
        "OPENAI_BASE_URL", "https://api.deepseek.com",
    )
    model = config.get("model") or os.environ.get("OPENAI_MODEL", "deepseek-chat")

    return {"api_key": api_key, "base_url": base_url, "model": model}


def messages_to_openai(messages: list[ChatMessage]) -> list[dict]:
    """将 ChatMessage 列表转为 OpenAI API 格式。"""
    result = []
    for m in messages:
        if m.role == "system":
            result.append({"role": "system", "content": m.content})
        elif m.role == "user":
            result.append({"role": "user", "content": m.content})
        elif m.role in ("assistant", "assistant_progress", "context_summary"):
            entry = {"role": "assistant", "content": m.content}
            result.append(entry)
        elif m.role == "assistant_tool_call":
            # 将 tool_call 转为 assistant 消息，包含工具调用描述
            content = m.content or f"[Tool call: {m.tool_name}({json.dumps(m.input)})]"
            result.append({"role": "assistant", "content": content})
        elif m.role == "tool_result":
            # tool_result 转为 user 消息保留内容（让压缩效果体现在 API 输入中）
            label = f"[Result of {m.tool_name}]"
            result.append({"role": "user", "content": f"{label}\n{m.content}"})
        elif m.role == "snip_boundary":
            result.append({"role": "system", "content": f"[Boundary] {m.content}"})
    return result


def call_api(
    api_key: str, base_url: str, model: str, messages: list[dict], max_retries: int = 2,
) -> dict | None:
    """调用 LLM API，返回响应 JSON 或 None。"""
    body = {
        "model": model,
        "max_tokens": 100,
        "messages": messages,
    }
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=60,
                verify=False,  # 本地 HTTPS 代理需要跳过 SSL 校验
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            print(f"        [ERROR] API 请求失败: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"        响应: {e.response.text[:300]}")
            return None


def build_test_conversation() -> list[ChatMessage]:
    """构造一个长对话，模拟 Coding Agent 调用工具产生长输出的场景。

    每轮: user → assistant_tool_call → tool_result(>200 chars) → assistant
    这样 Microcompact 能截断 tool_result，Snip 能删除中间段。
    """
    msgs: list[ChatMessage] = [
        ChatMessage(
            role="system",
            content="You are MiniCode, an AI coding assistant. You help users with coding tasks, "
            "file operations, and command execution in a Python project.",
        ),
    ]

    # 每轮模拟一次工具调用链
    for i in range(15):
        # User 提问
        msgs.append(ChatMessage(
            role="user",
            content=f"Task {i}: Analyze the file src/module_{i}.py and run its tests.",
        ))

        # 模拟 read_file 工具调用
        msgs.append(ChatMessage(
            role="assistant_tool_call",
            tool_use_id=f"read_{i}",
            tool_name="read_file",
            input={"path": f"src/module_{i}.py"},
            content="",
        ))

        # tool_result: 读文件的长输出 (>200 chars，Microcompact 会截断)
        file_lines = "\n".join(
            f"def func_{j}(): return {j * i}" for j in range(50)
        )
        msgs.append(ChatMessage(
            role="tool_result",
            tool_use_id=f"read_{i}",
            tool_name="read_file",
            content=f"# src/module_{i}.py\n{file_lines}\n# end of file\n"
            + "X" * 2000,
        ))

        # Assistant 中间回复
        msgs.append(ChatMessage(
            role="assistant",
            content=f"I've read module_{i}.py. It has ~50 functions. "
            + f"Now let me run the tests." + "y" * 100,
        ))

        # 模拟 run_command 工具调用
        msgs.append(ChatMessage(
            role="assistant_tool_call",
            tool_use_id=f"test_{i}",
            tool_name="run_command",
            input={"command": f"pytest src/test_module_{i}.py -v"},
            content="",
        ))

        # tool_result: 测试输出的长内容
        test_output = "\n".join(
            f"test_case_{k}: {'PASSED' if k % 5 != 0 else 'FAILED'}"
            for k in range(40)
        )
        msgs.append(ChatMessage(
            role="tool_result",
            tool_use_id=f"test_{i}",
            tool_name="run_command",
            content=f"Running tests for module_{i}...\n{test_output}\n"
            + "Y" * 2000,
        ))

        # Assistant 总结
        msgs.append(ChatMessage(
            role="assistant",
            content=f"Results for module_{i}: " + "z" * 50,
        ))

    return msgs


def main():
    print("=" * 60)
    print("  MiniCode 三层上下文压缩 — A/B 对照测试")
    print("  真实 API 调用，对比压缩效果")
    print("=" * 60)

    # ── 加载配置 ──
    config = load_config()
    if not config["api_key"]:
        print("\n[ERROR] 没有配置 API Key。请设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY。")
        print("  或在 .minicode/settings.json 中配置 api_key。")
        sys.exit(1)

    print(f"\n  模型: {config['model']}")
    print(f"  API:  {config['base_url']}")
    print()

    # ── 构造测试对话 ──
    print("  [1/5] 构造测试对话...")
    messages = build_test_conversation()
    raw_tokens = count_messages_tokens(messages)
    print(f"        共 {len(messages)} 条消息, 本地估算 {raw_tokens:,} tokens")

    # ── 压缩 ──
    print("  [2/5] 应用三层压缩...")
    compressed = apply_compression(messages)
    compressed_tokens = count_messages_tokens(compressed)
    local_savings = (1 - compressed_tokens / raw_tokens) * 100 if raw_tokens else 0
    print(f"        压缩后 {len(compressed)} 条消息, {compressed_tokens:,} tokens")
    print(f"        本地估算节省: {local_savings:.1f}%")

    mc_count = sum(1 for m in compressed if getattr(m, "_compacted", False))
    if mc_count:
        print(f"        Microcompact 截断: {mc_count} 条")
    if len(compressed) < len(messages):
        print(f"        Snip 删除: {len(messages) - len(compressed)} 条")

    # ── 转换为 OpenAI 格式 ──
    msgs_a = messages_to_openai(messages)
    msgs_b = messages_to_openai(compressed)

    # ── 实验 A: 无压缩 ──
    print(f"\n  [3/5] 实验 A: 无压缩 → 发送 {len(msgs_a)} 条({raw_tokens:,} tokens)...")
    start_a = time.time()
    resp_a = call_api(config["api_key"], config["base_url"], config["model"], msgs_a)
    duration_a = time.time() - start_a

    if resp_a is None:
        print("\n[ERROR] 实验 A 失败，终止测试。")
        sys.exit(1)

    usage_a = resp_a.get("usage", {})
    content_a = resp_a.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"        API 输入 Token: {usage_a.get('prompt_tokens', 'N/A'):>6}")
    print(f"        API 输出 Token: {usage_a.get('completion_tokens', 'N/A'):>6}")
    print(f"        耗时: {duration_a:.2f}s")
    print(f"        模型回复: {content_a[:100]}...")

    # ── 实验 B: 有压缩 ──
    print(f"\n  [4/5] 实验 B: 开启压缩 → 发送 {len(msgs_b)} 条({compressed_tokens:,} tokens)...")
    start_b = time.time()
    resp_b = call_api(config["api_key"], config["base_url"], config["model"], msgs_b)
    duration_b = time.time() - start_b

    if resp_b is None:
        print("\n[ERROR] 实验 B 失败，终止测试。")
        sys.exit(1)

    usage_b = resp_b.get("usage", {})
    content_b = resp_b.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"        API 输入 Token: {usage_b.get('prompt_tokens', 'N/A'):>6}")
    print(f"        API 输出 Token: {usage_b.get('completion_tokens', 'N/A'):>6}")
    print(f"        耗时: {duration_b:.2f}s")
    print(f"        模型回复: {content_b[:100]}...")

    # ── 对比结果 ──
    print(f"\n  [5/5] 生成对比报告...")

    in_a = usage_a.get("prompt_tokens", 0) or 0
    out_a = usage_a.get("completion_tokens", 0) or 0
    in_b = usage_b.get("prompt_tokens", 0) or 0
    out_b = usage_b.get("completion_tokens", 0) or 0

    token_savings = (1 - in_b / in_a) * 100 if in_a else 0
    time_savings = (1 - duration_b / duration_a) * 100 if duration_a else 0

    # 成本估算（DeepSeek 约 $0.5/M input, $2/M output）
    cost_a = (in_a * 0.5 + out_a * 2) / 1_000_000
    cost_b = (in_b * 0.5 + out_b * 2) / 1_000_000
    cost_savings = (1 - cost_b / cost_a) * 100 if cost_a else 0

    print()
    print("=" * 60)
    print("  A/B 测试结果对比")
    print("=" * 60)
    print(f"  {'指标':<25} {'A (无压缩)':<18} {'B (三层压缩)':<18}")
    print(f"  {'-'*25} {'-'*18} {'-'*18}")
    print(f"  {'消息数':<25} {len(msgs_a):<18} {len(msgs_b):<18}")
    print(f"  {'API 输入 Token':<25} {in_a:<18,} {in_b:<18,}")
    print(f"  {'API 输出 Token':<25} {out_a:<18,} {out_b:<18,}")
    print(f"  {'总 Token':<25} {in_a+out_a:<18,} {in_b+out_b:<18,}")
    print(f"  {'响应耗时 (s)':<25} {duration_a:<18.2f} {duration_b:<18.2f}")
    print(f"  {'估算成本 ($)':<25} ${cost_a:<17.5f} ${cost_b:<17.5f}")
    print(f"  {'─'*25} {'─'*18} {'─'*18}")
    print(f"  {'Token 节省率':<25} {'──':<18} {token_savings:<17.1f}%")
    print(f"  {'响应加速':<25} {'──':<18} {time_savings:<17.1f}%")
    print(f"  {'成本节省':<25} {'──':<18} {cost_savings:<17.1f}%")
    print("=" * 60)

    # JSON 输出
    result = {
        "model": config["model"],
        "base_url": config["base_url"],
        "messages_before": len(msgs_a),
        "messages_after": len(msgs_b),
        "experiment_a": {
            "input_tokens": in_a,
            "output_tokens": out_a,
            "duration_s": round(duration_a, 2),
            "cost": round(cost_a, 6),
        },
        "experiment_b": {
            "input_tokens": in_b,
            "output_tokens": out_b,
            "duration_s": round(duration_b, 2),
            "cost": round(cost_b, 6),
        },
        "savings": {
            "token_savings_pct": round(token_savings, 1),
            "time_savings_pct": round(time_savings, 1),
            "cost_savings_pct": round(cost_savings, 1),
        },
        "local_estimate": {
            "tokens_before": raw_tokens,
            "tokens_after": compressed_tokens,
            "savings_pct": round(local_savings, 1),
        },
    }

    result_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "benchmark_ab_result.json",
    )
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  [OK] 详细结果已保存: {result_path}")


if __name__ == "__main__":
    main()
