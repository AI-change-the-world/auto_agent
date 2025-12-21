"""
重规划模块

负责执行模式检测、增量重规划、替代计划生成。
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from auto_agent.core.executor.state import compress_state_for_llm
from auto_agent.models import (
    ExecutionPlan,
    ExecutionStrategy,
    PlanStep,
    SubTaskResult,
    ToolReplanPolicy,
)

if TYPE_CHECKING:
    from auto_agent.core.context import ExecutionContext
    from auto_agent.llm.client import LLMClient
    from auto_agent.tools.registry import ToolRegistry


class PatternType(Enum):
    """执行模式类型"""

    CIRCULAR_DEPENDENCY = "circular_dependency"
    REPEATED_FAILURE = "repeated_failure"
    INEFFICIENT_SEQUENCE = "inefficient_sequence"
    RESOURCE_BOTTLENECK = "resource_bottleneck"


@dataclass
class ExecutionPattern:
    """检测到的执行模式"""

    pattern_type: PatternType
    description: str
    frequency: int
    success_rate: float
    suggested_optimization: Optional[str] = None


class ReplanManager:
    """
    重规划管理器

    负责：
    1. 执行模式检测
    2. 判断是否需要重规划
    3. 增量重规划
    4. 全量重规划
    """

    def __init__(
        self,
        llm_client: Optional["LLMClient"] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        context: Optional["ExecutionContext"] = None,
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.context = context

    def detect_execution_patterns(
        self,
        execution_history: List[SubTaskResult],
    ) -> List[ExecutionPattern]:
        """
        检测执行模式（循环、重复失败等）

        检测规则：
        1. 重复失败模式：最近 5 次执行中有 3 次以上失败
        2. 循环依赖模式：同一步骤执行超过 3 次

        Args:
            execution_history: 执行历史记录列表

        Returns:
            检测到的执行模式列表
        """
        patterns: List[ExecutionPattern] = []

        if not execution_history:
            return patterns

        # 1. 检测重复失败模式
        recent_results = (
            execution_history[-5:] if len(execution_history) >= 5 else execution_history
        )
        recent_failures = [r for r in recent_results if not r.success]

        if len(recent_failures) >= 3:
            success_count = len([r for r in recent_results if r.success])
            success_rate = (
                success_count / len(recent_results) if recent_results else 0.0
            )

            patterns.append(
                ExecutionPattern(
                    pattern_type=PatternType.REPEATED_FAILURE,
                    description=f"连续多次执行失败：最近 {len(recent_results)} 次执行中有 {len(recent_failures)} 次失败",
                    frequency=len(recent_failures),
                    success_rate=success_rate,
                    suggested_optimization="建议检查工具配置或参数，考虑使用替代工具或重新规划",
                )
            )

        # 2. 检测循环依赖
        step_counts: Dict[str, int] = {}
        for r in execution_history:
            step_id = r.step_id
            step_counts[step_id] = step_counts.get(step_id, 0) + 1

        for step_id, count in step_counts.items():
            if count > 3:
                step_results = [r for r in execution_history if r.step_id == step_id]
                step_success_count = len([r for r in step_results if r.success])
                step_success_rate = (
                    step_success_count / len(step_results) if step_results else 0.0
                )

                patterns.append(
                    ExecutionPattern(
                        pattern_type=PatternType.CIRCULAR_DEPENDENCY,
                        description=f"步骤 {step_id} 重复执行 {count} 次，可能存在循环依赖",
                        frequency=count,
                        success_rate=step_success_rate,
                        suggested_optimization="建议检查步骤依赖关系，避免循环执行",
                    )
                )

        return patterns

    async def should_trigger_replan(
        self,
        step: PlanStep,
        result: SubTaskResult,
        execution_strategy: Optional[ExecutionStrategy],
        current_step_index: int,
        results: List[SubTaskResult],
    ) -> Tuple[bool, str]:
        """
        判断是否需要触发 replan 检查

        优先级：工具级策略 > 全局周期性策略 > 失败触发

        Args:
            step: 当前步骤
            result: 执行结果
            execution_strategy: 全局执行策略
            current_step_index: 当前步骤索引
            results: 执行历史

        Returns:
            (should_replan, reason): 是否需要 replan 及原因
        """
        # 获取工具级策略
        tool = (
            self.tool_registry.get_tool(step.tool)
            if self.tool_registry and step.tool
            else None
        )
        policy: Optional[ToolReplanPolicy] = None
        if tool and hasattr(tool, "definition") and tool.definition.replan_policy:
            policy = tool.definition.replan_policy

        # 1. 工具级强制检查
        if policy and policy.force_replan_check:
            if policy.replan_condition and self.llm_client:
                should_replan = await self._evaluate_replan_condition(
                    condition=policy.replan_condition,
                    result=result,
                    step=step,
                )
                if should_replan:
                    return (
                        True,
                        f"工具 {step.tool} 触发条件满足: {policy.replan_condition}",
                    )
            else:
                return True, f"工具 {step.tool} 配置了强制 replan 检查"

        # 2. 全局策略禁用
        if execution_strategy and not execution_strategy.enable_replan:
            return False, "全局策略禁用了 replan"

        # 3. 全局周期性检查
        if execution_strategy and execution_strategy.replan_trigger == "periodic":
            interval = execution_strategy.replan_interval
            if interval > 0 and (current_step_index + 1) % interval == 0:
                if policy and not policy.high_impact:
                    return False, "简单工具，跳过周期性检查"
                return True, f"周期性检查（每 {interval} 步）"

        # 4. 主动规划模式
        if execution_strategy and execution_strategy.replan_trigger == "proactive":
            if policy and policy.high_impact:
                return True, f"高影响力工具 {step.tool} 执行后主动检查"

        # 5. 失败触发
        if not result.success:
            if execution_strategy and execution_strategy.replan_trigger == "on_failure":
                return True, "执行失败触发 replan"
            recent_failures = sum(1 for r in results[-3:] if not r.success)
            if recent_failures >= 2:
                return True, f"连续 {recent_failures} 次失败"

        return False, ""

    async def _evaluate_replan_condition(
        self,
        condition: str,
        result: SubTaskResult,
        step: PlanStep,
    ) -> bool:
        """使用 LLM 评估自定义的 replan 条件"""
        if not self.llm_client:
            return False

        prompt = f"""判断以下条件是否满足。

