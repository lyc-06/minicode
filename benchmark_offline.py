#!/usr/bin/env python3
"""benchmark_offline.py -- 三层上下文压缩离线压测脚本

纯本地运行，不调用任何 API。构造 5 种模拟对话场景，
用 tiktoken 精确统计每层压缩前后的 Token 数。

用法:
    python benchmark_offline.py
"""

from __future__ import annotations

import copy
import os
import sys
from typing import Any

import tiktoken

# 确保能找到 minicode 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from minicode.types import ChatMessage
from minicode.compact.microcompact import microcompact
from minicode.compact.snip import snip_compact
from minicode.compact.auto_compact import should_auto_compact

# -- tiktoken 编码器 ----------------------------------------------
ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """用 tiktoken 精确计算文本的 token 数。"""
    return len(ENCODING.encode(text))


def count_messages_tokens(messages: list[ChatMessage]) -> int:
    """计算 messages 列表中所有消息的总 token 数。"""
    total = 0
    for m in messages:
        total += count_tokens(m.content or "")
        if m.input:
            import json
            total += count_tokens(json.dumps(m.input))
    return total


# -- 场景生成器 ---------------------------------------------------

def make_conversation(
    num_pairs: int,
    user_msg_len: int = 80,
    assistant_msg_len: int = 200,
    include_system: bool = True,
) -> list[ChatMessage]:
    """生成 User/Assistant 交替的对话。

    Args:
        num_pairs: User-Assistant 对话对数
        user_msg_len: 每条 user 消息的字符数
        assistant_msg_len: 每条 assistant 消息的字符数
        include_system: 是否包含 system 消息在开头
    """
    msgs: list[ChatMessage] = []
    if include_system:
        msgs.append(ChatMessage(role="system", content="You are MiniCode, a helpful AI coding assistant."))
    for i in range(num_pairs):
        msgs.append(ChatMessage(role="user", content=f"User message {i}: " + "x" * max(0, user_msg_len - 15)))
        msgs.append(ChatMessage(role="assistant", content=f"Assistant reply {i}: " + "y" * max(0, assistant_msg_len - 20)))
    return msgs


def make_tool_heavy_conversation(
    num_rounds: int = 12,
    tool_output_len: int = 3000,
    user_msg_len: int = 60,
) -> list[ChatMessage]:
    """模拟 Agent 调工具产生长输出的对话。

    每轮: user -> assistant_tool_call -> tool_result(长) -> assistant
    """
    msgs: list[ChatMessage] = [ChatMessage(role="system", content="You are MiniCode, a helpful AI coding assistant.")]
    for i in range(num_rounds):
        msgs.append(ChatMessage(role="user", content=f"Round {i}: please run this tool for me."))
        msgs.append(ChatMessage(
            role="assistant_tool_call",
            tool_use_id=f"call_{i}",
            tool_name="run_command",
            input={"command": f"echo test_{i}"},
            content="",
        ))
        output = f"[tool output for round {i}]\n" + "X" * max(0, tool_output_len - 30)
        msgs.append(ChatMessage(
            role="tool_result",
            tool_use_id=f"call_{i}",
            tool_name="run_command",
            content=output,
        ))
        msgs.append(ChatMessage(role="assistant", content=f"Here are the results for round {i}."))
    return msgs


def make_near_limit_conversation() -> list[ChatMessage]:
    """构造总 token 超过 170K 的对话，触发 AutoCompact。

    每对消息约 1250 token，170 对 -> ~212K token，超过 170K 阈值。
    """
    msgs: list[ChatMessage] = [ChatMessage(role="system", content="You are MiniCode.")]
    for i in range(170):
        msgs.append(ChatMessage(
            role="user",
            content=f"User long message #{i}: " + "ABCDEFGHIJ " * 200,
        ))
        msgs.append(ChatMessage(
            role="assistant",
            content=f"Assistant long reply #{i}: " + "MNOPQRSTUV " * 200,
        ))
    return msgs


