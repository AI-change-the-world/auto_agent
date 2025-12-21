"""
开放性高难度 Demo：可绑定参数 + LLM 推断参数(llm_infer) + 重试 + 反思改进 + replan

特点：
- 工具数量少（3 个工具：generate_memo / verify_memo / reflect_feedback）
- 计划步骤少（5 步固定计划，verify 失败会回到 reflect->generate 循环）
- 参数绑定：
  - requirements 来自 user_input（静态绑定）
  - memo 来自 step_output（静态绑定）
  - rubric / feedback 等由系统在运行时 llm_infer（BindingPlanner 会给出 generated / fallback=llm_infer）
- 重试：generate_memo 人为模拟一次 transient failure，依靠 on_fail_strategy="重试" 触发重试
- 反思：reflect_feedback 会基于 verify 的输出（即使 expectation fail 也会被写入 state）生成针对性改进指令
- replan：执行引擎在失败模式下会触发 replan（可在事件中观察 stage_replan）

运行：
  python examples/adaptive_memo_demo.py

环境变量：
  OPENAI_API_KEY / DEEPSEEK_API_KEY
  OPENAI_BASE_URL (可选，默认 deepseek)
  OPENAI_MODEL (可选，默认 deepseek-chat)
"""

import asyncio
import json
import os
import re
from typing import Any, Dict, Optional

from auto_agent import AutoAgent, BaseTool, OpenAIClient, ToolDefinition, ToolParameter, ToolRegistry


def get_llm_client() -> Optional[OpenAIClient]:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")
    return OpenAIClient(api_key=api_key, base_url=base_url, model=model, timeout=120.0)


def _validate_verify_output(result, expectations, state, mode, llm_client, db):
    """verify_memo 的 validate_function：passed==True 才算满足期望。"""
    passed = bool(result.get("passed"))
    if passed:
        return True, "通过验证"
    issues = result.get("issues") or []
    if isinstance(issues, list) and issues:
        return False, f"未通过验证: {issues[0]}"
    return False, "未通过验证"


class GenerateMemoTool(BaseTool):
    """生成备忘录（rubric/feedback 可由系统推断）"""

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client
        self._fail_once = True

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_memo",
            description=(
                "根据 requirements + rubric 生成一份中文决策备忘录。"
                "rubric 是一个 JSON 对象，包含 required_sections/min_risks/max_words/tone 等。"
                "如果用户未提供 rubric 或 feedback，应由系统在运行时推断并补全。"
            ),
            parameters=[
                ToolParameter(
                    name="requirements",
                    type="string",
                    description="用户的任务/背景/目标（来自输入）",
                    required=True,
                ),
                ToolParameter(
                    name="rubric",
                    type="object",
                    description=(
                        "评估与写作规则(JSON)。示例: "
                        '{"required_sections":["背景","决策","方案对比","风险清单","下一步"],'
                        '"min_risks":5,"max_words":650,"tone":"专业"}。'
                        "若用户未提供，必须由系统生成。"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="feedback",
                    type="string",
                    description="来自上一次验证/反思的改进指令（可选）",
                    required=False,
                ),
                ToolParameter(
                    name="previous_memo",
                    type="string",
                    description="上一版备忘录（可选，用于增量改写）",
                    required=False,
                ),
            ],
            output_schema={
                "memo": {"type": "string"},
                "rubric": {"type": "object"},
                "used_feedback": {"type": "string"},
            },
            # 给执行器兜底：即便没有 binding_plan，也能从 state 中取到这些值
            param_aliases={
                "requirements": "inputs.requirements",
                "rubric": "rubric",
                "feedback": "feedback",
                "previous_memo": "memo",
            },
        )

    async def execute(
        self,
        requirements: str,
        rubric: Dict[str, Any],
        feedback: str = "",
        previous_memo: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        # 模拟一次瞬态失败：让 demo 能看到 retry
        if self._fail_once:
            self._fail_once = False
            return {"success": False, "error": "transient_failure: simulate retry once"}

        rubric_json = json.dumps(rubric, ensure_ascii=False, indent=2)
        prompt = f"""你是一名资深技术负责人，请根据以下要求撰写一份“决策备忘录”(中文)。

【requirements】
{requirements}

【rubric（必须严格遵守）】
{rubric_json}

【上一次反馈（如果有则必须逐条落实）】
{feedback if feedback else "无"}

【上一版备忘录（可选参考，避免重复空话）】
{previous_memo[:1500] if previous_memo else "无"}

写作要求：
1) 使用 rubric.required_sections 的标题作为一级标题（按该顺序）
2) “风险清单”至少列出 rubric.min_risks 条风险，每条包含: 风险/严重度/缓解措施
3) 控制全文不超过 rubric.max_words 个中文字符（尽量精炼）
4) 语气/风格符合 rubric.tone
5) 不要输出 JSON，不要输出解释，直接输出备忘录正文
"""

        memo = await self.llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
            trace_purpose="tool_generate_memo",
        )

        return {
            "success": True,
            "memo": memo.strip(),
            "rubric": rubric,
            "used_feedback": feedback or "",
        }