【条件】
{condition}

【步骤信息】
工具: {step.tool}
描述: {step.description}

【执行结果】
成功: {result.success}
输出: {json.dumps(result.output, ensure_ascii=False, default=str)[:1000] if result.output else "无"}
错误: {result.error or "无"}

请判断条件是否满足，只返回 "yes" 或 "no"。"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                trace_purpose="replan_condition",
            )
            return response.strip().lower() in ["yes", "是", "true", "满足"]
        except Exception:
            return False

    async def evaluate_and_replan(
        self,
        current_plan: ExecutionPlan,
        execution_history: List[SubTaskResult],
        state: Dict[str, Any],
        context_changed: bool = False,
        current_step_index: int = 0,
        use_incremental: bool = True,
    ) -> Optional[ExecutionPlan]:
        """
        评估当前计划有效性，必要时动态重规划

        触发条件：
        1. 连续失败超过阈值
        2. 检测到循环模式
        3. 上下文发生重大变化

        Args:
            current_plan: 当前执行计划
            execution_history: 执行历史记录列表
            state: 当前状态字典
            context_changed: 上下文是否发生变化
            current_step_index: 当前步骤索引
            use_incremental: 是否使用增量重规划

        Returns:
            新的执行计划，如果不需要重规划则返回 None
        """
        # 上下文变化强制全量重规划
        if context_changed:
            patterns = [
                ExecutionPattern(
                    pattern_type=PatternType.INEFFICIENT_SEQUENCE,
                    description="上下文发生变化，需要重新评估计划",
                    frequency=1,
                    success_rate=0.0,
                    suggested_optimization="根据新的上下文重新规划",
                )
            ]
            return await self._generate_alternative_plan(
                current_plan, patterns, state, execution_history
            )

        # 检测执行模式
        patterns = self.detect_execution_patterns(execution_history)

        if not patterns:
            return None

        # 检查是否有需要触发重规划的模式
        problem_patterns = [
            p
            for p in patterns
            if p.pattern_type
            in [PatternType.CIRCULAR_DEPENDENCY, PatternType.REPEATED_FAILURE]
        ]

        if not problem_patterns:
            return None

        # 判断是否使用增量重规划
        has_severe_issue = any(
            p.pattern_type == PatternType.CIRCULAR_DEPENDENCY for p in problem_patterns
        )

        if use_incremental and not has_severe_issue and current_step_index > 0:
            return await self._incremental_replan(
                current_plan=current_plan,
                current_step_index=current_step_index,
                problem_description=problem_patterns[0].description,
                state=state,
                execution_history=execution_history,
            )
        else:
            return await self._generate_alternative_plan(
                current_plan, problem_patterns, state, execution_history
            )

    async def _incremental_replan(
        self,
        current_plan: ExecutionPlan,
        current_step_index: int,
        problem_description: str,
        state: Dict[str, Any],
        execution_history: List[SubTaskResult],
    ) -> Optional[ExecutionPlan]:
        """
        增量式重规划

        只调整后续步骤，保留已完成的工作。
        """
        if not self.llm_client:
            return None

        # 分离已完成步骤和待执行步骤
        completed_steps = current_plan.subtasks[:current_step_index]
        remaining_steps = current_plan.subtasks[current_step_index:]

        # 构建已完成步骤摘要
        completed_summary = []
        for i, step in enumerate(completed_steps):
            result = next((r for r in execution_history if r.step_id == step.id), None)
            completed_summary.append(
                {
                    "step": i + 1,
                    "id": step.id,
                    "tool": step.tool,
                    "description": step.description,
                    "success": result.success if result else "unknown",
                    "output_keys": list(result.output.keys())[:5]
                    if result and result.output
                    else [],
                }
            )

        # 构建待执行步骤摘要
        remaining_summary = []
        for i, step in enumerate(remaining_steps):
            remaining_summary.append(
                {
                    "step": current_step_index + i + 1,
                    "id": step.id,
                    "tool": step.tool,
                    "description": step.description,
                }
            )

        # 获取工作记忆上下文
        working_memory_context = ""
        if self.context:
            working_memory_context = self.context.working_memory.get_relevant_context(
                ""
            )
            consistency_context = self.context.consistency_checker.get_context_for_llm()
            if consistency_context:
                working_memory_context += "\n\n" + consistency_context

        # 获取可用工具列表
        tools_catalog = (
            self.tool_registry.get_tools_catalog()
            if self.tool_registry
            else "无可用工具信息"
        )

        prompt = f"""你是一个智能任务规划器。当前执行计划遇到了问题，需要调整后续步骤。

【重要】这是增量式重规划，必须保留已完成的步骤，只调整后续步骤。

【问题描述】
{problem_description}

【已完成的步骤】（必须保留，不能修改）
{json.dumps(completed_summary, ensure_ascii=False, indent=2)}

【原计划中待执行的步骤】（需要调整）
{json.dumps(remaining_summary, ensure_ascii=False, indent=2)}

【当前状态摘要】
{compress_state_for_llm(state)}

【工作记忆】
{working_memory_context if working_memory_context else "无"}

【可用工具】
{tools_catalog}

【任务】
基于已完成步骤的产出，重新规划后续步骤来完成原始目标。

要求：
1. 必须利用已完成步骤的产出
2. 新步骤的 read_fields 应该引用已完成步骤写入的字段
3. 避免重复之前失败的步骤
4. 如果某个工具多次失败，考虑使用替代工具

请返回 JSON 格式的新计划（只包含新的后续步骤）：
```json
{{
    "analysis": "问题分析和调整理由",
    "new_steps": [
        {{
            "step": {current_step_index + 1},
            "name": "工具名称",
            "description": "步骤描述",
            "read_fields": ["需要读取的字段"],
            "write_fields": ["将写入的字段"],
            "expectations": "期望结果",
            "on_fail_strategy": "失败策略"
        }}
    ],
    "expected_outcome": "预期结果"
}}
```"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                trace_purpose="incremental_replan",
            )

            # 提取 JSON
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    response = json_match.group()

            data = json.loads(response)

            # 构建新的步骤列表
            new_steps = []
            for step_data in data.get("new_steps", []):
                new_step = PlanStep(
                    id=f"replan_{step_data.get('step', len(completed_steps) + len(new_steps) + 1)}",
                    description=step_data.get("description", ""),
                    tool=step_data.get("name"),
                    parameters=step_data.get("parameters", {}),
                    dependencies=[],
                    expectations=step_data.get("expectations"),
                    on_fail_strategy=step_data.get("on_fail_strategy", "retry"),
                    read_fields=step_data.get("read_fields", []),
                    write_fields=step_data.get("write_fields", []),
                )
                new_steps.append(new_step)

            if not new_steps:
                return None

            # 合并已完成步骤和新步骤
            all_steps = list(completed_steps) + new_steps

            return ExecutionPlan(
                intent=current_plan.intent,
                subtasks=all_steps,
                expected_outcome=data.get(
                    "expected_outcome", current_plan.expected_outcome
                ),
                warnings=[f"增量重规划: {data.get('analysis', problem_description)}"],
            )

        except Exception:
            return None

    async def _generate_alternative_plan(
        self,
        current_plan: ExecutionPlan,
        patterns: List[ExecutionPattern],
        state: Dict[str, Any],
        execution_history: List[SubTaskResult],
    ) -> Optional[ExecutionPlan]:
        """
        当检测到问题模式时生成替代计划（全量重规划）
        """
        if not self.llm_client:
            return None

        # 构建问题模式描述
        patterns_description = "\n".join(
            [
                f"- {p.pattern_type.value}: {p.description} (频率: {p.frequency}, 成功率: {p.success_rate:.1%})"
                for p in patterns
            ]
        )

        # 构建执行历史摘要
        history_summary = []
        for r in execution_history[-10:]:
            history_summary.append(
                {
                    "step_id": r.step_id,
                    "success": r.success,
                    "error": r.error[:200] if r.error else None,
                }
            )

        # 构建当前计划摘要
        plan_summary = []
        for step in current_plan.subtasks:
            plan_summary.append(
                {
                    "id": step.id,
                    "tool": step.tool,
                    "description": step.description,
                }
            )

        tools_catalog = (
            self.tool_registry.get_tools_catalog()
            if self.tool_registry
            else "无可用工具信息"
        )

        prompt = f"""你是一个智能任务规划器。当前执行计划遇到了问题，需要生成替代方案。

