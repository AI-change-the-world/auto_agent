"""
OpenAI 原生客户端版本 Adaptive Memo Demo（tools-call）

与 examples/adaptive_memo_demo.py 对比：使用 OpenAI 原生 function calling 实现（generate / verify / reflect 三工具闭环）。

使用方法:
    cd auto_agent
    python examples/langchain_compare/adaptive_memo_langchain.py
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path（仿照 examples/langchain_compare/main.py）
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from openai import AsyncOpenAI


def _json_extract(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中提取 JSON object（宽松解析）"""
    try:
        m = re.search(r"\{[\s\S]*\}", text or "")
        if not m:
            return None
        return json.loads(m.group(0))
    except Exception:
        return None


# ==================== Token 追踪（仿照 main.py） ====================


class TokenTracker:
    """Token 追踪器"""

    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        self.cumulative_tokens = 0
        self.llm_call_count = 0

    def add(self, tokens: int, step_name: str):
        self.llm_call_count += 1
        self.cumulative_tokens += tokens
        self.steps.append(
            {
                "step": step_name,
                "tokens": tokens,
                "cumulative": self.cumulative_tokens,
            }
        )
        print(f"   📊 Token: +{tokens:,} | 累计: {self.cumulative_tokens:,}")


# ==================== 工具定义（3 tools） ====================


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "generate_memo_tool",
            "description": "根据 requirements + rubric (+feedback/+previous_memo) 生成备忘录正文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirements": {"type": "string", "description": "任务背景与约束"},
                    "rubric": {
                        "type": "object",
                        "description": "评估与写作规则(JSON)。若缺失，工具将自行推断并补全。",
                    },
                    "feedback": {
                        "type": "string",
                        "description": "上一轮反思得到的可执行改进指令（可选）",
                        "default": "",
                    },
                    "previous_memo": {
                        "type": "string",
                        "description": "上一版备忘录（可选，用于增量改写）",
                        "default": "",
                    },
                },
                "required": ["requirements"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_memo_tool",
            "description": "LLM judge：验证 memo 是否满足 rubric，返回 passed/issues/score 等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "memo": {"type": "string", "description": "待验证的 memo（缺失则默认用当前 state.memo）"},
                    "rubric": {"type": "object", "description": "rubric（缺失则默认用当前 state.rubric）"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reflect_feedback_tool",
            "description": "基于 verification 报告生成下一轮可执行改进指令。",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirements": {
                        "type": "string",
                        "description": "原始 requirements（缺失则默认用当前 state.requirements）",
                    },
                    "memo": {"type": "string", "description": "上一版 memo（缺失则默认用当前 state.memo）"},
                    "verification": {
                        "type": "object",
                        "description": "verify_memo_tool 输出（缺失则默认用当前 state.verification）",
                    },
                    "rubric": {"type": "object", "description": "rubric（缺失则默认用当前 state.rubric）"},
                },
                "required": [],
            },
        },
    },
]


# ==================== 工具实现（仿照 main.py 的 ToolExecutor） ====================