class VerifyMemoTool(BaseTool):
    """LLM 判定验证（把验证报告写入 state，便于后续反思/改写）"""

    def __init__(self, llm_client: Optional[OpenAIClient] = None):
        # 可选：用于“语义型兜底判定”（仅在规则解析不可靠时触发）
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="verify_memo",
            description="验证备忘录是否满足 rubric。返回 passed/issues/score，并附带 verification 报告。",
            parameters=[
                ToolParameter(
                    name="memo",
                    type="string",
                    description="待验证的备忘录",
                    required=True,
                ),
                ToolParameter(
                    name="rubric",
                    type="object",
                    description="评估规则(JSON)，来自 generate_memo 输出",
                    required=True,
                ),
            ],
            output_schema={
                "passed": {"type": "boolean"},
                "issues": {"type": "array"},
                "score": {"type": "number"},
                "verification": {"type": "object"},
            },
            validate_function=_validate_verify_output,
            param_aliases={"memo": "memo", "rubric": "rubric"},
        )

    async def execute(self, memo: str, rubric: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        if not self.llm_client:
            return {
                "success": True,
                "passed": False,
                "issues": ["llm_client_missing_for_verify"],
                "score": 10.0,
                "verification": {"passed": False, "issues": ["llm_client_missing_for_verify"]},
            }

        min_risks = int(rubric.get("min_risks") or 0)
        max_words = int(rubric.get("max_words") or 0)

        rubric_json = json.dumps(rubric, ensure_ascii=False, indent=2)
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
        resp = await self.llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            trace_purpose="tool_verify_memo_llm_judge",
        )

        passed = False
        score = 10.0
        issues = ["judge_parse_failed"]
        risk_items: list[str] = []
        try:
            m = re.search(r"\{[\s\S]*\}", resp)
            if m:
                obj = json.loads(m.group(0))
                passed = bool(obj.get("passed"))
                score = float(obj.get("score", 0.0) or 0.0)
                issues_raw = obj.get("issues") or []
                if isinstance(issues_raw, list):
                    issues = [str(x) for x in issues_raw if str(x).strip()]
                risk_raw = obj.get("risk_items") or []
                if isinstance(risk_raw, list):
                    risk_items = [str(x) for x in risk_raw if str(x).strip()]
        except Exception:
            # 保留默认值
            pass

        # 双保险：如果 LLM 没填 memo_length，就用本地长度
        memo_len = len(memo or "")
        # 用 rubric 约束再兜一层（防止模型输出不一致）
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

        # 注意：这里 success 永远 True，让输出能写入 state；
        # “是否通过”交给 validate_function + expectations 来决定 step 成败。
        return {
            "success": True,
            "passed": passed,
            "issues": issues,
            "score": score,
            "verification": verification,
        }


