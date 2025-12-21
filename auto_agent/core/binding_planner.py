"""
Binding Planner（参数绑定规划器）

核心功能：
- 在规划阶段分析参数依赖链路
- 生成静态绑定配置，减少运行时 LLM 调用
- 支持置信度评估和 fallback 策略

设计思路：
- 将参数构造从"运行时 LLM 推理"提前到"规划时静态绑定"
- 一次 LLM 调用分析所有步骤的参数来源
- 执行时直接按绑定取值，只有低置信度时才 fallback 到 LLM
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from auto_agent.llm.client import LLMClient
from auto_agent.models import (
    BindingFallbackPolicy,
    BindingPlan,
    BindingSourceType,
    ExecutionPlan,
    ParameterBinding,
    StepBindings,
    ToolDefinition,
)
from auto_agent.tools.registry import ToolRegistry


class BindingPlanner:
    """
    参数绑定规划器

    在 TaskPlanner 生成执行计划后，分析每个步骤的参数来源，
    生成静态绑定配置，减少运行时 LLM 调用。

    使用方式：
    ```python
    # 1. 先用 TaskPlanner 生成执行计划
    plan = await task_planner.plan(query, ...)

    # 2. 用 BindingPlanner 生成参数绑定
    binding_plan = await binding_planner.create_binding_plan(
        execution_plan=plan,
        user_input=query,
        tool_registry=registry,
    )

    # 3. 执行时使用 binding_plan
    # executor 会根据 binding_plan 解析参数，而不是每步都调用 LLM
    ```
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        confidence_threshold: float = 0.7,
    ):
        """
        初始化 BindingPlanner

        Args:
            llm_client: LLM 客户端
            tool_registry: 工具注册表
            confidence_threshold: 置信度阈值，低于此值触发 fallback
        """
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.confidence_threshold = confidence_threshold

    async def create_binding_plan(
        self,
        execution_plan: ExecutionPlan,
        user_input: str,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> BindingPlan:
        """
        为执行计划创建参数绑定

        Args:
            execution_plan: 执行计划（由 TaskPlanner 生成）
            user_input: 用户原始输入
            initial_state: 初始状态（可选）

        Returns:
            BindingPlan: 参数绑定计划
        """
        import time

        from auto_agent.tracing import (
            BindingAction,
            start_span,
            trace_binding_event,
            trace_llm_call,
        )

        start_time = time.time()

        # 收集所有步骤的工具参数信息
        steps_info = self._collect_steps_info(execution_plan)

        if not steps_info:
            # 没有需要绑定的步骤
            return BindingPlan(
                steps=[],
                confidence_threshold=self.confidence_threshold,
                reasoning="无需绑定参数（无工具步骤）",
                created_at=datetime.now().isoformat(),
            )

        # 统计参数信息
        total_params = sum(len(s.get("parameters", [])) for s in steps_info)
        required_params = sum(
            sum(1 for p in s.get("parameters", []) if p.get("required", False))
            for s in steps_info
        )

        # 构建 prompt 让 LLM 分析参数链路
        prompt = self._build_binding_prompt(
            steps_info=steps_info,
            user_input=user_input,
            initial_state=initial_state,
        )

        # 调用 LLM 生成绑定计划
        with start_span(
            "binding_planner_llm",
            span_type="binding_plan",
            steps_count=len(steps_info),
            total_params=total_params,
            required_params=required_params,
            confidence_threshold=self.confidence_threshold,
        ):
            try:
                binding_result = await self._call_llm_for_binding(prompt)

                # 记录 LLM 调用详情
                trace_llm_call(
                    purpose="binding_plan",
                    prompt=prompt,
                    response=json.dumps(binding_result, ensure_ascii=False),
                    success=True,
                    metadata={
                        "steps_count": len(steps_info),
                        "total_params": total_params,
                        "required_params": required_params,
                    },
                )

                result = self._parse_binding_result(binding_result, execution_plan)

                # 统计绑定结果
                total_bindings = sum(len(s.bindings) for s in result.steps)
                high_confidence = sum(
                    1
                    for s in result.steps
                    for b in s.bindings.values()
                    if b.confidence >= self.confidence_threshold
                )
                low_confidence = total_bindings - high_confidence

                # 按来源类型统计
                source_type_stats = {}
                binding_details = []
                for step in result.steps:
                    for param_name, binding in step.bindings.items():
                        source_type = binding.source_type.value
                        source_type_stats[source_type] = (
                            source_type_stats.get(source_type, 0) + 1
                        )
                        binding_details.append(
                            {
                                "step_id": step.step_id,
                                "tool": step.tool,
                                "param": param_name,
                                "source": binding.source,
                                "source_type": source_type,
                                "confidence": binding.confidence,
                                "reasoning": binding.reasoning,
                            }
                        )

                # 记录绑定事件
                duration_ms = (time.time() - start_time) * 1000
                trace_binding_event(
                    action=BindingAction.PLAN_CREATE,
                    step_id="all",
                    tool_name="binding_planner",
                    bindings_count=total_bindings,
                    resolved_count=high_confidence,
                    fallback_count=low_confidence,
                    confidence_threshold=self.confidence_threshold,
                    binding_details=binding_details,
                    duration_ms=duration_ms,
                    source_type_stats=source_type_stats,
                    steps_count=len(steps_info),
                    total_params=total_params,
                    required_params=required_params,
                )

                # 添加解析统计到 reasoning
                result.reasoning = (
                    f"{result.reasoning} "
                    f"[统计: {total_bindings} 个绑定, {high_confidence} 个高置信度, "
                    f"{low_confidence} 个需要 fallback]"
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                # 记录失败的 LLM 调用
                trace_llm_call(
                    purpose="binding_plan",
                    prompt=prompt,
                    response="",
                    success=False,
                    error=str(e),
                    duration_ms=duration_ms,
                )

                # 记录失败的绑定事件
                trace_binding_event(
                    action=BindingAction.PLAN_CREATE,
                    step_id="all",
                    tool_name="binding_planner",
                    bindings_count=0,
                    resolved_count=0,
                    fallback_count=total_params,
                    confidence_threshold=self.confidence_threshold,
                    binding_details=[],
                    duration_ms=duration_ms,
                    error=str(e),
                )

                # LLM 调用失败，返回空绑定计划（执行时会 fallback 到原有逻辑）
                return BindingPlan(
                    steps=[],
                    confidence_threshold=self.confidence_threshold,
                    reasoning=f"绑定规划失败: {str(e)}",
                    created_at=datetime.now().isoformat(),
                )

    def _collect_steps_info(
        self,
        execution_plan: ExecutionPlan,
    ) -> List[Dict[str, Any]]:
        """
        收集所有步骤的工具参数信息

        Returns:
            步骤信息列表，每个元素包含:
            - step_id: 步骤 ID
            - tool_name: 工具名称
            - description: 步骤描述
            - parameters: 工具参数定义列表
            - output_schema: 工具输出 schema
        """
        steps_info = []

        for subtask in execution_plan.subtasks:
            if not subtask.tool:
                continue

            tool = self.tool_registry.get_tool(subtask.tool)
            if not tool:
                continue

            tool_def: ToolDefinition = tool.definition

            # 收集参数信息
            params_info = []
            for p in tool_def.parameters:
                params_info.append(
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description,
                        "required": p.required,
                        "default": p.default,
                    }
                )

            steps_info.append(
                {
                    "step_id": subtask.id,
                    "tool_name": subtask.tool,
                    "description": subtask.description,
                    # 规划器（TaskPlanner）可能已经为这一步提供了显式参数（含默认值/固定值）
                    # BindingPlanner 应优先认为这些参数“已确定”，避免重复绑定。
                    "preset_parameters": subtask.parameters or {},
                    "parameters": params_info,
                    "output_schema": tool_def.output_schema or {},
                    "read_fields": subtask.read_fields,
                    "write_fields": subtask.write_fields,
                }
            )

        return steps_info

    def _build_binding_prompt(
        self,
        steps_info: List[Dict[str, Any]],
        user_input: str,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建参数绑定分析的 prompt"""

        steps_json = json.dumps(steps_info, ensure_ascii=False, indent=2)
        state_json = json.dumps(initial_state or {}, ensure_ascii=False, indent=2)
        available_inputs = []
        if initial_state and isinstance(initial_state, dict):
            inp = initial_state.get("inputs")
            if isinstance(inp, dict):
                available_inputs = list(inp.keys())
        inputs_hint = (
            f"可用的 user_input 字段（source 必须从中选择）: {available_inputs}\n"
            if available_inputs
            else ""
        )

        return f"""你是一个参数绑定分析专家。分析执行计划中每个步骤的参数应该从哪里获取。

【用户输入】
{user_input}

【初始状态】
{state_json}

【提示】
{inputs_hint}

【执行步骤】
{steps_json}

【任务】
分析每个步骤的每个参数应该从哪里获取值，生成参数绑定配置。

【绑定来源类型】
1. "user_input": 来自用户输入，source 填写字段名（如 "query"）
2. "step_output": 来自前序步骤输出，source 格式为 "step_{{id}}.output.{{field}}"（如 "step_1.output.endpoints"）
3. "state": 来自状态字段，source 填写字段路径（如 "documents"）
4. "literal": 字面量值，需要在 default_value 中提供具体值
5. "generated": 无法确定来源，需要运行时由 LLM 生成

【默认值与 preset 参数规则（重要）】
1. 每个参数在 steps_json 的 parameters 里可能带有 "default"（工具 schema 的默认值）
2. 如果某一步的 preset_parameters 已经包含某个参数的值，表示该参数已经确定：
   - 你应该 **不要** 在 bindings 中返回这个参数（避免重复设置）
3. 如果参数没有可靠来源，但工具 schema 给了 default，你可以选择：
   - source_type="generated"，fallback="use_default"，default_value=<schema default>
4. 若参数就是固定字面量（例如 limit=10），使用：
   - source_type="literal"，default_value=具体值，fallback="use_default"

【置信度评估】
- 1.0: 完全确定（如用户明确提供、前序步骤明确输出）
- 0.8-0.9: 高度确定（语义匹配度高）
- 0.5-0.7: 中等确定（需要推理）
- 0.3-0.5: 低确定性（可能需要 fallback）
- 0.0-0.3: 非常不确定（建议 fallback）

【fallback 策略】
- "llm_infer": 默认策略，运行时让 LLM 推理参数
- "use_default": 使用 default_value（或工具 schema default）作为回退
- "error": 无法构造时直接报错（仅在强约束场景使用）

【分析要点】
1. 第一个步骤的参数通常来自 user_input 或 literal
2. 后续步骤的参数通常来自前序步骤的 output
3. 注意参数类型匹配（如 array 类型参数应该绑定到 array 输出）
4. 参数名和输出字段名可能不完全一致，需要语义匹配
5. 如果无法确定来源，使用 "generated" 类型
6. 对于 source_type="user_input"，source 必须是【提示】中的字段名；否则请使用 "literal"

【返回格式】
```json
{{
    "bindings": [
        {{
            "step_id": "1",
            "tool": "tool_name",
            "bindings": {{
                "param_name": {{
                    "source": "来源路径",
                    "source_type": "user_input|step_output|state|literal|generated",
                    "confidence": 0.0-1.0,
                    "fallback": "llm_infer|use_default|error",
                    "default_value": null,
                    "reasoning": "简短说明为什么这样绑定"
                }}
            }}
        }}
    ],
    "reasoning": "整体分析说明"
}}
```

请分析并返回 JSON："""

    async def _call_llm_for_binding(self, prompt: str) -> Dict[str, Any]:
        """调用 LLM 生成绑定配置"""
        messages = [
            {
                "role": "system",
                "content": "你是一个参数绑定分析专家，请返回有效的 JSON 格式。",
            },
            {"role": "user", "content": prompt},
        ]

        response = await self.llm_client.chat(
            messages,
            temperature=0.1,
            trace_purpose="binding_plan",
        )

        # 提取 JSON
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            response = json_match.group(1)
        else:
            # 尝试直接匹配 JSON 对象
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                response = json_match.group()

        return json.loads(response)

    def _parse_binding_result(
        self,
        result: Dict[str, Any],
        execution_plan: ExecutionPlan,
    ) -> BindingPlan:
        """解析 LLM 返回的绑定结果"""
        steps = []

        for binding_data in result.get("bindings", []):
            step_id = str(binding_data.get("step_id", ""))
            tool = binding_data.get("tool", "")

            bindings = {}
            for param_name, param_binding in binding_data.get("bindings", {}).items():
                source_type_str = param_binding.get("source_type", "generated")

                # 映射 source_type
                source_type_map = {
                    "user_input": BindingSourceType.USER_INPUT,
                    "step_output": BindingSourceType.STEP_OUTPUT,
                    "state": BindingSourceType.STATE,
                    "literal": BindingSourceType.LITERAL,
                    "generated": BindingSourceType.GENERATED,
                }
                source_type = source_type_map.get(
                    source_type_str, BindingSourceType.GENERATED
                )

                # 映射 fallback（兼容旧返回：缺省 llm_infer）
                fallback_str = (param_binding.get("fallback") or "llm_infer").lower()
                fallback_map = {
                    "llm_infer": BindingFallbackPolicy.LLM_INFER,
                    "use_default": BindingFallbackPolicy.USE_DEFAULT,
                    "error": BindingFallbackPolicy.ERROR,
                }
                fallback = fallback_map.get(
                    fallback_str, BindingFallbackPolicy.LLM_INFER
                )

                bindings[param_name] = ParameterBinding(
                    source=param_binding.get("source", ""),
                    source_type=source_type,
                    confidence=param_binding.get("confidence", 0.5),
                    fallback=fallback,
                    default_value=param_binding.get("default_value"),
                    reasoning=param_binding.get("reasoning"),
                )

            steps.append(
                StepBindings(
                    step_id=step_id,
                    tool=tool,
                    bindings=bindings,
                )
            )

        plan = BindingPlan(
            steps=steps,
            confidence_threshold=self.confidence_threshold,
            reasoning=result.get("reasoning", ""),
            created_at=datetime.now().isoformat(),
        )
        # 注入工具 schema 默认值，确保 default_value 在 binding_plan 中可用
        self._enrich_binding_plan_with_tool_defaults(plan, execution_plan)
        return plan

    def _enrich_binding_plan_with_tool_defaults(
        self,
        binding_plan: BindingPlan,
        execution_plan: ExecutionPlan,
    ) -> None:
        """
        用工具 schema 的默认值补齐 binding_plan 中每个参数的 default_value。

        目的：
        - 避免 LLM 未输出 default_value 时丢失工具默认值
        - 为运行时 fallback（USE_DEFAULT）提供稳定数据
        """
        # step_id -> tool_name
        step_tool_map = {s.id: s.tool for s in execution_plan.subtasks if s.tool}

        for step in binding_plan.steps:
            tool_name = step.tool or step_tool_map.get(step.step_id)
            if not tool_name:
                continue

            tool = self.tool_registry.get_tool(tool_name)
            if not tool:
                continue

            tool_def: ToolDefinition = tool.definition
            default_map = {p.name: p.default for p in tool_def.parameters}

            for param_name, binding in step.bindings.items():
                tool_default = default_map.get(param_name)
                # 1) 无论 LLM 如何绑定，都可把 tool default 写入 default_value，便于后续 fallback
                if binding.default_value is None and tool_default is not None:
                    binding.default_value = tool_default

                # 2) 对 GENERATED 类型，如果工具有默认值，优先使用 USE_DEFAULT 以减少运行时 LLM
                if (
                    binding.source_type == BindingSourceType.GENERATED
                    and binding.fallback == BindingFallbackPolicy.LLM_INFER
                    and tool_default is not None
                ):
                    binding.fallback = BindingFallbackPolicy.USE_DEFAULT
