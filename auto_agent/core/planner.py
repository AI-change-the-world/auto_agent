"""
TaskPlanner（任务规划器）

核心功能：
- 基于 LLM 的动态规划
- 支持固定步骤（is_pinned）
- 生成 state schema
- 失败后重规划
"""

from typing import Any, Dict, List, Optional

from auto_agent.llm.client import LLMClient
from auto_agent.models import ExecutionPlan, PlanStep
from auto_agent.tools.registry import ToolRegistry


class TaskPlanner:
    """
    任务规划器

    核心思路（来自 custom_agent_executor_v2.py）：
    - 不使用静态步骤
    - 根据 Agent 目标、约束、可用工具，让 LLM 规划步骤
    - 同时生成 state schema 定义各个工具需要的字段
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        agent_goals: Optional[List[str]] = None,
        agent_constraints: Optional[List[str]] = None,
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.agent_goals = agent_goals or []
        self.agent_constraints = agent_constraints or []

    async def plan(
        self,
        query: str,
        user_context: str,
        conversation_context: str,
        initial_plan: Optional[List[Dict[str, Any]]] = None,
    ) -> ExecutionPlan:
        """
        生成执行计划

        支持固定步骤：
        - 如果 initial_plan 中有 is_pinned=True 的步骤，这些步骤必须保留
        - LLM 只能在固定步骤基础上补充必要的辅助步骤

        Args:
            query: 用户查询
            user_context: 用户长期记忆上下文
            conversation_context: 对话短期记忆上下文
            initial_plan: 初始计划（含固定步骤）

        Returns:
            ExecutionPlan
        """
        # 提取固定步骤
        pinned_steps = []
        if initial_plan:
            for step in initial_plan:
                if step.get("is_pinned", False):
                    pinned_steps.append(step)

        # 如果全部都是固定步骤，直接返回
        if pinned_steps and initial_plan and len(pinned_steps) == len(initial_plan):
            return ExecutionPlan(
                intent="fixed",
                subtasks=[self._dict_to_plan_step(s) for s in initial_plan],
                state_schema={},
            )

        # 获取工具目录
        tools_catalog = self.tool_registry.get_tools_catalog()

        # 构建固定步骤信息
        pinned_steps_info = ""
        if pinned_steps:
            import json

            pinned_steps_info = f"""

【⭐⭐⭐ 固定步骤(必须保留,不可修改) ⭐⭐⭐】
以下步骤是用户明确指定的固定步骤,你必须完整保留:
{json.dumps(pinned_steps, ensure_ascii=False, indent=2)}

你的任务是:
1. 保留所有固定步骤(is_pinned=True)
2. 在固定步骤之间或之后,根据需要补充必要的辅助步骤
3. 确保最终计划完整可执行
"""

        # 构建规划提示词
        prompt = self._build_planning_prompt(
            query=query,
            tools_catalog=tools_catalog,
            user_context=user_context,
            conversation_context=conversation_context,
            pinned_steps_info=pinned_steps_info,
        )

        # 调用 LLM 生成计划
        try:
            plan_json = await self._call_llm_for_plan(prompt)

            steps = plan_json.get("steps", [])
            state_schema = plan_json.get("state_schema", {})
            errors = plan_json.get("errors", [])
            warnings = plan_json.get("warnings", [])

            return ExecutionPlan(
                intent=plan_json.get("intent", "general"),
                subtasks=[self._dict_to_plan_step(s) for s in steps],
                expected_outcome=plan_json.get("expected_outcome"),
                state_schema=state_schema,
                errors=errors,
                warnings=warnings,
            )

        except Exception as e:
            # Fallback: 返回简单的单步计划
            return ExecutionPlan(
                intent="fallback",
                subtasks=[
                    PlanStep(
                        id="1",
                        description=f"处理查询：{query}",
                        tool=None,
                        parameters={"query": query},
                    )
                ],
                errors=[f"规划失败: {str(e)}"],
            )

    async def replan(
        self,
        original_plan: ExecutionPlan,
        error: Exception,
        execution_history: List,
        query: str,
        user_context: str = "",
        conversation_context: str = "",
    ) -> ExecutionPlan:
        """
        根据错误重新规划

        Args:
            original_plan: 原始计划
            error: 错误信息
            execution_history: 执行历史
            query: 原始查询
            user_context: 用户上下文
            conversation_context: 对话上下文

        Returns:
            新的执行计划
        """
        # 构建重规划提示词
        import json

        history_summary = json.dumps(
            [
                {"step": r.step_id, "success": r.success, "error": r.error}
                for r in execution_history
            ],
            ensure_ascii=False,
        )

        replan_prompt = f"""原计划执行失败，需要重新规划。