class ToolExecutor:
    """工具执行器（维护 state，并在工具内部调用 LLM）"""

    def __init__(self, client: AsyncOpenAI, model: str):
        self.client = client
        self.model = model
        self.state: Dict[str, Any] = {
            "requirements": "",
            "rubric": None,
            "memo": "",
            "verification": None,
            "feedback": "",
        }
        self._fail_once = True  # 模拟一次瞬态失败，便于对比 auto_agent 的 retry

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> str:
        """执行工具（返回字符串 content，写入 messages['tool']）"""
        print(f"   ▶️ 执行工具: {tool_name}")

        if tool_name == "generate_memo_tool":
            result = await self._generate_memo_tool(args)
        elif tool_name == "verify_memo_tool":
            result = await self._verify_memo_tool(args)
        elif tool_name == "reflect_feedback_tool":
            result = await self._reflect_feedback_tool(args)
        else:
            result = {"success": False, "error": f"未知工具: {tool_name}"}

        return json.dumps(result, ensure_ascii=False)

    async def _infer_rubric(self, requirements: str) -> Dict[str, Any]:
        """rubric 的 llm_infer（在 tools-call 版本里放到工具内部做）"""
        fallback = {
            "required_sections": ["背景", "决策", "方案对比", "风险清单", "下一步"],
            "min_risks": 5,
            "max_words": 650,
            "tone": "专业",
        }

        prompt = f"""请为下面的写作任务生成一个 rubric(JSON)，用于约束“决策备忘录”输出。

你必须输出 JSON（不要输出其它文字），至少包含：
- required_sections: string[]
- min_risks: int
- max_words: int
- tone: string

【requirements】
{requirements}
"""
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        txt = resp.choices[0].message.content or ""
        obj = _json_extract(txt) or {}
        if not isinstance(obj, dict):
            return fallback

        required_sections = obj.get("required_sections") or fallback["required_sections"]
        if not isinstance(required_sections, list) or not required_sections:
            required_sections = fallback["required_sections"]

        try:
            min_risks = int(obj.get("min_risks") or fallback["min_risks"])
        except Exception:
            min_risks = fallback["min_risks"]
        try:
            max_words = int(obj.get("max_words") or fallback["max_words"])
        except Exception:
            max_words = fallback["max_words"]
        tone = str(obj.get("tone") or fallback["tone"])

        return {
            "required_sections": [str(x) for x in required_sections if str(x).strip()],
            "min_risks": max(0, min_risks),
            "max_words": max(0, max_words),
            "tone": tone,
        }

    async def _generate_memo_tool(self, args: Dict[str, Any]) -> Dict[str, Any]:
        requirements = (args.get("requirements") or self.state.get("requirements") or "").strip()
        if not requirements:
            return {"success": False, "error": "missing_requirements"}
        self.state["requirements"] = requirements

        rubric = args.get("rubric") or self.state.get("rubric")
        if not isinstance(rubric, dict) or not rubric:
            rubric = await self._infer_rubric(requirements)

        feedback = (args.get("feedback") or self.state.get("feedback") or "").strip()
        previous_memo = (args.get("previous_memo") or self.state.get("memo") or "").strip()

        # 模拟一次瞬态失败：让 demo 能看到“工具失败 -> 下一轮重试/调整”
        if self._fail_once:
            self._fail_once = False
            print("   ⚠️ 模拟瞬态失败一次（用于展示 retry/replan）")
            return {"success": False, "error": "transient_failure: simulate retry once"}

        # 把 rubric 的具体数值直接写进 prompt，让模型更容易遵守
        max_words = int(rubric.get("max_words") or 650)
        min_risks = int(rubric.get("min_risks") or 5)
        required_sections = rubric.get("required_sections") or ["背景", "决策", "方案对比", "风险清单", "下一步"]
        sections_str = "、".join(required_sections)
        tone = rubric.get("tone") or "专业"
        _ = rubric  # keep rubric reference

        prompt = f"""你是一名资深技术负责人，请根据以下要求撰写一份“决策备忘录”(中文)。

【requirements】
{requirements}

【上一次反馈（如果有则必须逐条落实）】
{feedback if feedback else "无"}

【上一版备忘录（可选参考，避免重复空话）】
{previous_memo[:1500] if previous_memo else "无"}

【硬性约束（必须严格遵守）】
1) 章节标题：必须包含 {sections_str}（按此顺序作为一级标题）
2) 风险清单：必须列出 >= {min_risks} 条风险，每条包含: 风险/严重度/缓解措施
3) 字数限制：全文不超过 {max_words} 个中文字符（当前限制 {max_words} 字，请精炼表达）
4) 语气风格：{tone}
5) 不要输出 JSON，不要输出解释，直接输出备忘录正文
"""
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        memo = (resp.choices[0].message.content or "").strip()

        self.state["rubric"] = rubric
        self.state["memo"] = memo
        if feedback:
            self.state["feedback"] = feedback

        print(f"   ✅ 生成完成: memo_len={len(memo)}")
        return {
            "success": True,
            "memo": memo,
            "rubric": rubric,
            "used_feedback": feedback or "",
        }

    async def _verify_memo_tool(self, args: Dict[str, Any]) -> Dict[str, Any]:
        memo = (args.get("memo") or self.state.get("memo") or "").strip()
        rubric = args.get("rubric") or self.state.get("rubric") or {}
        if not memo:
            return {"success": True, "passed": False, "issues": ["missing_memo"], "score": 0.0, "verification": {}}
        if not isinstance(rubric, dict) or not rubric:
            rubric = await self._infer_rubric(self.state.get("requirements") or "")

        min_risks = int(rubric.get("min_risks") or 0)
        max_words = int(rubric.get("max_words") or 0)

        rubric_json = json.dumps(rubric, ensure_ascii=False, indent=2)
        # 对齐 examples/adaptive_memo_demo.py 的 LLM judge prompt
        prompt = f"""你是一个严格的“备忘录评审官”。请仅基于 rubric 判断 memo 是否通过，并给出可执行 issues。

要求：
1) 你必须输出 JSON（不要输出其它文字），结构如下：
{{
  "passed": true/false,
  "score": 0-100,
  "issues": ["..."],
  "risk_items": ["..."],  // 你认为属于《风险清单》的独立风险条目
  "memo_length": <int>
}}
2) passed 为 true 的充要条件：rubric.required_sections 全部出现；risk_items 数量 >= rubric.min_risks；memo_length <= rubric.max_words
3) issues 必须具体、可操作（例如“风险条目不足：目前3条，需要>=5条”）

【rubric】
{rubric_json}

【memo】
{memo}
"""
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )

        passed = False
        score = 10.0
        issues: List[str] = ["judge_parse_failed"]
        risk_items: List[str] = []

        txt = resp.choices[0].message.content or ""
        obj = _json_extract(txt) or {}
        try:
            if isinstance(obj, dict):
                passed = bool(obj.get("passed"))
                score = float(obj.get("score", 0.0) or 0.0)
                issues_raw = obj.get("issues") or []
                if isinstance(issues_raw, list):
                    issues = [str(x) for x in issues_raw if str(x).strip()]
                risk_raw = obj.get("risk_items") or []
                if isinstance(risk_raw, list):
                    risk_items = [str(x) for x in risk_raw if str(x).strip()]
        except Exception:
            pass

        memo_len = len(memo or "")
        # 双保险：用 rubric 再校验一次（避免模型漏写）
        if memo_len > 0:
            if max_words > 0 and memo_len > max_words and all("内容过长" not in str(x) for x in issues):
                issues.append(f"内容过长: {memo_len} > {max_words}")
            if min_risks > 0 and len(risk_items) < min_risks and all("风险条数不足" not in str(x) for x in issues):
                issues.append(f"风险条数不足: {len(risk_items)} < {min_risks}")
            passed = (len(issues) == 0)

        verification = {
            "passed": passed,
            "issues": issues,
            "memo_length": memo_len,
            "min_risks": min_risks,
            "max_words": max_words,
            "risk_items_count": len(risk_items),
            "risk_count_method": "llm_only",
            "risk_items_preview": risk_items[:10],
        }

        self.state["rubric"] = rubric
        self.state["verification"] = verification

        print(
            f"   ✅ 验证完成: passed={passed} score={score} issues={len(issues)} risk_items={len(risk_items)}"
        )
        return {
            "success": True,
            "passed": passed,
            "issues": issues,
            "score": score,
            "verification": verification,
        }

    async def _reflect_feedback_tool(self, args: Dict[str, Any]) -> Dict[str, Any]:
        requirements = (args.get("requirements") or self.state.get("requirements") or "").strip()
        memo = (args.get("memo") or self.state.get("memo") or "").strip()
        verification = args.get("verification") or self.state.get("verification") or {}
        rubric = args.get("rubric") or self.state.get("rubric") or {}

        if not requirements or not memo:
            return {"success": False, "error": "missing_requirements_or_memo"}

        prompt = f"""你是一个“备忘录质量改进助手”。请根据验证报告，输出下一轮生成 memo 的“可执行改进指令”。

【requirements】
{requirements}

【rubric】
{json.dumps(rubric, ensure_ascii=False, indent=2)}

【verification 报告】
{json.dumps(verification, ensure_ascii=False, indent=2)}

【上一版 memo（截断）】
{memo[:1800]}

输出要求：
1) 只输出改进指令文本（不要 JSON）
2) 必须逐条对应 verification.issues，给出明确的“应该补什么/删什么/改什么”
3) 如果字数超限，给出精简策略（删冗余、合并段落、改为列表）
4) 给出一个“优先级顺序”（先修最影响通过验证的点）
"""
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        feedback = (resp.choices[0].message.content or "").strip()

        self.state["feedback"] = feedback
        print(f"   ✅ 反思完成: feedback_len={len(feedback)}")
        return {"success": True, "feedback": feedback, "rubric": rubric}