class ReflectFeedbackTool(BaseTool):
    """反思上一步验证结果，产出更具体的改进指令（用于下一轮 generate_memo）"""

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="reflect_feedback",
            description="根据 verification 报告，反思备忘录的不足并给出针对性改进指令（用于下一轮生成）。",
            parameters=[
                ToolParameter(
                    name="requirements",
                    type="string",
                    description="原始 requirements",
                    required=True,
                ),
                ToolParameter(
                    name="memo",
                    type="string",
                    description="上一版备忘录",
                    required=True,
                ),
                ToolParameter(
                    name="verification",
                    type="object",
                    description="verify_memo 的 verification 报告（即使验证失败也会写入 state）",
                    required=True,
                ),
                ToolParameter(
                    name="rubric",
                    type="object",
                    description="rubric（用于保持一致）",
                    required=True,
                ),
            ],
            output_schema={"feedback": {"type": "string"}, "rubric": {"type": "object"}},
            param_aliases={
                "requirements": "inputs.requirements",
                "memo": "memo",
                "verification": "verification",
                "rubric": "rubric",
            },
        )

    async def execute(
        self,
        requirements: str,
        memo: str,
        verification: Dict[str, Any],
        rubric: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
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
        feedback = await self.llm_client.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            trace_purpose="tool_reflect_feedback",
        )

        return {"success": True, "feedback": feedback.strip(), "rubric": rubric}