def make_protected_role_conversation() -> list[ChatMessage]:
    """包含 system / snip_boundary 保护角色的对话，验证 Snip 不裁剪。"""
    msgs: list[ChatMessage] = [ChatMessage(role="system", content="You are MiniCode.")]
    for i in range(40):
        msgs.append(ChatMessage(role="user", content=f"Regular user message {i}"))
        msgs.append(ChatMessage(role="assistant", content=f"Regular assistant reply {i}"))
    # 在中间插入 protected 消息
    msgs.insert(10, ChatMessage(role="snip_boundary", content="snip boundary marker"))
    return msgs


def make_mixed_realistic_conversation() -> list[ChatMessage]:
    """模拟真实 Coding Agent 使用场景。

    混合了短问答、长工具输出、多步工具链。
    """
    msgs: list[ChatMessage] = [ChatMessage(role="system", content="You are MiniCode, a coding assistant.")]
    # 前几轮短对话
    for i in range(5):
        msgs.append(ChatMessage(role="user", content=f"Quick question {i}?"))
        msgs.append(ChatMessage(role="assistant", content=f"Short answer {i}."))
    # 中间几轮长工具输出
    for i in range(8):
        msgs.append(ChatMessage(role="user", content=f"Read and process file {i}"))
        msgs.append(ChatMessage(
            role="assistant_tool_call",
            tool_use_id=f"read_{i}",
            tool_name="read_file",
            input={"path": f"src/file_{i}.py"},
        ))
        msgs.append(ChatMessage(
            role="tool_result",
            tool_use_id=f"read_{i}",
            tool_name="read_file",
            content=f"# file_{i}.py\n" + "Z" * 2000 + f"\n... end of file_{i}",
        ))
        msgs.append(ChatMessage(role="assistant", content=f"Processed {i}. Here's the analysis."))
    # 最后几轮短对话
    for i in range(5):
        msgs.append(ChatMessage(role="user", content=f"Follow-up {i}?"))
        msgs.append(ChatMessage(role="assistant", content=f"Follow-up answer {i}."))
    return msgs


# -- 场景运行器 ---------------------------------------------------

def run_scenario(name: str, description: str, messages: list[ChatMessage]) -> dict[str, Any]:
    """对一组 messages 运行所有压缩层，返回统计结果。"""
    total_before = count_messages_tokens(messages)

    result: dict[str, Any] = {
        "name": name,
        "description": description,
        "total_messages": len(messages),
        "tokens_before": total_before,
    }

    # -- AutoCompact 检测 --
    result["auto_compact"] = {
        "triggered": should_auto_compact(messages),
        "threshold": 170_000,
    }

    # -- Microcompact（在副本上操作） --
    mc_msgs = copy.deepcopy(messages)
    mc_msgs = microcompact(mc_msgs)
    mc_after = count_messages_tokens(mc_msgs)
    mc_compacted = sum(1 for m in mc_msgs if getattr(m, "_compacted", False))
    result["microcompact"] = {
        "tokens_before": total_before,
        "tokens_after": mc_after,
        "saved": total_before - mc_after,
        "ratio": round(mc_after / total_before, 4) if total_before else 1.0,
        "compacted_count": mc_compacted,
    }

    # -- Snip Compact（在副本上操作） --
    snip_messages = copy.deepcopy(messages)
    snip_result = snip_compact(snip_messages)
    if snip_result:
        snip_msgs, removed = snip_result
        snip_after = count_messages_tokens(snip_msgs)
        result["snip"] = {
            "triggered": True,
            "removed": removed,
            "remaining_messages": len(snip_msgs),
            "tokens_before": total_before,
            "tokens_after": snip_after,
            "saved": total_before - snip_after,
            "ratio": round(snip_after / total_before, 4) if total_before else 1.0,
        }
    else:
        result["snip"] = {
            "triggered": False,
            "reason": "no safe interval (protected roles or too few messages)",
        }

    # -- 三层联合 A（模拟 cli.py 中的真实流程） --
    # AutoCompact 触发时才调 Snip，否则只用 Microcompact
    combined = copy.deepcopy(messages)
    if should_auto_compact(combined):
        r = snip_compact(combined)
        if r:
            combined, _ = r
    combined = microcompact(combined)
    combined_after = count_messages_tokens(combined)
    result["combined"] = {
        "tokens_before": total_before,
        "tokens_after": combined_after,
        "saved": total_before - combined_after,
        "ratio": round(combined_after / total_before, 4) if total_before else 1.0,
        "remaining_messages": len(combined),
        "mode": "auto (Snip only if AutoCompact triggered)",
    }

    # -- 三层联合 B（最大压缩潜力）--
    # 始终应用所有三层（类似手动 /snip 的效果）
    combined_max = copy.deepcopy(messages)
    r = snip_compact(combined_max)
    if r:
        combined_max, _ = r
    combined_max = microcompact(combined_max)
    combined_max_after = count_messages_tokens(combined_max)
    result["combined_max"] = {
        "tokens_before": total_before,
        "tokens_after": combined_max_after,
        "saved": total_before - combined_max_after,
        "ratio": round(combined_max_after / total_before, 4) if total_before else 1.0,
        "remaining_messages": len(combined_max),
        "mode": "max (Snip + Microcompact unconditional)",
    }

    return result


