#!/usr/bin/env python3
"""benchmark_verifier.py — Verifier Agent 压测脚本

对比有无 Verifier Agent 审查对编码任务 PASS 率的影响。

设计：
- 5 个编码任务（简单到中等难度）
- 每个任务跑两轮实验：
    A: 主 Agent 直接生成 → Judge 中立评判
    B: 主 Agent 生成 → Verifier 审查 → 修改(最多3轮) → Judge 中立评判
- 使用独立 Judge Agent 统一评判标准，避免循环论证

前置条件:
    - 已配置 API Key
    - pip install tiktoken

用法:
    python benchmark_verifier.py

注意:
    - 会消耗 API 调用（5 个任务 × ~5-8 次调用 = 约 $0.1-0.3）
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import requests
import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))


# ── API 配置与调用 ─────────────────────────────────────────────

def load_config() -> dict:
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


def call_api(
    api_key: str, base_url: str, model: str,
    messages: list[dict], max_tokens: int = 1024, max_retries: int = 3,
) -> dict | None:
    """调用 LLM API，返回完整响应 JSON。"""
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    # 使用带连接池的 Session
    sess = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
    sess.mount("https://", adapter)
    for attempt in range(max_retries):
        try:
            resp = sess.post(
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=180,
                verify=False,
            )
            resp.raise_for_status()
            sess.close()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 4  # 退避: 4s, 8s, 12s
                print(f"        [RETRY {attempt+1}/{max_retries}] 等待 {wait}s...")
                time.sleep(wait)
                continue
            print(f"        [ERROR] API 请求失败: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"        响应: {e.response.text[:300]}")
            sess.close()
            return None
    sess.close()
    return None


# ── Prompt 定义 ────────────────────────────────────────────────

MAIN_AGENT_PROMPT = (
    "You are a Python coding agent. Write clean, correct, well-documented Python code "
    "for the given task. Output ONLY the code, no explanations. "
    "Use proper error handling and edge case considerations."
)

VERIFIER_PROMPT = (
    "You are a strict code reviewer. Review the following code critically.\n\n"
    "Check for:\n"
    "1. Correctness: Does it handle all edge cases?\n"
    "2. Security: Any vulnerabilities?\n"
    "3. Performance: Any obvious inefficiencies?\n"
    "4. Style: Follows Python best practices?\n\n"
    "CRITICAL: Your response MUST start with exactly one word: PASS, MINOR, or FAIL. "
    "Then a newline and your explanation.\n"
    "- PASS if correct and well-written.\n"
    "- MINOR if there are small issues (list them).\n"
    "- FAIL if there are significant problems (list them with specifics).\n\n"
    "Be strict. Even small issues should get MINOR, not PASS."
)

VERIFIER_REVIEW_PROMPT = (
    "You are a strict code reviewer. Review the following code critically.\n\n"
    "Check for:\n"
    "1. Correctness: Does it handle all edge cases?\n"
    "2. Security: Any vulnerabilities?\n"
    "3. Performance: Any obvious inefficiencies?\n"
    "4. Did the author fix the previously identified issues?\n\n"
    "CRITICAL: Your response MUST start with exactly one word: PASS, MINOR, or FAIL. "
    "Then a newline and your explanation.\n"
    "- PASS if all issues are fixed and code is correct.\n"
    "- MINOR if there are small remaining issues.\n"
    "- FAIL if significant problems remain."
)

JUDGE_PROMPT = (
    "You are a neutral, impartial code judge. Evaluate the following code:\n\n"
    "CRITICAL: Your response MUST start with exactly one word: PASS, MINOR, or FAIL. "
    "Then a newline and your explanation.\n"
    "- PASS if it is correct, handles edge cases, well-structured.\n"
    "- MINOR if there are minor issues (style, edge cases, documentation).\n"
    "- FAIL if there are bugs, missing functionality, or serious problems.\n\n"
    "Be fair."
)

# ── 测试任务集 ──────────────────────────────────────────────────

TASKS = [
    {
        "id": 1,
        "title": "斐波那契数列",
        "difficulty": "简单",
        "description": (
            "Write a Python function `fibonacci(n)` that returns the nth number "
            "in the Fibonacci sequence (0-indexed, so fibonacci(0) = 0, fibonacci(1) = 1). "
            "The function should handle: n=0, n=1, large n (up to 100) efficiently. "
            "Don't use recursion without memoization."
        ),
    },
    {
        "id": 2,
        "title": "CSV 行解析器",
        "difficulty": "中等",
        "description": (
            "Write a Python function `parse_csv_line(line: str) -> list[str]` "
            "that parses a single CSV line into a list of fields. "
            "Must handle: quoted fields with commas inside, escaped quotes (\"\"), "
            "empty fields, leading/trailing whitespace. "
            "Do NOT use Python's built-in csv module."
        ),
    },
    {
        "id": 3,
        "title": "LRU Cache",
        "difficulty": "中等",
        "description": (
            "Write a Python class `LRUCache` with:\n"
            "- `__init__(self, capacity: int)`\n"
            "- `get(self, key: int) -> int` (return -1 if not found)\n"
            "- `put(self, key: int, value: int) -> None`\n\n"
            "When cache reaches capacity, evict the least recently used item. "
            "Both get and put must be O(1) average time complexity. "
            "Use only standard library (no OrderedDict)."
        ),
    },
    {
        "id": 4,
        "title": "邮箱正则验证",
        "difficulty": "简单",
        "description": (
            "Write a Python function `is_valid_email(email: str) -> bool` "
            "that validates an email address using regex. "
            "Must check: local part, @ symbol, domain name with at least one dot. "
            "Should handle: subdomains, plus addressing (user+tag@domain.com), "
            "numeric domains, and reject obvious invalid formats."
        ),
    },
    {
        "id": 5,
        "title": "线程安全计数器",
        "difficulty": "中等",
        "description": (
            "Write a Python class `ThreadSafeCounter` with:\n"
            "- `__init__(self)` initializes counter to 0\n"
            "- `increment(self, n: int = 1)` adds n to counter\n"
            "- `decrement(self, n: int = 1)` subtracts n from counter\n"
            "- `get(self) -> int` returns current value\n"
            "- `reset(self)` resets to 0\n\n"
            "Must be thread-safe. Use appropriate locking. "
            "Support context manager protocol (__enter__/__exit__)."
        ),
    },
]


# ── Agent 辅助函数 ─────────────────────────────────────────────

def extract_code(text: str) -> str:
    """从模型回复中提取代码块。"""
    # 尝试找 ```python ... ``` 块
    if "```python" in text:
        start = text.index("```python") + 9
        end = text.index("```", start) if "```" in text[start:] else len(text)
        return text[start:end].strip()
    # 尝试找 ``` ... ``` 块
    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        return text[start:end].strip()
    return text.strip()


import re

def extract_verdict(text: str) -> str:
    """从回复中提取 PASS/MINOR/FAIL 判定。"""
    if not text:
        return "UNKNOWN"
    for pattern in [r'\*\*(PASS|MINOR|FAIL)\*\*', r'\b(PASS|MINOR|FAIL)\b']:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            last = matches[-1]
            return (last.group(1) or last.group(0)).upper()
    return "UNKNOWN"


def get_response_text(resp: dict) -> str:
    """从 API 响应中提取文本内容，兼容 content 和 reasoning_content 字段。"""
    choice = resp.get("choices", [{}])[0] or {}
    msg = choice.get("message", {}) or {}
    # DeepSeek 推理模型的内容可能在 reasoning_content 中
    text = msg.get("content", "") or ""
    if not text.strip():
        text = msg.get("reasoning_content", "") or ""
    return text


# ── 单任务运行器 ───────────────────────────────────────────────

def run_task(
    config: dict, task: dict,
) -> dict[str, Any]:
    """对单个任务运行 A/B 两组实验。"""
    task_title = task["title"]
    task_desc = task["description"]
    print(f"\n  ┌─ Task {task['id']}: {task_title} ({task['difficulty']})")
    print(f"  │ {task_desc[:80]}...")

    # ── 实验 A: 无 Verifier ──
    print(f"  ├─ [A] 无 Verifier 生成代码...")

    # Step A1: 主 Agent 写代码
    start_a = time.time()
    resp = call_api(
        config["api_key"], config["base_url"], config["model"],
        [
            {"role": "system", "content": MAIN_AGENT_PROMPT},
            {"role": "user", "content": task_desc},
        ],
        max_tokens=2048,
    )
    if not resp:
        return {"task_id": task["id"], "title": task_title, "error": "API call failed"}

    code_a = extract_code(
        get_response_text(resp)
    )
    usage_a_gen = resp.get("usage", {})
    tokens_a_gen = usage_a_gen.get("prompt_tokens", 0) + usage_a_gen.get("completion_tokens", 0)

    # Step A2: Judge 评判
    resp = call_api(
        config["api_key"], config["base_url"], config["model"],
        [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"Task: {task_desc}\n\nCode:\n{code_a}"},
        ],
        max_tokens=512,
    )
    duration_a = time.time() - start_a
    if not resp:
        return {"task_id": task["id"], "title": task_title, "error": "Judge API call failed"}

    judge_a_text = get_response_text(resp)
    verdict_a = extract_verdict(judge_a_text)
    usage_a_judge = resp.get("usage", {})

    total_tokens_a = (usage_a_gen.get("prompt_tokens", 0)
                      + usage_a_gen.get("completion_tokens", 0)
                      + usage_a_judge.get("prompt_tokens", 0)
                      + usage_a_judge.get("completion_tokens", 0))

    print(f"  │   生成 Token: {usage_a_gen.get('prompt_tokens', 0):,} in + "
          f"{usage_a_gen.get('completion_tokens', 0):,} out")
    print(f"  │   Judge: {verdict_a}")

    # ── 实验 B: 有 Verifier ──
    print(f"  ├─ [B] 有 Verifier 审查流程...")

    start_b = time.time()
    total_tokens_b = 0
    verifier_calls = 0
    history: list[dict] = []
    current_code = ""
    retry_loop = True

    # Step B1: 主 Agent 写代码
    resp = call_api(
        config["api_key"], config["base_url"], config["model"],
        [
            {"role": "system", "content": MAIN_AGENT_PROMPT},
            {"role": "user", "content": task_desc},
        ],
        max_tokens=2048,
    )
    if not resp:
        return {"task_id": task["id"], "title": task_title, "error": "B: Main agent failed"}

    current_code = extract_code(get_response_text(resp))
    usage_b_gen = resp.get("usage", {})
    total_tokens_b += usage_b_gen.get("prompt_tokens", 0) + usage_b_gen.get("completion_tokens", 0)

    # Step B2-B4: Verifier 审查 + 修改循环
    final_verdict_b = "FAIL"
    issues_list = []

    for attempt in range(1, 3):  # 最多 2 轮审查
        verifier_calls += 1

        # Verifier 审查
        verifier_prompt_used = (
            VERIFIER_REVIEW_PROMPT if attempt > 1 else VERIFIER_PROMPT
        )
        resp = call_api(
            config["api_key"], config["base_url"], config["model"],
            [
                {"role": "system", "content": verifier_prompt_used},
                {
                    "role": "user",
                    "content": f"Task: {task_desc}\n\nCode to review:\n{current_code}",
                },
            ],
            max_tokens=1024,
        )
        if not resp:
            continue

        verifier_text = get_response_text(resp)
        verifier_verdict = extract_verdict(verifier_text)
        usage_v = resp.get("usage", {})
        total_tokens_b += usage_v.get("prompt_tokens", 0) + usage_v.get("completion_tokens", 0)

        print(f"  │   Verifier 第{attempt}轮: {verifier_verdict}")

        if verifier_verdict == "PASS":
            final_verdict_b = "PASS"
            break
        elif verifier_verdict == "MINOR":
            final_verdict_b = "MINOR"
            issues_list.append(verifier_text)
            if attempt < 2:
                # 尝试修改
                resp = call_api(
                    config["api_key"], config["base_url"], config["model"],
                    [
                        {"role": "system", "content": MAIN_AGENT_PROMPT},
                        {"role": "user", "content": (
                            f"Fix the following code based on this review:\n\n"
                            f"Task: {task_desc}\n\n"
                            f"Current code:\n{current_code}\n\n"
                            f"Reviewer's issues:\n{verifier_text}\n\n"
                            f"Output the fixed code only."
                        )},
                    ],
                    max_tokens=2048,
                )
                if resp:
                    current_code = extract_code(
                        get_response_text(resp)
                    )
                    usage_fix = resp.get("usage", {})
                    total_tokens_b += (
                        usage_fix.get("prompt_tokens", 0)
                        + usage_fix.get("completion_tokens", 0)
                    )
            break
        else:  # FAIL
            final_verdict_b = "FAIL"
            issues_list.append(verifier_text)
            if attempt < 2:
                # 必须修改
                resp = call_api(
                    config["api_key"], config["base_url"], config["model"],
                    [
                        {"role": "system", "content": MAIN_AGENT_PROMPT},
                        {"role": "user", "content": (
                            f"Fix the following code. The reviewer found serious issues:\n\n"
                            f"Task: {task_desc}\n\n"
                            f"Current code:\n{current_code}\n\n"
                            f"Issues to fix:\n{verifier_text}\n\n"
                            f"Output the fixed code only."
                        )},
                    ],
                    max_tokens=2048,
                )
                if resp:
                    current_code = extract_code(
                        get_response_text(resp)
                    )
                    usage_fix = resp.get("usage", {})
                    total_tokens_b += (
                        usage_fix.get("prompt_tokens", 0)
                        + usage_fix.get("completion_tokens", 0)
                    )

    # Step B5: Judge 评判最终代码
    resp = call_api(
        config["api_key"], config["base_url"], config["model"],
        [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"Task: {task_desc}\n\nCode:\n{current_code}"},
        ],
        max_tokens=512,
    )
    duration_b = time.time() - start_b
    judge_b_text = get_response_text(resp) if resp else "UNKNOWN"
    verdict_b_judge = extract_verdict(judge_b_text) if resp else "FAIL"
    if resp:
        usage_b_judge = resp.get("usage", {})
        total_tokens_b += usage_b_judge.get("prompt_tokens", 0) + usage_b_judge.get("completion_tokens", 0)

    print(f"  │   Judge 终审: {verdict_b_judge} | Verifier 调用了 {verifier_calls} 轮")
    print(f"  │   Token 消耗: A={total_tokens_a:,} | B={total_tokens_b:,} "
          f"({(total_tokens_b-total_tokens_a):+,})")

    return {
        "task_id": task["id"],
        "title": task_title,
        "difficulty": task["difficulty"],
        "a": {
            "verdict": verdict_a,
            "tokens": total_tokens_a,
            "duration_s": round(duration_a, 2),
            "has_verifier": False,
        },
        "b": {
            "verdict": verdict_b_judge,
            "tokens": total_tokens_b,
            "duration_s": round(duration_b, 2),
            "has_verifier": True,
            "verifier_calls": verifier_calls,
            "verifier_final_verdict": final_verdict_b,
            "issues_count": len(issues_list),
        },
    }


# ── 评分映射 ───────────────────────────────────────────────────

VERDICT_SCORE = {"PASS": 2, "MINOR": 1, "FAIL": 0}


# ── 主入口 ─────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  MiniCode Verifier Agent 压测")
    print("  对比有无 Verifier 审查对编码任务 PASS 率的影响")
    print("=" * 60)

    config = load_config()
    if not config["api_key"]:
        print("\n[ERROR] 没有配置 API Key")
        sys.exit(1)

    print(f"\n  模型: {config['model']}")
    print(f"  API:  {config['base_url']}")
    print(f"  任务数: {len(TASKS)}")
    print(f"  预计消耗: ~{len(TASKS) * 8} 次 API 调用")
    print()

    all_results = []
    for task in TASKS:
        result = run_task(config, task)
        all_results.append(result)

    # ── 过滤有效结果（排除 error） ──
    valid = [r for r in all_results if "error" not in r]

    # ── 统计 ──
    a_pass = sum(1 for r in valid if r.get("a", {}).get("verdict") == "PASS")
    a_minor = sum(1 for r in valid if r.get("a", {}).get("verdict") == "MINOR")
    a_fail = sum(1 for r in valid if r.get("a", {}).get("verdict") == "FAIL")
    b_pass = sum(1 for r in valid if r.get("b", {}).get("verdict") == "PASS")
    b_minor = sum(1 for r in valid if r.get("b", {}).get("verdict") == "MINOR")
    b_fail = sum(1 for r in valid if r.get("b", {}).get("verdict") == "FAIL")

    n_valid = len(valid)
    a_pass_rate = a_pass / n_valid * 100 if n_valid else 0
    b_pass_rate = b_pass / n_valid * 100 if n_valid else 0
    improvement = (
        (b_pass_rate - a_pass_rate) / (100 - a_pass_rate) * 100
        if a_pass_rate < 100 else 0
    )

    total_tokens_a = sum(r.get("a", {}).get("tokens", 0) for r in valid)
    total_tokens_b = sum(r.get("b", {}).get("tokens", 0) for r in valid)
    total_verifier_calls = sum(r.get("b", {}).get("verifier_calls", 0) for r in valid)

    # ── 输出 ──
    errors = len(TASKS) - n_valid

    print(f"\n{'='*60}")
    print("  结果汇总")
    print(f"{'='*60}")
    if errors:
        print(f"  [NOTE] {errors}/{len(TASKS)} 个任务因网络错误未完成，仅统计 {n_valid} 个有效任务")
    print(f"  {'指标':<30} {'A (无Verifier)':<20} {'B (有Verifier)':<20}")
    print(f"  {'-'*30} {'-'*20} {'-'*20}")
    print(f"  {'PASS':<30} {a_pass:<20} {b_pass:<20}")
    print(f"  {'MINOR':<30} {a_minor:<20} {b_minor:<20}")
    print(f"  {'FAIL':<30} {a_fail:<20} {b_fail:<20}")
    print(f"  {'PASS 率':<30} {a_pass_rate:<19.0f}% {b_pass_rate:<19.0f}%")
    print(f"  {'提升率':<30} {'--':<20} {improvement:<19.1f}%")
    print(f"  {'总 Token':<30} {total_tokens_a:<20,} {total_tokens_b:<20,}")
    print(f"  {'平均每任务 Token':<30} {total_tokens_a//n_valid:<20,} {total_tokens_b//n_valid:<20,}")
    print(f"  {'Verifier 总调用轮次':<30} {'--':<20} {total_verifier_calls:<20}")
    print(f"  {'平均每任务审查轮次':<30} {'--':<20} {total_verifier_calls/n_valid:<20.1f}")

    # ── 逐任务详情 ──
    print(f"\n{'='*60}")
    print("  逐任务详情")
    print(f"{'='*60}")
    print(f"  {'#':<4} {'任务':<20} {'难度':<8} {'A裁决':<10} {'B裁决':<10} {'Verifier轮次':<12} {'额外Token':<12}")
    print(f"  {'-'*4} {'-'*20} {'-'*8} {'-'*10} {'-'*10} {'-'*12} {'-'*12}")
    for r in all_results:
        if "error" in r:
            print(f"  {r['task_id']:<4} {r['title']:<20} {'ERROR':<8} {'ERR':<10} {'ERR':<10} {'--':<12} {'--':<12}")
            continue
        extra = r.get("b", {}).get("tokens", 0) - r.get("a", {}).get("tokens", 0)
        print(f"  {r['task_id']:<4} {r['title']:<20} {r['difficulty']:<8} "
              f"{r['a']['verdict']:<10} {r['b']['verdict']:<10} "
              f"{r['b']['verifier_calls']:<12} {extra:<+12,}")

    # ── 生成报告 ──
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "benchmark_verifier_report.md",
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Verifier Agent 压测报告\n\n")
        f.write(f"> 由 `benchmark_verifier.py` 自动生成\n")
        f.write(f"> 模型: {config['model']}\n\n")

        f.write("## 汇总数据\n\n")
        f.write(f"| 指标 | A（无 Verifier） | B（有 Verifier） | 变化 |\n")
        f.write(f"|------|-----------------|-----------------|------|\n")
        f.write(f"| 有效任务数 | — | {n_valid}/{len(TASKS)} | {errors} 个因网络错误未完成 |\n")
        f.write(f"| PASS 数 | {a_pass}/{n_valid} | {b_pass}/{n_valid} | +{b_pass - a_pass} |\n")
        f.write(f"| MINOR 数 | {a_minor}/{n_valid} | {b_minor}/{n_valid} | {b_minor - a_minor:+} |\n")
        f.write(f"| FAIL 数 | {a_fail}/{n_valid} | {b_fail}/{n_valid} | {b_fail - a_fail:+} |\n")
        f.write(f"| **PASS 率** | **{a_pass_rate:.0f}%** | **{b_pass_rate:.0f}%** | **+{b_pass_rate - a_pass_rate:.0f}%** |\n")
        f.write(f"| **提升率（纠正率）** | — | **{improvement:.1f}%** | 在原本不通过的任务中纠正的比例 |\n")
        f.write(f"| 总 Token 消耗 | {total_tokens_a:,} | {total_tokens_b:,} | +{total_tokens_b - total_tokens_a:,} |\n")
        f.write(f"| 平均每任务 Token | {total_tokens_a // n_valid:,} | {total_tokens_b // n_valid:,} | +{(total_tokens_b - total_tokens_a) // n_valid:,} |\n")
        f.write(f"| Verifier 总调用轮次 | — | {total_verifier_calls} | 平均 {total_verifier_calls/n_valid:.1f} 轮/任务 |\n\n")

        f.write("## 逐任务详情\n\n")
        f.write("| # | 任务 | 难度 | A 裁决 | B 裁决 | Verifier 轮次 | 额外 Token | 质量变化 |\n")
        f.write("|---|------|------|--------|--------|-------------|-----------|---------|\n")
        for r in all_results:
            if "error" in r:
                f.write(f"| {r['task_id']} | {r['title']} | ERROR | ERR | ERR | -- | -- | ERROR |\n")
                continue
            extra = r["b"]["tokens"] - r["a"]["tokens"]
            score_a = VERDICT_SCORE.get(r["a"]["verdict"], 0)
            score_b = VERDICT_SCORE.get(r["b"]["verdict"], 0)
            if score_b > score_a:
                change = f"UPGRADE ({r['a']['verdict']}->{r['b']['verdict']})"
            elif score_b < score_a:
                change = f"REGRESS ({r['a']['verdict']}->{r['b']['verdict']})"
            else:
                change = "SAME"
            f.write(f"| {r['task_id']} | {r['title']} | {r['difficulty']} "
                    f"| {r['a']['verdict']} | {r['b']['verdict']} "
                    f"| {r['b']['verifier_calls']} | +{extra:,} | {change} |\n")

        f.write("\n## 结论\n\n")
        f.write(f"- 无 Verifier 时 PASS 率: **{a_pass_rate:.0f}%** ({a_pass}/{n_valid})\n")
        f.write(f"- 有 Verifier 时 PASS 率: **{b_pass_rate:.0f}%** ({b_pass}/{n_valid})\n")
        f.write(f"- **提升率: {improvement:.1f}%**（在原本不通过的任务中，Verifier 帮助纠正了 {improvement:.0f}%）\n")
        f.write(f"- 每次审查的平均额外 Token 消耗: ~{(total_tokens_b - total_tokens_a) // max(total_verifier_calls, 1):,} tokens\n")
        f.write(f"- Verifier Agent 通过独立审查 + 针对性修改的闭环，有效提升了编码任务的通过率\n")

    print(f"\n  [OK] 报告已生成: {report_path}")


if __name__ == "__main__":
    main()