async def main():
    llm_client = get_llm_client()
    if not llm_client:
        print("请先设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY")
        return

    registry = ToolRegistry()
    registry.register(GenerateMemoTool(llm_client))
    registry.register(VerifyMemoTool(llm_client))
    registry.register(ReflectFeedbackTool(llm_client))

    agent = AutoAgent(
        llm_client=llm_client,
        tool_registry=registry,
        agent_name="Adaptive Memo Agent",
        agent_description="少工具 + 多轮反思改进 + 可重试/可重规划 的开放性 demo",
    )

    # 开放性任务：你也可以替换成自己想测的高难度任务
    user_query = """
请为团队写一份“技术决策备忘录”，主题是：我们是否要把现有单体服务拆分为微服务。

需求描述:
1) 背景：目前单体已出现部署频率低、发布风险大、部分模块性能瓶颈
2) 目标：在不牺牲交付速度的前提下，提高可维护性、可扩展性和故障隔离能力
3) 约束：团队人数 6 人；未来 3 个月主要目标是稳定交付；运维能力一般；预算有限
4) 输出必须包含：背景、决策、方案对比、风险清单、下一步

请按“先给出初稿 -> 严格验证 -> 反思不足 -> 修订 -> 再验证”的方式迭代到通过验证。
"""

    # 固定计划：确保 demo 一定会走到 binding/llm_infer/反思/重试/循环
    initial_plan = [
        {
            "id": "1",
            "tool": "generate_memo",
            "description": "生成初版备忘录（rubric 将由系统推断）",
            "is_pinned": True,
            "on_fail_strategy": "重试",
        },
        {
            "id": "2",
            "tool": "verify_memo",
            "description": "验证初版备忘录（失败会产出报告供后续反思）",
            "is_pinned": True,
            "expectations": "passed 必须为 true，否则必须给出 issues",
            "on_fail_strategy": "回退到步骤 3",
        },
        {
            "id": "3",
            "tool": "reflect_feedback",
            "description": "反思验证报告并生成针对性改进指令",
            "is_pinned": True,
            "on_fail_strategy": "重试",
        },
        {
            "id": "4",
            "tool": "generate_memo",
            "description": "根据改进指令生成修订版备忘录",
            "is_pinned": True,
        },
        {
            "id": "5",
            "tool": "verify_memo",
            "description": "验证修订版（不通过则继续反思-修订循环）",
            "is_pinned": True,
            "expectations": "passed 必须为 true，否则必须给出 issues",
            "on_fail_strategy": "回退到步骤 3",
        },
    ]

    print("=" * 70)
    print("🧪 Adaptive Memo Demo (auto_agent)")
    print("=" * 70)

    final_answer = ""
    last_memo = ""
    last_verification: Dict[str, Any] = {}
    last_issues = []
    async for event in agent.run_stream(
        query=user_query,
        user_id="demo",
        initial_plan=initial_plan,
    ):
        et = event.get("event")
        data = event.get("data", {})

        if et == "planning":
            print(f"\n📝 {data.get('message')}")

        elif et == "binding_plan":
            # 简要打印即可（详细看 trace 报告）
            print(f"\n🔗 {data.get('message')}")
            print(f"   bindings_count={data.get('bindings_count')}")

        elif et == "execution_plan":
            print(f"\n📋 固定计划已加载，steps={len(data.get('steps', []))}")

        elif et == "stage_start":
            print(f"\n▶️  Step {data.get('step')}: {data.get('name')}")
            print(f"   描述: {data.get('description', '')}")

        elif et == "param_build":
            # 参数构造详情
            is_loop = data.get("is_loop_execution", False)
            args_preview = data.get("args_preview", {})
            if is_loop:
                print(f"   🔄 [循环执行] {args_preview.get('loop_reason', '')}")
            final_args = args_preview.get("final_args", {})
            if final_args:
                print(f"   📦 参数预览:")
                for k, v in final_args.items():
                    v_str = str(v)
                    if len(v_str) > 100:
                        v_str = v_str[:100] + "..."
                    print(f"      - {k}: {v_str}")

        elif et == "stage_complete":
            status = "✅" if data.get("success") else "❌"
            print(f"   {status} {data.get('name')}")
            result = data.get("result") or {}
            if data.get("name") == "verify_memo" and isinstance(result, dict):
                passed = result.get("passed")
                issues = result.get("issues") or []
                score = result.get("score")
                last_issues = issues if isinstance(issues, list) else []
                last_verification = result.get("verification") or {}
                print(f"   验证结果: passed={passed}, score={score}")
                if isinstance(last_verification, dict) and last_verification:
                    rc = last_verification.get("risk_items_count")
                    rm = last_verification.get("risk_count_method")
                    if rc is not None:
                        print(f"   📌 风险计数: {rc}（method={rm}）")
                    rp = last_verification.get("risk_items_preview") or []
                    if isinstance(rp, list) and rp:
                        print("   📌 识别到的风险条目(前5):")
                        for x in rp[:5]:
                            print(f"      - {x}")
                if issues:
                    print(f"   ❗ 问题列表:")
                    for issue in issues[:5]:  # 最多显示5个问题
                        print(f"      - {issue}")
            elif data.get("name") == "reflect_feedback" and isinstance(result, dict):
                feedback = result.get("feedback", "")
                if feedback:
                    print(f"   📝 反馈摘要: {feedback[:200]}...")
            elif data.get("name") == "generate_memo" and isinstance(result, dict):
                memo = result.get("memo", "")
                if memo:
                    last_memo = memo
                    print(f"   📄 备忘录长度: {len(memo)} 字符")
                    # 统计风险条数
                    risk_lines = [ln for ln in memo.splitlines() if "风险" in ln]
                    print(f"   📊 风险条目数: {len(risk_lines)}")

        elif et == "stage_retry":
            print(f"   🔄 {data.get('message')}")

        elif et == "stage_replan":
            print(f"\n⚠️  触发 replan: {data.get('trigger_reason')} | {data.get('reason')}")

        elif et == "answer":
            final_answer = data.get("answer", "")

        elif et == "done":
            trace = data.get("trace") or {}
            summary = trace.get("summary") or {}
            llm_calls = (summary.get("llm_calls") or {}).get("count", 0)
            total_tokens = (summary.get("llm_calls") or {}).get("total_tokens", 0)
            print("\n" + "=" * 70)
            print("✅ Demo 完成")
            print(f"- iterations: {data.get('iterations')}")
            print(f"- llm_calls: {llm_calls}")
            print(f"- total_tokens: {total_tokens}")
            print("=" * 70)

    # 输出最终 memo
    # 该 demo 的最终产物会在 state['memo'] 中
    print("\n" + "=" * 70)
    print("📄 最终结果（最终 memo 正文）")
    print("=" * 70)
    if isinstance(final_answer, str) and final_answer.strip() and final_answer.strip() != "任务执行完成":
        # 优先打印 agent 聚合的 answer（若已返回 memo）
        print(final_answer.strip())
    elif isinstance(last_memo, str) and last_memo.strip():
        # 否则兜底打印最后一次 generate_memo 的输出
        print(last_memo.strip())
    else:
        print("（未捕获到 memo 输出：请检查 generate_memo 是否返回了 result['memo']）")

    if last_issues:
        print("\n" + "-" * 70)
        print("❗ 最后一次 verify 失败原因（issues）")
        for x in last_issues[:20]:
            print(f"- {x}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())