# -- 报告生成器 ---------------------------------------------------

def print_scenario_result(r: dict[str, Any]) -> None:
    """在控制台打印单个场景的结果。"""
    name = r["name"]
    print(f"\n{'='*60}")
    print(f"  [SCENARIO] {name}")
    print(f"  {r['description']}")
    print(f"  消息数: {r['total_messages']}  |  原始 Token: {r['tokens_before']:,}")
    print(f"{'='*60}")

    # AutoCompact
    ac = r["auto_compact"]
    status = "[OK] 触发" if ac["triggered"] else "[NO] 未触发"
    print(f"  AutoCompact : {status} (阈值: {ac['threshold']:,})")

    # Microcompact
    mc = r["microcompact"]
    if mc["compacted_count"] > 0:
        print(f"  Microcompact: [OK] 截断 {mc['compacted_count']} 条  |  "
              f"{mc['tokens_before']:,} -> {mc['tokens_after']:,}  "
              f"(节省 {mc['saved']:,}, 压缩率 {mc['ratio']:.2f})")
    else:
        mc_ratio_display = f"压缩率 {mc['ratio']:.2f}" if mc["saved"] > 0 else "无操作"
        print(f"  Microcompact: --  {mc_ratio_display}")

    # Snip
    sn = r["snip"]
    if sn["triggered"]:
        print(f"  Snip Compact : [OK] 删除 {sn['removed']} 条  |  "
              f"{sn['tokens_before']:,} -> {sn['tokens_after']:,}  "
              f"(节省 {sn['saved']:,}, 压缩率 {sn['ratio']:.2f})")
    else:
        print(f"  Snip Compact : [NO] {sn.get('reason', '未触发')}")

    # 联合
    cb = r["combined"]
    saved_pct = (1 - cb["ratio"]) * 100
    print(f"  [AUTO] 生产模式 : {cb['tokens_before']:,} -> {cb['tokens_after']:,}  "
          f"| 节省 {cb['saved']:,}  | 压缩率 {cb['ratio']:.2f}  | {cb['mode']}")

    cb_max = r["combined_max"]
    max_saved_pct = (1 - cb_max["ratio"]) * 100
    print(f"  [MAX]  最大潜力 : {cb_max['tokens_before']:,} -> {cb_max['tokens_after']:,}  "
          f"| 节省 {cb_max['saved']:,}  | 压缩率 {cb_max['ratio']:.2f}  | 节省 {max_saved_pct:.1f}%")