# ==================== Agent 主循环（仿照 main.py） ====================


async def run_openai_agent(requirements: str) -> Dict[str, Any]:
    """运行 OpenAI Function Calling Agent（memo 版本）"""

    print("=" * 70)
    print("📝 OpenAI Function Calling Agent (Adaptive Memo)")
    print("=" * 70)

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    tool_executor = ToolExecutor(client, model)
    tracker = TokenTracker()

    print(f"\n✅ 客户端初始化成功 (model: {model})")

    system_prompt = """你是一个“备忘录生成智能体”(tools-call)。

你可以使用以下工具完成任务：
1) generate_memo_tool - 生成 memo（rubric 缺失时工具会 llm_infer 补全）
2) verify_memo_tool - LLM judge 严格验证 memo（返回 passed/issues）
3) reflect_feedback_tool - 根据验证报告生成下一轮可执行改进指令

规则：
1) 必须通过调用工具来迭代：generate -> verify -> (reflect -> generate -> verify ...) 直到 passed=true 或达到迭代上限。
2) 不要直接在 message.content 输出 memo 正文；memo 必须通过 generate_memo_tool 产出。
3) 每次工具调用尽量携带最新 memo/rubric/verification/feedback（但即使缺失，脚本会用 state 兜底）。
"""

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": requirements},
    ]

    print(f"\n📋 用户需求:\n{requirements.strip()}")
    print("\n" + "=" * 70)
    print("🚀 开始执行...")
    print("=" * 70)

    start_time = time.time()
    max_iterations = 15
    iteration = 0

    # 为了保证“不会无声结束”，如果模型连续不调工具，就强制提示并最终兜底输出 best memo
    non_tool_rounds = 0
    max_non_tool_rounds = 3

    best_candidate = {"memo": "", "score": -1.0, "issues": []}
    final_output = ""

    try:
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- 迭代 {iteration} ---")

            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.7,
            )

            if response.usage:
                tracker.add(response.usage.total_tokens, f"iteration_{iteration}")

            message = response.choices[0].message

            # 有工具调用：执行工具
            if message.tool_calls:
                non_tool_rounds = 0
                messages.append(message)

                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments or "{}")
                    except Exception:
                        func_args = {}

                    result = await tool_executor.execute(func_name, func_args)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result[:5000],
                        }
                    )

                    # 额外 tracing：replan（verify 不通过时）
                    if func_name == "verify_memo_tool":
                        obj = _json_extract(result) or {}
                        passed = bool(obj.get("passed"))
                        score = float(obj.get("score", 0.0) or 0.0)
                        issues = obj.get("issues") or []
                        if isinstance(issues, list):
                            issues = [str(x) for x in issues if str(x).strip()]
                        else:
                            issues = []

                        # best memo 兜底
                        memo_now = tool_executor.state.get("memo") or ""
                        if memo_now and score > float(best_candidate.get("score", -1.0) or -1.0):
                            best_candidate = {"memo": memo_now, "score": score, "issues": issues}

                        if not passed:
                            first_issue = issues[0] if issues else "unknown"
                            print(f"   ⚠️ 发生 replan: {first_issue}")
                            # 强提示下一步走 reflect->generate->verify，避免模型“结束”或乱跳
                            messages.append(
                                {
                                    "role": "system",
                                    "content": "验证未通过：请调用 reflect_feedback_tool 生成改进指令，然后调用 generate_memo_tool 产出修订版，再次 verify。",
                                }
                            )

                # 成功条件：passed=true 直接收敛
                verification = tool_executor.state.get("verification") or {}
                if isinstance(verification, dict) and verification.get("passed") is True:
                    final_output = tool_executor.state.get("memo") or ""
                    print("\n✅ 已通过验证，结束迭代")
                    break

            else:
                # 没有工具调用：memo demo 里通常是不合规（容易“一次就结束”）
                non_tool_rounds += 1
                messages.append({"role": "assistant", "content": message.content or ""})
                messages.append(
                    {
                        "role": "system",
                        "content": "你必须调用工具（generate/verify/reflect），不要直接输出内容。若未通过验证，不允许结束。",
                    }
                )
                print("   ⚠️ 模型未调用工具，已强制提示继续使用工具")

                if non_tool_rounds >= max_non_tool_rounds:
                    print("   ⚠️ 连续多轮未调用工具，触发兜底输出")
                    break

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        # 最终输出：优先用通过验证的 memo，否则用 best_candidate
        if not final_output:
            final_output = tool_executor.state.get("memo") or best_candidate.get("memo") or ""

        appendix = ""
        verification = tool_executor.state.get("verification") or {}
        passed = isinstance(verification, dict) and verification.get("passed") is True
        if not passed:
            issues = best_candidate.get("issues") or (verification.get("issues") if isinstance(verification, dict) else []) or []
            if isinstance(issues, list) and issues:
                appendix = "\n\n附注（未通过验证，剩余问题）：\n" + "\n".join([f"- {x}" for x in issues[:10]])

        output_text = (final_output + appendix).strip() or "（未生成有效 memo）"

        print("\n" + "=" * 70)
        print("✅ 执行完成!")
        print("=" * 70)
        print(f"\n📊 执行统计:")
        print(f"   - 迭代次数: {iteration}")
        print(f"   - LLM 调用(决策轮): {tracker.llm_call_count}")
        print(f"   - Token 消耗(决策轮): {tracker.cumulative_tokens:,}")
        print(f"   - 耗时: {duration_ms:.1f}ms")

        print(f"\n📊 Token 消耗明细:")
        for step in tracker.steps:
            print(
                f"      {step['step']}: +{step['tokens']:,} (累计: {step['cumulative']:,})"
            )

        print("\n" + "=" * 70)
        print("📄 最终输出（OpenAI 官方 client + tools call，3 tools 自主规划）")
        print("=" * 70)
        print(output_text)

        return {
            "success": True,
            "output": output_text,
            "iterations": iteration,
            "llm_calls": tracker.llm_call_count,
            "total_tokens": tracker.cumulative_tokens,
            "token_steps": tracker.steps,
            "duration_ms": duration_ms,
            "passed": passed,
        }

    except Exception as e:
        end_time = time.time()
        print(f"\n❌ 执行失败: {e}")
        import traceback

        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "duration_ms": (end_time - start_time) * 1000,
            "total_tokens": tracker.cumulative_tokens,
        }