【检测到的问题模式】
{patterns_description}

【当前计划】
{json.dumps(plan_summary, ensure_ascii=False, indent=2)}

【执行历史（最近 10 条）】
{json.dumps(history_summary, ensure_ascii=False, indent=2)}

【当前状态摘要】
{compress_state_for_llm(state)}

【可用工具】
{tools_catalog}

【任务】
分析失败原因，生成一个新的执行计划来完成原始目标。

要求：
1. 避免重复之前失败的步骤
2. 如果某个工具多次失败，考虑使用替代工具
3. 如果检测到循环依赖，重新设计步骤顺序
4. 保留已成功执行的步骤结果

请返回 JSON 格式的新计划：
```json
{{
    "intent": "替代计划的意图描述",
    "analysis": "失败原因分析",
    "steps": [
        {{
            "step": 1,
            "name": "工具名称",
            "description": "步骤描述",
            "read_fields": ["需要读取的字段"],
            "write_fields": ["将写入的字段"],
            "expectations": "期望结果",
            "on_fail_strategy": "失败策略"
        }}
    ],
    "expected_outcome": "预期结果"
}}
```"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                trace_purpose="replan",
            )

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    response = json_match.group()

            plan_json = json.loads(response)

            steps = plan_json.get("steps", [])
            new_subtasks = []

            for s in steps:
                new_subtasks.append(
                    PlanStep(
                        id=str(s.get("step", len(new_subtasks) + 1)),
                        description=s.get("description", ""),
                        tool=s.get("name", s.get("tool")),
                        parameters=s.get("parameters", {}),
                        dependencies=s.get("dependencies", []),
                        expectations=s.get("expectations"),
                        on_fail_strategy=s.get("on_fail_strategy"),
                        read_fields=s.get("read_fields", []),
                        write_fields=s.get("write_fields", []),
                    )
                )

            return ExecutionPlan(
                intent=plan_json.get("intent", "alternative_plan"),
                subtasks=new_subtasks,
                expected_outcome=plan_json.get("expected_outcome"),
                state_schema=current_plan.state_schema,
                warnings=[
                    f"这是替代计划，原因: {plan_json.get('analysis', '检测到执行问题')}"
                ],
            )

        except Exception:
            return None
