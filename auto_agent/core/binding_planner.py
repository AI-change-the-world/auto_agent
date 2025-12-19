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
            start_span,
            trace_llm_call,
            trace_binding_event,
            BindingAction,
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
                    1 for s in result.steps
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
                        source_type_stats[source_type] = source_type_stats.get(source_type, 0) + 1
                        binding_details.append({
                            "step_id": step.step_id,
                            "tool": step.tool,
                            "param": param_name,
                            "source": binding.source,
                            "source_type": source_type,
                            "confidence": binding.confidence,
                            "reasoning": binding.reasoning,
                        })

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
                params_info.append({
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                })

            steps_info.append({
                "step_id": subtask.id,
                "tool_name": subtask.tool,
                "description": subtask.description,
                "parameters": params_info,
                "output_schema": tool_def.output_schema or {},
                "read_fields": subtask.read_fields,
                "write_fields": subtask.write_fields,
            })

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

        return f"""你是一个参数绑定分析专家。分析执行计划中每个步骤的参数应该从哪里获取。

【用户输入】
{user_input}

【初始状态】
{state_json}

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

【置信度评估】
- 1.0: 完全确定（如用户明确提供、前序步骤明确输出）
- 0.8-0.9: 高度确定（语义匹配度高）
- 0.5-0.7: 中等确定（需要推理）
- 0.3-0.5: 低确定性（可能需要 fallback）
- 0.0-0.3: 非常不确定（建议 fallback）

【分析要点】
1. 第一个步骤的参数通常来自 user_input 或 literal
2. 后续步骤的参数通常来自前序步骤的 output
3. 注意参数类型匹配（如 array 类型参数应该绑定到 array 输出）
4. 参数名和输出字段名可能不完全一致，需要语义匹配
5. 如果无法确定来源，使用 "generated" 类型

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

                bindings[param_name] = ParameterBinding(
                    source=param_binding.get("source", ""),
                    source_type=source_type,
                    confidence=param_binding.get("confidence", 0.5),
                    fallback=BindingFallbackPolicy.LLM_INFER,
                    default_value=param_binding.get("default_value"),
                    reasoning=param_binding.get("reasoning"),
                )

            steps.append(StepBindings(
                step_id=step_id,
                tool=tool,
                bindings=bindings,
            ))

        return BindingPlan(
            steps=steps,
            confidence_threshold=self.confidence_threshold,
            reasoning=result.get("reasoning", ""),
            created_at=datetime.now().isoformat(),
        )
