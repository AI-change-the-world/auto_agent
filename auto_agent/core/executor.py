"""
Execution Engine（执行引擎）

核心功能：
- 执行计划中的每个步骤
- 期望验证（ExpectationEvaluator）
- 失败策略解析
- 状态更新
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

from auto_agent.llm.client import LLMClient
from auto_agent.models import (
    ExecutionPlan,
    FailAction,
    PlanStep,
    SubTaskResult,
    ValidationMode,
)
from auto_agent.retry.controller import RetryController
from auto_agent.retry.models import RetryConfig
from auto_agent.tools.registry import ToolRegistry


class ExecutionEngine:
    """
    执行引擎

    功能：
    - 执行计划中的每个步骤（带重试）
    - 期望评估（自然语言期望 -> 通过/不通过）
    - 失败策略解析（重试/回退/fallback/abort）
    - 状态更新
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        retry_config: RetryConfig,
        llm_client: Optional[LLMClient] = None,
    ):
        self.tool_registry = tool_registry
        self.retry_controller = RetryController(retry_config, llm_client)
        self.llm_client = llm_client

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        state: Dict[str, Any],
        conversation_id: str,
        on_step_complete: Optional[Callable] = None,
    ) -> Tuple[List[SubTaskResult], Dict[str, Any]]:
        """
        执行完整计划

        Args:
            plan: 执行计划
            state: 初始状态字典
            conversation_id: 对话ID
            on_step_complete: 步骤完成回调

        Returns:
            (List[SubTaskResult], 最终状态)
        """
        results = []
        current_step_index = 0
        max_iterations = state.get("control", {}).get("max_iterations", 20)
        iterations = 0

        while current_step_index < len(plan.subtasks) and iterations < max_iterations:
            iterations += 1
            subtask = plan.subtasks[current_step_index]

            result = await self._execute_subtask(subtask, state, conversation_id)
            results.append(result)

            # 更新状态
            if result.success:
                self._update_state_from_result(subtask.tool, result.output, state)

            # 回调
            if on_step_complete:
                await on_step_complete(subtask, result)

            # 处理失败
            if not result.success:
                action = await self._handle_failure(subtask, result, state, plan)

                if action.type == "retry":
                    continue  # 不移动指针，重试当前步骤
                elif action.type == "goto":
                    # 跳转到指定步骤
                    for i, s in enumerate(plan.subtasks):
                        if s.id == action.target_step:
                            current_step_index = i
                            break
                    continue
                elif action.type == "abort":
                    break
                # fallback: 继续下一步

            current_step_index += 1

        state["control"]["iterations"] = iterations
        return results, state

    async def _execute_subtask(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        conversation_id: str,
    ) -> SubTaskResult:
        """
        执行单个子任务（带重试和验证）
        """
        # 如果没有指定工具，直接返回成功
        if not subtask.tool:
            return SubTaskResult(
                step_id=subtask.id,
                success=True,
                output=subtask.parameters,
            )

        # 获取工具
        tool = self.tool_registry.get_tool(subtask.tool)
        if not tool:
            return SubTaskResult(
                step_id=subtask.id,
                success=False,
                error=f"工具未找到: {subtask.tool}",
            )

        # 执行工具（带重试）
        try:
            output = await self.retry_controller.execute_with_retry(
                tool.execute,
                **subtask.parameters,
            )

            # 验证期望
            if subtask.expectations and output.get("success"):
                passed, reason = await self._evaluate_expectations(
                    tool=tool,
                    result=output,
                    expectations=subtask.expectations,
                    state=state,
                )

                if not passed:
                    return SubTaskResult(
                        step_id=subtask.id,
                        success=False,
                        output=output,
                        error=reason,
                        expectation_failed=True,
                        evaluation_reason=reason,
                    )

            return SubTaskResult(
                step_id=subtask.id,
                success=output.get("success", True),
                output=output,
                error=output.get("error"),
            )

        except Exception as e:
            return SubTaskResult(
                step_id=subtask.id,
                success=False,
                error=str(e),
            )

    async def _evaluate_expectations(
        self,
        tool: Any,
        result: Dict[str, Any],
        expectations: str,
        state: Dict[str, Any],
        mode: ValidationMode = ValidationMode.LOOSE,
    ) -> Tuple[bool, str]:
        """
        评估执行结果是否满足期望

        验证逻辑：
        1. 如果工具有 validate_function，调用它
        2. 否则只检查 success 字段
        """
        # 尝试调用工具的验证函数
        validate_fn = tool.definition.validate_function if hasattr(tool, "definition") else None

        if validate_fn is None:
            success = result.get("success", False)
            if success:
                return True, "无需验证，执行成功即通过"
            else:
                return False, f"执行失败: {result.get('error', '未知错误')}"

        # 调用自定义验证函数
        try:
            if asyncio.iscoroutinefunction(validate_fn):
                return await validate_fn(
                    result, expectations, state, mode, self.llm_client, None
                )
            else:
                return validate_fn(
                    result, expectations, state, mode, self.llm_client, None
                )
        except Exception as e:
            return result.get("success", False), f"验证异常: {str(e)}"

    async def _handle_failure(
        self,
        subtask: PlanStep,
        result: SubTaskResult,
        state: Dict[str, Any],
        plan: ExecutionPlan,
    ) -> FailAction:
        """
        处理失败，解析失败策略
        """
        # 记录失败
        if "control" not in state:
            state["control"] = {}
        if "failed_steps" not in state["control"]:
            state["control"]["failed_steps"] = []

        state["control"]["failed_steps"].append({
            "step": subtask.id,
            "name": subtask.tool,
            "error": result.error,
        })

        # 记录上次失败原因（供重试时参考）
        if "last_failure" not in state:
            state["last_failure"] = {}
        state["last_failure"][subtask.tool or "unknown"] = {
            "reason": result.evaluation_reason or result.error,
            "expectations": subtask.expectations,
            "step": subtask.id,
        }

        # 解析失败策略
        if subtask.on_fail_strategy:
            return await self._parse_fail_strategy(
                strategy=subtask.on_fail_strategy,
                step_name=subtask.tool,
                state=state,
            )

        # 默认：继续下一步
        return FailAction(type="fallback")

    async def _parse_fail_strategy(
        self,
        strategy: str,
        step_name: Optional[str],
        state: Dict[str, Any],
    ) -> FailAction:
        """
        解析失败策略（自然语言 -> 结构化动作）

        支持：
        - "重试最多3次" -> retry
        - "回退到步骤2" -> goto
        - "使用默认值继续" -> fallback
        - "停止执行" -> abort
        """
        strategy_lower = strategy.lower()

        # 简单规则匹配
        if "重试" in strategy_lower or "retry" in strategy_lower:
            return FailAction(type="retry", max_retries=3)

        if "回退" in strategy_lower or "返回" in strategy_lower or "goto" in strategy_lower:
            # 尝试提取步骤号
            import re

            match = re.search(r"步骤\s*(\d+)", strategy)
            if match:
                return FailAction(type="goto", target_step=match.group(1))
            return FailAction(type="retry")  # 找不到步骤号，改为重试

        if "停止" in strategy_lower or "终止" in strategy_lower or "abort" in strategy_lower:
            return FailAction(type="abort")

        # 默认：使用 fallback
        return FailAction(type="fallback")

    def _update_state_from_result(
        self,
        tool_name: Optional[str],
        result: Dict[str, Any],
        state: Dict[str, Any],
    ):
        """
        根据工具执行结果更新状态字典

        来自 custom_agent_executor_v2.py 的状态更新逻辑
        """
        if not result or not result.get("success"):
            return

        if not tool_name:
            return

        # 根据工具类型更新对应字段
        if tool_name == "analyze_input":
            state["case_summary"] = result.get("case_summary", "")
            state["case_type"] = result.get("case_type", [])
            state["key_info"] = result.get("key_info", {})
            state["analysis_result"] = result.get("analysis_result", {})

        elif tool_name == "generate_outline":
            state["outline"] = result.get("outline", {})

        elif tool_name in [
            "multi_query_search",
            "es_fulltext_search",
            "search_documents_by_classification",
        ]:
            state["document_ids"] = result.get("document_ids", [])
            if result.get("documents"):
                state["documents"] = result.get("documents", [])

        elif tool_name in ["get_document_contents", "skim_documents", "read_documents"]:
            state["documents"] = result.get("documents", [])

        elif tool_name == "document_extraction":
            state["extracted_content"] = result.get("extracted_content", {})

        elif tool_name == "document_compose":
            state["composed_document"] = result.get("document", {})

        elif tool_name == "document_review":
            state["reviewed_document"] = result.get("reviewed_document", {})

        elif tool_name == "analyze_documents":
            state["analysis_result"] = result.get("analysis", {})