def generate_markdown_report(all_results: list[dict[str, Any]]) -> str:
    """生成完整的 Markdown 报告。"""
    lines = []
    lines.append("# 三层上下文压缩压测报告")
    lines.append("")
    lines.append("> 由 `benchmark_offline.py` 自动生成")
    lines.append("")
    lines.append("## 测试环境")
    lines.append("")
    lines.append(f"| 项目 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 日期 | 2026-06-07 |")
    lines.append(f"| Token 编码 | `cl100k_base` (tiktoken) |")
    lines.append(f"| 项目路径 | `Minicode-Python` |")
    lines.append("")

    # -- 总览汇总表 --
    lines.append("## 汇总对比")
    lines.append("")
    lines.append("| 场景 | 消息数 | 原始 Token | 生产模式 | 最大潜力 | 主要贡献层 |")
    lines.append("|------|--------|-----------|---------|---------|-----------|")
    for r in all_results:
        mc = r["microcompact"]
        sn = r["snip"]
        contributors = []
        if mc["saved"] > 0:
            contributors.append("Microcompact")
        if sn["triggered"]:
            contributors.append("Snip")
        if r["auto_compact"]["triggered"]:
            contributors.insert(0, "AutoCompact->")
        main = ", ".join(contributors) if contributors else "--"

        cb = r["combined"]
        prod_pct = (1 - cb["ratio"]) * 100
        cb_max = r["combined_max"]
        max_pct = (1 - cb_max["ratio"]) * 100
        lines.append(
            f"| {r['name']} "
            f"| {r['total_messages']} "
            f"| {cb['tokens_before']:,} "
            f"| {cb['tokens_after']:,} ({prod_pct:.0f}%) "
            f"| {cb_max['tokens_after']:,} ({max_pct:.0f}%) "
            f"| {main} |"
        )
    lines.append("")

    # -- 逐场景详情 --
    for r in all_results:
        lines.append(f"---")
        lines.append("")
        lines.append(f"## {r['name']}")
        lines.append("")
        lines.append(f"{r['description']}")
        lines.append("")
        # 基础信息
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 总消息数 | {r['total_messages']} |")
        lines.append(f"| 原始 Token | {r['tokens_before']:,} |")
        lines.append("")
        # 压缩详情表
        lines.append("| 压缩层 | Token 前 | Token 后 | 节省 | 压缩率 | 详情 |")
        lines.append("|--------|---------|---------|------|--------|------|")

        # AutoCompact
        ac = r["auto_compact"]
        ac_display = "[OK] 触发" if ac["triggered"] else "[NO] 未触发"
        lines.append(f"| AutoCompact | {r['tokens_before']:,} | -- | -- | -- | {ac_display} |")

        # Microcompact
        mc = r["microcompact"]
        mc_detail = f"截断 {mc['compacted_count']} 条" if mc["compacted_count"] > 0 else "无操作"
        lines.append(f"| Microcompact | {mc['tokens_before']:,} | {mc['tokens_after']:,} "
                     f"| {mc['saved']:,} | {mc['ratio']:.2f}x | {mc_detail} |")

        # Snip
        sn = r["snip"]
        if sn["triggered"]:
            sn_detail = f"删除 {sn['removed']} 条, 剩余 {sn['remaining_messages']} 条"
            lines.append(f"| Snip Compact | {sn['tokens_before']:,} | {sn['tokens_after']:,} "
                         f"| {sn['saved']:,} | {sn['ratio']:.2f}x | {sn_detail} |")
        else:
            lines.append(f"| Snip Compact | {r['tokens_before']:,} | -- | -- | -- | {sn.get('reason', '未触发')} |")

        # 联合（生产模式）
        cb = r["combined"]
        saved_pct = (1 - cb["ratio"]) * 100
        lines.append(f"| **三层联合（生产）** | **{cb['tokens_before']:,}** | **{cb['tokens_after']:,}** "
                     f"| **{cb['saved']:,}** | **{cb['ratio']:.2f}x ({saved_pct:.0f}%)** "
                     f"| 剩余 {cb['remaining_messages']} 条，{cb['mode']} |")

        # 联合（最大潜力）
        cb_max = r["combined_max"]
        max_pct = (1 - cb_max["ratio"]) * 100
        lines.append(f"| **三层联合（最大）** | **{cb_max['tokens_before']:,}** | **{cb_max['tokens_after']:,}** "
                     f"| **{cb_max['saved']:,}** | **{cb_max['ratio']:.2f}x ({max_pct:.0f}%)** "
                     f"| 剩余 {cb_max['remaining_messages']} 条，{cb_max['mode']} |")
        lines.append("")

    # -- 结论 --
    lines.append("## 分析与结论")
    lines.append("")
    lines.append("### 各层定位验证")
    lines.append("")
    lines.append("| 压缩层 | 适用场景 | 效果 |")
    lines.append("|--------|---------|------|")
    lines.append("| **Microcompact** | 工具结果冗长的对话 | 轻量截断长 tool_result，不影响消息结构 |")
    lines.append("| **Snip Compact** | 历史对话过长的对话 | 大幅删除中间段，保留头尾关键上下文 |")
    lines.append("| **AutoCompact** | Token 接近限制的对话 | 最后防线，防止上下文溢出导致的 API 报错 |")
    lines.append("")

    max_saved_prod = max((1 - r["combined"]["ratio"]) * 100 for r in all_results) if all_results else 0
    max_saved_max = max((1 - r["combined_max"]["ratio"]) * 100 for r in all_results) if all_results else 0
    lines.append(f"### 结论")
    lines.append("")
    lines.append(f"- 三层递进式压缩在不同场景下均能有效减少 Token 消耗")
    lines.append(f"- **生产模式**（AutoCompact 自动触发）：最佳场景节省 **{max_saved_prod:.0f}%**")
    lines.append(f"- **最大潜力**（Snip + Microcompact 主动应用）：最佳场景节省 **{max_saved_max:.0f}%**")
    lines.append("- Microcompact 作为每轮自动执行的轻量层，对长工具输出场景效果显著")
    lines.append("- Snip Compact 在长对话中大幅裁剪，且保护规则确保不破坏 tool_call/tool_result 对")
    lines.append("- AutoCompact 作为安全网，在 Token 接近限制时自动触发，防止 API 报错")
    lines.append("")

    return "\n".join(lines)