async def main():
    """主函数（仿照 main.py）"""
    print("🚀 启动 OpenAI Function Calling Adaptive Memo Demo...")

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 未设置 API Key（OPENAI_API_KEY 或 DEEPSEEK_API_KEY）")
        return

    requirements = """
请为团队写一份“技术决策备忘录”，主题是：我们是否要把现有单体服务拆分为微服务。

需求描述:
1) 背景：目前单体已出现部署频率低、发布风险大、部分模块性能瓶颈
2) 目标：在不牺牲交付速度的前提下，提高可维护性、可扩展性和故障隔离能力
3) 约束：团队人数 6 人；未来 3 个月主要目标是稳定交付；运维能力一般；预算有限
4) 输出必须包含：背景、决策、方案对比、风险清单、下一步

请按“先给出初稿 -> 严格验证 -> 反思不足 -> 修订 -> 再验证”的方式迭代到通过验证。
""".strip()

    result = await run_openai_agent(requirements)

    # 保存结果（仿照 main.py）
    if result.get("success"):
        output_dir = script_dir / "output"
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"openai_fc_adaptive_memo_{timestamp}.md"

        token_detail = "\n### Token 消耗明细（仅决策轮）\n\n| 步骤 | Token | 累计 |\n|------|-------|------|\n"
        for step in result.get("token_steps", []):
            token_detail += (
                f"| {step['step']} | {step['tokens']:,} | {step['cumulative']:,} |\n"
            )

        output_file.write_text(
            f"""# OpenAI Function Calling - Adaptive Memo

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 框架: OpenAI Native Function Calling
> 通过验证: {result.get("passed")}

---

{result.get("output", "")}

---

## 执行统计

- 迭代次数: {result.get("iterations")}
- LLM 调用次数(决策轮): {result.get("llm_calls")}
- Token 消耗(决策轮): {result.get("total_tokens", 0):,}
- 耗时: {result.get("duration_ms", 0.0):.1f}ms
{token_detail}
""",
            encoding="utf-8",
        )

        print(f"\n📄 输出已保存: {output_file}")


if __name__ == "__main__":
    print("=" * 70)
    print("OpenAI Function Calling Adaptive Memo Demo")
    print("=" * 70)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")