【原始查询】
{query}

【原计划】
{json.dumps([s.__dict__ for s in original_plan.subtasks], ensure_ascii=False, indent=2)}

【执行历史】
{history_summary}

【错误信息】
{str(error)}

请分析失败原因，生成新的执行计划。
"""

        try:
            plan_json = await self._call_llm_for_plan(replan_prompt)

            steps = plan_json.get("steps", [])
            state_schema = plan_json.get("state_schema", {})

            return ExecutionPlan(
                intent=plan_json.get("intent", "replan"),
                subtasks=[self._dict_to_plan_step(s) for s in steps],
                expected_outcome=plan_json.get("expected_outcome"),
                state_schema=state_schema,
                warnings=["这是重规划后的计划"],
            )

        except Exception:
            # Fallback: 返回原计划
            return original_plan

    def _build_planning_prompt(
        self,
        query: str,
        tools_catalog: str,
        user_context: str,
        conversation_context: str,
        pinned_steps_info: str,
    ) -> str:
        """构建规划提示词"""
        goals_text = (
            "\n".join(f"- {g}" for g in self.agent_goals)
            if self.agent_goals
            else "- 完成用户查询"
        )
        constraints_text = (
            "\n".join(f"- {c}" for c in self.agent_constraints)
            if self.agent_constraints
            else "- 无特殊约束"
        )

        return f"""你是一个专业的任务规划器。

【Agent目标】
{goals_text}

【执行约束】
{constraints_text}

【可用工具列表】
{tools_catalog}
{pinned_steps_info}
【用户上下文（长期记忆）】
{user_context or "无"}

【对话上下文（短期记忆）】
{conversation_context or "无"}

【核心要求】
1. 根据用户查询和Agent目标,规划执行步骤
2. 同时设计state schema(状态字段结构)
3. 每个步骤必须指定:
   - step: 步骤序号(从1开始)
   - name: 工具名称
   - description: 这一步做什么
   - read_fields: 需要读取的state字段列表
   - write_fields: 将写入的state字段列表
   - expectations: 自然语言描述的期望
   - on_fail_strategy: 失败策略

【返回格式】
请返回JSON:
{{
    "intent": "用户意图描述",
    "steps": [...],
    "state_schema": {{...}},
    "expected_outcome": "预期结果",
    "errors": [],
    "warnings": []
}}

【用户查询】
{query}
"""

    async def _call_llm_for_plan(self, prompt: str) -> Dict[str, Any]:
        """调用 LLM 生成计划"""
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的任务规划器，请返回有效的JSON格式。",
            },
            {"role": "user", "content": prompt},
        ]

        response = await self.llm_client.chat(messages)

        # 解析 JSON
        import json
        import re

        # 尝试提取 JSON
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            response = json_match.group(1)

        return json.loads(response)

    def _dict_to_plan_step(self, d: Dict[str, Any]) -> PlanStep:
        """将字典转换为 PlanStep"""
        return PlanStep(
            id=str(d.get("step", d.get("id", "1"))),
            description=d.get("description", ""),
            tool=d.get("name", d.get("tool")),
            parameters=d.get("parameters", {}),
            dependencies=d.get("dependencies", []),
            expectations=d.get("expectations"),
            on_fail_strategy=d.get("on_fail_strategy"),
            read_fields=d.get("read_fields", []),
            write_fields=d.get("write_fields", []),
            is_pinned=d.get("is_pinned", False),
            pinned_parameters=d.get("pinned_parameters"),
            parameter_template=d.get("parameter_template"),
            template_variables=d.get("template_variables"),
        )