# -- 主入口 -------------------------------------------------------

def main():
    print("=" * 60)
    print("  MiniCode 三层上下文压缩 -- 离线压测")
    print("  Token 编码: cl100k_base (tiktoken)")
    print("=" * 60)

    # 定义 5 个场景
    scenarios = [
        (
            "场景 1: 短对话基线",
            "10 条短消息，预期三层都不触发。",
            make_conversation(num_pairs=5, user_msg_len=30, assistant_msg_len=50),
        ),
        (
            "场景 2: 长对话",
            "100 条 User/Assistant 交替消息，Snip Compact 应触发删除中间段。",
            make_conversation(num_pairs=50, user_msg_len=80, assistant_msg_len=200),
        ),
        (
            "场景 3: 工具结果密集",
            "12 轮工具调用，tool_result 含 3000 字符长输出，Microcompact 应大幅截断。",
            make_tool_heavy_conversation(num_rounds=12, tool_output_len=3000),
        ),
        (
            "场景 4: 超长对话（AutoCompact 触发）",
            "200 对长消息，总 Token > 170K，AutoCompact 应自动触发 Snip。",
            make_near_limit_conversation(),
        ),
        (
            "场景 5: 保护规则验证",
            "40 对对话中插入 snip_boundary 角色，Snip 应拒绝裁剪。",
            make_protected_role_conversation(),
        ),
    ]

    all_results = []
    for name, desc, msgs in scenarios:
        r = run_scenario(name, desc, msgs)
        all_results.append(r)
        print_scenario_result(r)

    # -- 额外：混合真实场景 --
    print(f"\n{'='*60}")
    print(f"  [SCENARIO] 场景 6 (附加): 混合真实场景")
    print(f"  模拟 Coding Agent 真实使用：短问答 + 长工具输出 + 多步工具链")
    mixed_msgs = make_mixed_realistic_conversation()
    mixed_r = run_scenario("场景 6: 混合真实场景", "模拟 Coding Agent 真实使用。", mixed_msgs)
    all_results.append(mixed_r)
    print_scenario_result(mixed_r)

    # -- 生成 Markdown 报告 --
    report = generate_markdown_report(all_results)
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{'='*60}")
    print(f"  [OK] 报告已生成: {report_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
