"""
执行引擎核心模块

核心功能：
- 执行计划中的每个步骤
- 期望验证
- 失败策略解析
- 状态更新
- 内置 ExecutionContext 管理执行上下文
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

from auto_agent.core.context import ExecutionContext
from auto_agent.core.executor.consistency import ConsistencyManager

# 导入子模块
from auto_agent.core.executor.param_builder import ParameterBuilder
from auto_agent.core.executor.post_policy import PostPolicyManager
from auto_agent.core.executor.replan import ExecutionPattern, PatternType, ReplanManager
from auto_agent.core.executor.state import (
    compress_state_for_llm,
    get_nested_value,
    update_state_from_result,
)
from auto_agent.llm.client import LLMClient
from auto_agent.models import (
    BindingPlan,
    ExecutionPlan,
    FailAction,
    PlanStep,
    SubTaskResult,
    ValidationMode,
)
from auto_agent.retry.controller import RetryController
from auto_agent.retry.models import ErrorRecoveryRecord, ErrorType, RetryConfig
from auto_agent.tools.registry import ToolRegistry

# 重新导出供外部使用
__all__ = ["ExecutionEngine", "ExecutionPattern", "PatternType"]


class ExecutionEngine:
    """
    执行引擎

    功能：
    - 执行计划中的每个步骤（带重试）
    - 期望评估
    - 失败策略解析
    - 状态更新
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        retry_config: RetryConfig,
        llm_client: Optional[LLMClient] = None,
        memory_storage_path: Optional[str] = None,
    ):
        self.tool_registry = tool_registry
        self.retry_controller = RetryController(retry_config, llm_client)
        self.llm_client = llm_client
        self._memory_storage_path = memory_storage_path
        self.context: Optional[ExecutionContext] = None
        self._memory_systems: Dict[str, Any] = {}

        # 子模块（在 execute_plan_stream 中初始化）
        self._param_builder: Optional[ParameterBuilder] = None
        self._replan_manager: Optional[ReplanManager] = None
        self._consistency_manager: Optional[ConsistencyManager] = None
        self._post_policy_manager: Optional[PostPolicyManager] = None

    def _get_memory_system(self, user_id: str):
        """获取用户的 MemorySystem"""
        if user_id in self._memory_systems:
            return self._memory_systems[user_id]

        from pathlib import Path

        from auto_agent.memory.system import MemorySystem

        if self._memory_storage_path:
            storage_path = Path(self._memory_storage_path) / user_id
        else:
            storage_path = Path("./auto_agent_memory") / user_id

        storage_path.mkdir(parents=True, exist_ok=True)

        memory_system = MemorySystem(
            storage_path=str(storage_path),
            auto_save=True,
            llm_client=self.llm_client,
        )

        self._memory_systems[user_id] = memory_system
        return memory_system

    # ==================== 兼容性方法（委托给子模块）====================

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """从嵌套字典中获取值（兼容旧代码）"""
        return get_nested_value(data, path)

    def _compress_state_for_llm(
        self, state: Dict[str, Any], max_chars: int = 4000
    ) -> str:
        """压缩状态信息（兼容旧代码）"""
        return compress_state_for_llm(state, max_chars)

    def _update_state_from_result(
        self,
        tool_name: Optional[str],
        result: Dict[str, Any],
        state: Dict[str, Any],
        step_id: Optional[str] = None,
    ):
        """更新状态（兼容旧代码）"""
        update_state_from_result(tool_name, result, state, step_id, self.tool_registry)

    def _detect_execution_patterns(
        self,
        execution_history: List[SubTaskResult],
    ) -> List[ExecutionPattern]:
        """检测执行模式（兼容旧代码）"""
        if self._replan_manager:
            return self._replan_manager.detect_execution_patterns(execution_history)
        return []

    def _validate_parameters(
        self,
        arguments: Dict[str, Any],
        tool: Any,
    ) -> Tuple[bool, List[str]]:
        """验证参数（兼容旧代码）"""
        if self._param_builder:
            return self._param_builder.validate_parameters(arguments, tool)
        return True, []

    # ==================== 主执行方法 ====================

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

            if result.success:
                self._update_state_from_result(
                    subtask.tool, result.output, state, step_id=subtask.id
                )

            if on_step_complete:
                await on_step_complete(subtask, result)

            if not result.success:
                action = await self._handle_failure(subtask, result, state, plan)

                if action.type == "retry":
                    continue
                elif action.type == "goto":
                    for i, s in enumerate(plan.subtasks):
                        if s.id == action.target_step:
                            current_step_index = i
                            break
                    continue
                elif action.type == "abort":
                    break

            current_step_index += 1

        state["control"]["iterations"] = iterations
        return results, state

    async def execute_plan_stream(
        self,
        plan: ExecutionPlan,
        state: Dict[str, Any],
        conversation_id: str,
        tool_executor: Optional[Callable] = None,
        agent_info: Optional[Dict[str, Any]] = None,
        enable_tracing: bool = True,
        binding_plan: Optional[BindingPlan] = None,
        binding_planner: Optional[Any] = None,
    ):
        """
        流式执行计划（AsyncGenerator）

        Args:
            plan: 执行计划
            state: 初始状态字典
            conversation_id: 对话ID
            tool_executor: 自定义工具执行器
            agent_info: Agent 信息
            enable_tracing: 是否启用追踪
            binding_plan: 参数绑定计划
            binding_planner: 参数绑定规划器（可选，用于 replan 后自动刷新 binding_plan）

        Yields:
            Dict: 事件字典
        """
        from auto_agent.tracing import Tracer, start_span, trace_flow_event

        # 初始化子模块
        self._binding_plan = binding_plan
        self._step_outputs: Dict[str, Any] = {}

        query = state.get("inputs", {}).get("query", "")
        user_id = agent_info.get("user_id", "default") if agent_info else "default"

        # 开始追踪
        tracer_ctx = None
        if enable_tracing:
            tracer_ctx = Tracer.start(query=query, user_id=user_id)
            tracer_ctx.__enter__()

        plan_summary = "\n".join(
            f"{i + 1}. {s.description}" for i, s in enumerate(plan.subtasks)
        )

        # 获取 MemorySystem
        memory_system = self._get_memory_system(user_id)

        self.context = ExecutionContext(
            query=query,
            user_id=user_id,
            plan_summary=plan_summary,
            state=state,
            agent_name=agent_info.get("name", "") if agent_info else "",
            agent_description=agent_info.get("description", "") if agent_info else "",
            agent_goals=agent_info.get("goals", []) if agent_info else [],
            agent_constraints=agent_info.get("constraints", []) if agent_info else [],
            memory_system=memory_system,
        )
        self.context.total_steps = len(plan.subtasks)

        # 初始化子模块
        self._param_builder = ParameterBuilder(
            llm_client=self.llm_client,
            binding_plan=binding_plan,
            step_outputs=self._step_outputs,
            context=self.context,
            tool_registry=self.tool_registry,
        )
        self._replan_manager = ReplanManager(
            llm_client=self.llm_client,
            tool_registry=self.tool_registry,
            context=self.context,
        )
        self._consistency_manager = ConsistencyManager(
            llm_client=self.llm_client,
            context=self.context,
        )
        self._post_policy_manager = PostPolicyManager(
            llm_client=self.llm_client,
            tool_registry=self.tool_registry,
            context=self.context,
        )

        results = []
        current_step_index = 0
        max_iterations = state.get("control", {}).get("max_iterations", 20)
        iterations = 0
        execution_strategy = plan.execution_strategy

        while current_step_index < len(plan.subtasks) and iterations < max_iterations:
            iterations += 1
            step_num = current_step_index + 1
            subtask = plan.subtasks[current_step_index]
            self.context.current_step = step_num

            # 发送步骤开始事件
            yield {
                "event": "stage_start",
                "data": {
                    "stage": f"step_{step_num}",
                    "step": step_num,
                    "step_id": subtask.id,
                    "name": subtask.tool,
                    "description": subtask.description,
                    "status": "running",
                },
            }

            try:
                step_span = None
                if enable_tracing:
                    step_span = start_span(
                        f"step_{step_num}",
                        span_type="step",
                        tool=subtask.tool,
                        description=subtask.description,
                    )
                    step_span.__enter__()

                # 一致性检查
                consistency_violations = []
                if execution_strategy and self.llm_client and self.context:
                    tool_for_check = (
                        self.tool_registry.get_tool(subtask.tool)
                        if subtask.tool
                        else None
                    )
                    should_check_consistency = False
                    if (
                        tool_for_check
                        and hasattr(tool_for_check, "definition")
                        and tool_for_check.definition.replan_policy
                    ):
                        policy = tool_for_check.definition.replan_policy
                        if policy.requires_consistency_check or policy.high_impact:
                            should_check_consistency = True
                    if execution_strategy.require_phase_review:
                        should_check_consistency = True

                    if (
                        should_check_consistency
                        and self.context.consistency_checker.checkpoints
                    ):
                        pre_check_args = (
                            await self._build_tool_arguments(
                                subtask, state, tool_for_check
                            )
                            if tool_for_check
                            else {}
                        )
                        consistency_violations = (
                            await self._consistency_manager.check_consistency(
                                step=subtask,
                                arguments=pre_check_args,
                                state=state,
                            )
                        )

                        if consistency_violations:
                            critical_violations = [
                                v
                                for v in consistency_violations
                                if v.severity == "critical"
                            ]
                            if critical_violations:
                                yield {
                                    "event": "consistency_violation",
                                    "data": {
                                        "step": step_num,
                                        "step_id": subtask.id,
                                        "violations": [
                                            v.to_dict() for v in critical_violations
                                        ],
                                        "severity": "critical",
                                        "message": f"检测到 {len(critical_violations)} 个严重一致性违规",
                                    },
                                }
                                if enable_tracing:
                                    trace_flow_event(
                                        action="consistency_violation",
                                        reason=f"严重一致性违规: {critical_violations[0].description}",
                                        from_step=subtask.id,
                                    )

                # 执行步骤
                args = {}
                build_args_info = {}  # 用于记录参数构造的详细信息
                if tool_executor:
                    tool = (
                        self.tool_registry.get_tool(subtask.tool)
                        if subtask.tool
                        else None
                    )
                    # 检测循环执行
                    is_loop = subtask.id in self._step_outputs
                    build_args_info["is_loop_execution"] = is_loop
                    if is_loop:
                        build_args_info["loop_reason"] = "步骤已执行过，将触发 LLM 基于完整上下文重新构造参数"

                    args = (
                        await self._build_tool_arguments(subtask, state, tool)
                        if tool
                        else {}
                    )
                    build_args_info["final_args"] = {
                        k: (str(v)[:200] + "..." if isinstance(v, str) and len(v) > 200 else v)
                        for k, v in args.items()
                    }

                    # 发送参数构造详情事件
                    yield {
                        "event": "param_build",
                        "data": {
                            "step": step_num,
                            "step_id": subtask.id,
                            "tool": subtask.tool,
                            "is_loop_execution": is_loop,
                            "args_preview": build_args_info,
                        },
                    }

                    output = await tool_executor(subtask.tool, args)
                    result = SubTaskResult(
                        step_id=subtask.id,
                        success=output.get("success", True),
                        output=output,
                        error=output.get("error"),
                    )
                else:
                    # 检测循环执行
                    is_loop = subtask.id in self._step_outputs
                    build_args_info["is_loop_execution"] = is_loop
                    if is_loop:
                        build_args_info["loop_reason"] = "步骤已执行过，将触发 LLM 基于完整上下文重新构造参数"

                    # 先获取参数信息用于 tracing（在 _execute_subtask 之前）
                    tool_for_args = (
                        self.tool_registry.get_tool(subtask.tool)
                        if subtask.tool
                        else None
                    )
                    if tool_for_args:
                        preview_args = await self._build_tool_arguments(
                            subtask, state, tool_for_args
                        )
                        build_args_info["final_args"] = {
                            k: (str(v)[:200] + "..." if isinstance(v, str) and len(v) > 200 else v)
                            for k, v in preview_args.items()
                        }

                    # 发送参数构造详情事件
                    yield {
                        "event": "param_build",
                        "data": {
                            "step": step_num,
                            "step_id": subtask.id,
                            "tool": subtask.tool,
                            "is_loop_execution": is_loop,
                            "args_preview": build_args_info,
                        },
                    }

                    result = await self._execute_subtask(
                        subtask, state, conversation_id
                    )

                results.append(result)

                if step_span:
                    step_span.__exit__(None, None, None)

                # 更新状态
                if result.success:
                    self._update_state_from_result(
                        subtask.tool, result.output, state, step_id=subtask.id
                    )
                # 期望验证失败但工具本身执行成功（output.success=True）时，也应写入状态，
                # 这样后续步骤（反思/修正）才能基于失败报告进行针对性优化。
                elif (
                    result.expectation_failed
                    and isinstance(result.output, dict)
                    and result.output.get("success") is True
                ):
                    self._update_state_from_result(
                        subtask.tool, result.output, state, step_id=subtask.id
                    )

                # 记录到 ExecutionContext
                self.context.record_step(
                    step_id=subtask.id,
                    step_num=step_num,
                    tool_name=subtask.tool or "",
                    description=subtask.description,
                    arguments=args if tool_executor else {},
                    output=result.output or {},
                    success=result.success,
                    error=result.error,
                )

                # 应用后处理策略
                if result.success:
                    post_result = await self._post_policy_manager.apply_post_policy(
                        step=subtask,
                        result=result,
                        state=state,
                        execution_strategy=execution_strategy,
                    )

                    if post_result["should_extract_memory"] and self.llm_client:
                        await self._post_policy_manager.extract_working_memory(
                            step=subtask,
                            result=result,
                            state=state,
                        )

                    if post_result["should_register_checkpoint"] and self.llm_client:
                        await self._consistency_manager.register_consistency_checkpoint(
                            step=subtask,
                            result=result,
                            state=state,
                        )

                # 保存步骤输出
                if result.success and result.output:
                    self._step_outputs[subtask.id] = result.output
                    if self._param_builder:
                        self._param_builder.update_step_output(
                            subtask.id, result.output
                        )

                # 发送步骤完成事件
                yield {
                    "event": "stage_complete",
                    "data": {
                        "stage": f"step_{step_num}",
                        "step": step_num,
                        "step_id": subtask.id,
                        "name": subtask.tool,
                        "description": subtask.description,
                        "success": result.success,
                        "result": result.output,
                        "status": "completed" if result.success else "failed",
                    },
                }

                # 处理失败
                if not result.success:
                    action = await self._handle_failure(subtask, result, state, plan)

                    if action.type == "retry":
                        if enable_tracing:
                            trace_flow_event(
                                action="retry",
                                reason=result.error or "执行失败",
                                from_step=subtask.id,
                            )
                        yield {
                            "event": "stage_retry",
                            "data": {
                                "step": step_num,
                                "name": subtask.tool,
                                "message": f"重试步骤 {step_num}",
                            },
                        }
                        continue
                    elif action.type == "goto":
                        for i, s in enumerate(plan.subtasks):
                            if s.id == action.target_step:
                                current_step_index = i
                                break
                        if enable_tracing:
                            trace_flow_event(
                                action="jump",
                                reason=action.reason or "失败策略跳转",
                                from_step=subtask.id,
                                to_step=action.target_step,
                            )
                        yield {
                            "event": "stage_jump",
                            "data": {
                                "from_step": step_num,
                                "to_step": current_step_index + 1,
                                "message": f"跳转到步骤 {current_step_index + 1}",
                            },
                        }
                        continue
                    elif action.type == "abort":
                        if enable_tracing:
                            trace_flow_event(
                                action="abort",
                                reason=action.reason or "执行中止",
                                from_step=subtask.id,
                            )
                        yield {
                            "event": "stage_abort",
                            "data": {
                                "step": step_num,
                                "message": "执行中止",
                            },
                        }
                        break

            except Exception as e:
                result = SubTaskResult(
                    step_id=subtask.id,
                    success=False,
                    error=str(e),
                )
                yield {
                    "event": "stage_error",
                    "data": {
                        "step": step_num,
                        "name": subtask.tool,
                        "error": str(e),
                    },
                }
                results.append(
                    result
                )

            # 检查是否需要重规划
            (
                should_check,
                check_reason,
            ) = await self._replan_manager.should_trigger_replan(
                step=subtask,
                result=result,
                execution_strategy=execution_strategy,
                current_step_index=current_step_index,
                results=results,
            )

            if should_check:
                new_plan = await self._replan_manager.evaluate_and_replan(
                    current_plan=plan,
                    execution_history=results,
                    state=state,
                    current_step_index=current_step_index,
                    use_incremental=True,
                )

                if new_plan is not None:
                    new_plan.task_profile = plan.task_profile
                    new_plan.execution_strategy = plan.execution_strategy

                    yield {
                        "event": "stage_replan",
                        "data": {
                            "step": step_num,
                            "trigger_reason": check_reason,
                            "reason": new_plan.warnings[0]
                            if new_plan.warnings
                            else "检测到执行问题，触发重规划",
                            "new_plan_intent": new_plan.intent,
                            "new_steps_count": len(new_plan.subtasks),
                            "message": f"执行计划已重新规划，新计划包含 {len(new_plan.subtasks)} 个步骤",
                        },
                    }

                    plan = new_plan
                    # replan 后旧 binding_plan 可能与新计划不匹配：默认丢弃；如果提供 binding_planner 则立即重建
                    self._binding_plan = None
                    if self._param_builder:
                        self._param_builder.binding_plan = None

                    if binding_planner is not None:
                        try:
                            rebuilt = await binding_planner.create_binding_plan(
                                execution_plan=plan,
                                user_input=state.get("inputs", {}).get("query", "")
                                or "",
                                initial_state=state,
                            )
                            # 仅当真正有 bindings 时才启用（空计划等场景会返回 steps=[]）
                            if rebuilt and rebuilt.steps:
                                self._binding_plan = rebuilt
                                if self._param_builder:
                                    self._param_builder.binding_plan = rebuilt

                                yield {
                                    "event": "binding_plan",
                                    "data": {
                                        "success": True,
                                        "phase": "replan",
                                        "message": f"重规划后已刷新参数绑定，共 {len(rebuilt.steps)} 个步骤",
                                        "bindings_count": sum(
                                            len(s.bindings) for s in rebuilt.steps
                                        ),
                                        "reasoning": rebuilt.reasoning,
                                        "confidence_threshold": rebuilt.confidence_threshold,
                                    },
                                }
                        except Exception as e:
                            yield {
                                "event": "binding_plan",
                                "data": {
                                    "success": False,
                                    "phase": "replan",
                                    "message": f"重规划后参数绑定刷新失败，将 fallback 到运行时推理: {str(e)}",
                                    "bindings_count": 0,
                                    "error": str(e),
                                    "fallback": "llm_infer",
                                },
                            }

                    current_step_index = 0
                    continue

            current_step_index += 1

        state["control"]["iterations"] = iterations

        if self.context:
            self.context.end_task(promote_to_long_term=False)

        # 结束追踪
        trace_data = None
        trace_data_full = None
        if enable_tracing and tracer_ctx:
            tracer_ctx.__exit__(None, None, None)
            if tracer_ctx.trace:
                trace_data = tracer_ctx.trace.to_dict(truncate=True)
                trace_data_full = tracer_ctx.trace.to_dict(truncate=False)

        yield {
            "event": "execution_complete",
            "data": {
                "results": [
                    {"step_id": r.step_id, "success": r.success, "error": r.error}
                    for r in results
                ],
                "iterations": iterations,
                "state": state,
                "context": self.context,
                "trace": trace_data,
                "trace_full": trace_data_full,
            },
        }

    # ==================== 子任务执行 ====================

    async def _execute_subtask(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        conversation_id: str,
        use_smart_retry: bool = True,
    ) -> SubTaskResult:
        """执行单个子任务（带重试和验证）"""
        if use_smart_retry:
            return await self._execute_subtask_with_smart_retry(
                subtask, state, conversation_id
            )

        # 传统简单重试逻辑
        if not subtask.tool:
            return SubTaskResult(
                step_id=subtask.id,
                success=True,
                output=subtask.parameters,
            )

        tool = self.tool_registry.get_tool(subtask.tool)
        if not tool:
            return SubTaskResult(
                step_id=subtask.id,
                success=False,
                error=f"工具未找到: {subtask.tool}",
            )

        arguments = await self._build_tool_arguments(subtask, state, tool)

        try:
            output = await self.retry_controller.execute_with_retry(
                tool.execute,
                **arguments,
            )

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

    async def _execute_subtask_with_smart_retry(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        conversation_id: str,
    ) -> SubTaskResult:
        """带智能重试的子任务执行"""
        if not subtask.tool:
            return SubTaskResult(
                step_id=subtask.id,
                success=True,
                output=subtask.parameters,
            )

        tool = self.tool_registry.get_tool(subtask.tool)
        if not tool:
            return SubTaskResult(
                step_id=subtask.id,
                success=False,
                error=f"工具未找到: {subtask.tool}",
            )

        arguments = await self._build_tool_arguments(subtask, state, tool)
        original_arguments = dict(arguments)

        last_exception: Optional[Exception] = None
        max_retries = self.retry_controller.config.max_retries

        for attempt in range(max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(tool.execute):
                    output = await tool.execute(**arguments)
                else:
                    output = tool.execute(**arguments)

                if attempt > 0 and last_exception is not None:
                    await self._record_successful_recovery(
                        exception=last_exception,
                        tool_name=subtask.tool,
                        original_params=original_arguments,
                        fixed_params=arguments,
                    )

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
                last_exception = e

                if attempt >= max_retries:
                    alt_result = await self._try_alternative_tool(
                        original_tool_name=subtask.tool,
                        subtask=subtask,
                        state=state,
                        original_error=str(e),
                    )
                    if alt_result is not None:
                        return alt_result

                    return SubTaskResult(
                        step_id=subtask.id,
                        success=False,
                        error=str(e),
                    )

                error_analysis = await self.retry_controller.analyze_error(
                    exception=e,
                    context={"state": state, "arguments": arguments},
                    tool_definition=tool.definition
                    if hasattr(tool, "definition")
                    else None,
                )

                if not error_analysis.is_recoverable:
                    alt_result = await self._try_alternative_tool(
                        original_tool_name=subtask.tool,
                        subtask=subtask,
                        state=state,
                        original_error=str(e),
                    )
                    if alt_result is not None:
                        return alt_result

                    return SubTaskResult(
                        step_id=subtask.id,
                        success=False,
                        error=f"{str(e)} (不可恢复: {error_analysis.root_cause})",
                    )

                if error_analysis.error_type == ErrorType.PARAMETER_ERROR:
                    fixed_arguments = (
                        await self.retry_controller.suggest_parameter_fixes(
                            failed_params=arguments,
                            error_analysis=error_analysis,
                            context={"state": state},
                            tool_definition=tool.definition
                            if hasattr(tool, "definition")
                            else None,
                        )
                    )
                    if fixed_arguments != arguments:
                        arguments = fixed_arguments

                delay = self.retry_controller.get_delay(attempt)
                await asyncio.sleep(delay)

        alt_result = await self._try_alternative_tool(
            original_tool_name=subtask.tool,
            subtask=subtask,
            state=state,
            original_error=str(last_exception) if last_exception else "未知错误",
        )
        if alt_result is not None:
            return alt_result

        return SubTaskResult(
            step_id=subtask.id,
            success=False,
            error=str(last_exception) if last_exception else "未知错误",
        )

    async def _try_alternative_tool(
        self,
        original_tool_name: str,
        subtask: PlanStep,
        state: Dict[str, Any],
        original_error: str,
    ) -> Optional[SubTaskResult]:
        """当工具失败且有 alternative_tools 时尝试替代工具"""
        original_tool = self.tool_registry.get_tool(original_tool_name)
        if not original_tool or not hasattr(original_tool, "definition"):
            return None

        tool_def = original_tool.definition
        alternative_tools = (
            tool_def.alternative_tools if tool_def.alternative_tools else []
        )

        if not alternative_tools:
            return None

        for alt_tool_name in alternative_tools:
            alt_tool = self.tool_registry.get_tool(alt_tool_name)
            if not alt_tool:
                continue

            try:
                alt_subtask = PlanStep(
                    id=subtask.id,
                    description=subtask.description,
                    tool=alt_tool_name,
                    parameters=subtask.parameters,
                    dependencies=subtask.dependencies,
                    expectations=subtask.expectations,
                    on_fail_strategy=subtask.on_fail_strategy,
                    read_fields=subtask.read_fields,
                    write_fields=subtask.write_fields,
                    is_pinned=subtask.is_pinned,
                    pinned_parameters=subtask.pinned_parameters,
                    parameter_template=subtask.parameter_template,
                    template_variables=subtask.template_variables,
                )

                arguments = await self._build_tool_arguments(
                    alt_subtask, state, alt_tool
                )

                if asyncio.iscoroutinefunction(alt_tool.execute):
                    output = await alt_tool.execute(**arguments)
                else:
                    output = alt_tool.execute(**arguments)

                if output.get("success", True):
                    return SubTaskResult(
                        step_id=subtask.id,
                        success=True,
                        output=output,
                        metadata={
                            "original_tool": original_tool_name,
                            "alternative_tool": alt_tool_name,
                            "original_error": original_error,
                            "fallback_reason": f"原工具 {original_tool_name} 失败，使用替代工具 {alt_tool_name}",
                        },
                    )

            except Exception:
                continue

        return None

    # ==================== 参数构造 ====================

    async def _build_tool_arguments(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        tool: Any,
    ) -> Dict[str, Any]:
        """
        构造工具参数

        核心思路：
        - 首次执行：优先使用 BindingPlan 静态绑定，fallback 到 LLM 推理
        - 循环执行（步骤被重复执行）：跳过静态绑定，直接触发 LLM 干预，
          让大模型基于完整上下文（之前的失败原因、验证报告等）来智能构造参数
        """
        from auto_agent.tracing import start_span, trace_flow_event

        arguments = {}

        # 1. 处理 pinned_parameters
        if subtask.pinned_parameters:
            arguments.update(subtask.pinned_parameters)

        # 2. 合并静态参数
        if subtask.parameters:
            arguments.update(subtask.parameters)

        # 检测是否是循环执行（步骤已经执行过）
        # 循环执行意味着之前的方案失败了，需要 LLM 介入来做调整
        is_loop_execution = subtask.id in self._step_outputs

        # 3. 尝试使用 BindingPlan 解析参数
        # 注意：循环执行时跳过静态绑定，强制走 LLM fallback
        binding_used = False
        fallback_params = []
        binding_resolved = {}
        binding_details = []

        if (
            self._param_builder
            and hasattr(self, "_binding_plan")
            and self._binding_plan
            and not is_loop_execution  # 循环执行时跳过静态绑定
        ):
            step_bindings = self._binding_plan.get_step_bindings(subtask.id)
            if step_bindings:
                with start_span(
                    "param_binding_resolve",
                    span_type="param_binding",
                    tool=subtask.tool,
                    step_id=subtask.id,
                    bindings_count=len(step_bindings.bindings),
                    confidence_threshold=self._binding_plan.confidence_threshold,
                ):
                    (
                        resolved,
                        needs_fallback,
                        details,
                    ) = await self._param_builder.resolve_bindings_with_trace(
                        step_bindings=step_bindings,
                        state=state,
                        existing_args=arguments,
                    )
                    binding_resolved = resolved
                    arguments.update(resolved)
                    fallback_params = needs_fallback
                    binding_details = details
                    binding_used = True

                    trace_flow_event(
                        action="binding_resolve",
                        reason=f"绑定解析完成: {len(resolved)} 成功, {len(needs_fallback)} 需要 fallback",
                        from_step=subtask.id,
                        resolved_params=list(resolved.keys()),
                        fallback_params=needs_fallback,
                        binding_details=details,
                    )

        # 4. 从 state 中读取 read_fields（兼容旧逻辑）
        if not binding_used and subtask.read_fields:
            for field in subtask.read_fields:
                if field in state:
                    arguments[field] = state[field]
                elif "." in field:
                    value = get_nested_value(state, field)
                    if value is not None:
                        param_name = field.split(".")[-1]
                        arguments[param_name] = value

        # 4.5 在不调用 LLM 的情况下尽量补齐参数（默认值/别名映射）
        # - 目的：减少不必要的 LLM fallback，尤其是 required 参数存在默认值或可从 state 映射时
        if tool and hasattr(tool, "definition"):
            try:
                import copy

                tool_def = tool.definition

                # (a) param_aliases: {param_name: state_field_path}
                # 允许 path 为 "inputs.query"/"steps.1.output.xxx"/"documents" 等
                if getattr(tool_def, "param_aliases", None):
                    for param_name, state_path in tool_def.param_aliases.items():
                        if (
                            param_name in arguments
                            and arguments[param_name] is not None
                        ):
                            continue
                        if not state_path:
                            continue

                        value = None
                        if isinstance(state_path, str):
                            # 兼容写法：允许 "state.xxx"
                            if state_path.startswith("state."):
                                value = get_nested_value(state, state_path[6:])
                            else:
                                value = (
                                    get_nested_value(state, state_path)
                                    if "." in state_path
                                    else state.get(state_path)
                                )

                        if value is not None:
                            arguments[param_name] = value

                # (b) 工具 schema 默认值：优先用于 required 参数缺失的场景
                for p in tool_def.parameters:
                    if p.name in arguments and arguments[p.name] is not None:
                        continue
                    if p.required and p.default is not None:
                        # 避免可变对象共享（list/dict）
                        arguments[p.name] = copy.deepcopy(p.default)
            except Exception:
                # 默认值/别名补齐失败不影响主流程
                pass

        # 5. 对于需要 fallback 的参数，使用 LLM 推理
        if self.llm_client and tool and self._param_builder:
            tool_def = tool.definition
            missing_required = []
            for p in tool_def.parameters:
                if p.required and (
                    p.name not in arguments or arguments[p.name] is None
                ):
                    missing_required.append(p.name)

            # 触发 LLM fallback 的条件：
            # 1. 存在必需参数缺失
            # 2. 绑定解析需要 fallback
            # 3. 循环执行（之前的方案失败了，需要 LLM 基于完整上下文重新构造参数）
            should_use_llm = missing_required or fallback_params or is_loop_execution

            if should_use_llm:
                fallback_reason = []
                if is_loop_execution:
                    fallback_reason.append("loop_execution:需要LLM基于完整上下文重新构造参数")
                if not binding_used:
                    fallback_reason.append("no_binding_plan")
                if missing_required:
                    fallback_reason.append(f"missing_required:{missing_required}")
                if fallback_params:
                    fallback_reason.append(f"low_confidence:{fallback_params}")

                with start_span(
                    "param_build_llm_fallback",
                    span_type="param_build",
                    tool=subtask.tool,
                    existing_args=list(arguments.keys()),
                    fallback_params=fallback_params,
                    missing_required=missing_required,
                    fallback_reason=fallback_reason,
                    binding_used=binding_used,
                ):
                    trace_flow_event(
                        action="fallback",
                        reason=f"参数构造 fallback 到 LLM: {', '.join(fallback_reason)}",
                        from_step=subtask.id,
                        fallback_reason=fallback_reason,
                        existing_args=list(arguments.keys()),
                        target_params=missing_required + fallback_params,
                    )

                    args_before_fallback = dict(arguments)

                    arguments = await self._param_builder.build_arguments_with_llm(
                        subtask, state, tool, arguments
                    )

                    new_params = [
                        k for k in arguments.keys() if k not in args_before_fallback
                    ]
                    trace_flow_event(
                        action="fallback",
                        reason=f"LLM fallback 完成: 新增 {len(new_params)} 个参数",
                        from_step=subtask.id,
                        new_params=new_params,
                        final_args=list(arguments.keys()),
                    )

        # 6. 验证参数
        if tool and self._param_builder:
            with start_span(
                "param_validate",
                span_type="validation",
                tool=subtask.tool,
                args_to_validate=list(arguments.keys()),
            ):
                arguments = await self._param_builder.validate_and_fix_parameters(
                    arguments, tool, state, subtask
                )

        return arguments

    # ==================== 辅助方法 ====================

    async def _record_successful_recovery(
        self,
        exception: Exception,
        tool_name: str,
        original_params: Dict[str, Any],
        fixed_params: Dict[str, Any],
    ) -> None:
        """记录成功的错误恢复策略到记忆系统"""
        import time

        if not self.context or not self.context.memory_system:
            return

        try:
            recovery_record = ErrorRecoveryRecord(
                error_type=type(exception).__name__,
                error_message=str(exception),
                tool_name=tool_name,
                original_params=original_params,
                fixed_params=fixed_params,
                recovery_successful=True,
                timestamp=time.time(),
            )

            memory_content = recovery_record.to_memory_content()

            memory_system = self.context.memory_system
            if hasattr(memory_system, "add_experience"):
                await memory_system.add_experience(
                    category="error_recovery",
                    content=memory_content,
                )
            elif hasattr(memory_system, "l2_semantic") and hasattr(
                memory_system.l2_semantic, "add"
            ):
                memory_system.l2_semantic.add(
                    content=str(memory_content),
                    metadata={"category": "error_recovery", "tool_name": tool_name},
                )
        except Exception:
            pass

    async def _evaluate_expectations(
        self,
        tool: Any,
        result: Dict[str, Any],
        expectations: str,
        state: Dict[str, Any],
        mode: ValidationMode = ValidationMode.LOOSE,
    ) -> Tuple[bool, str]:
        """评估执行结果是否满足期望"""
        validate_fn = (
            tool.definition.validate_function if hasattr(tool, "definition") else None
        )

        if validate_fn is None:
            success = result.get("success", False)
            if success:
                return True, "无需验证，执行成功即通过"
            else:
                return False, f"执行失败: {result.get('error', '未知错误')}"

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
        """处理失败，解析失败策略"""
        if "control" not in state:
            state["control"] = {}
        if "failed_steps" not in state["control"]:
            state["control"]["failed_steps"] = []

        state["control"]["failed_steps"].append(
            {
                "step": subtask.id,
                "name": subtask.tool,
                "error": result.error,
            }
        )

        if "last_failure" not in state:
            state["last_failure"] = {}
        state["last_failure"][subtask.tool or "unknown"] = {
            "reason": result.evaluation_reason or result.error,
            "expectations": subtask.expectations,
            "step": subtask.id,
        }

        if subtask.on_fail_strategy:
            return await self._parse_fail_strategy(
                strategy=subtask.on_fail_strategy,
                step_name=subtask.tool,
                state=state,
            )

        return FailAction(type="fallback")

    async def _parse_fail_strategy(
        self,
        strategy: str,
        step_name: Optional[str],
        state: Dict[str, Any],
    ) -> FailAction:
        """解析失败策略"""
        import re

        strategy_lower = strategy.lower()

        if "重试" in strategy_lower or "retry" in strategy_lower:
            return FailAction(type="retry", max_retries=3)

        if (
            "回退" in strategy_lower
            or "返回" in strategy_lower
            or "goto" in strategy_lower
        ):
            match = re.search(r"步骤\s*(\d+)", strategy)
            if match:
                return FailAction(type="goto", target_step=match.group(1))
            return FailAction(type="retry")

        if (
            "停止" in strategy_lower
            or "终止" in strategy_lower
            or "abort" in strategy_lower
        ):
            return FailAction(type="abort")

        return FailAction(type="fallback")

    async def generate_tool_prompt(
        self,
        subtask: PlanStep,
        tool: Any,
        prompt_template: Optional[str] = None,
    ) -> Optional[str]:
        """让 LLM 根据执行上下文动态生成工具调用的 prompt"""
        import json

        if not self.llm_client or not self.context:
            return None

        tool_def = tool.definition
        tool_info = {
            "name": tool_def.name,
            "description": tool_def.description,
            "parameters": [
                {"name": p.name, "type": p.type, "description": p.description}
                for p in tool_def.parameters
            ],
        }

        meta_prompt = f"""你是一个智能 prompt 生成助手。根据当前执行上下文，为工具调用生成最合适的 prompt。

【执行上下文】
{self.context.to_llm_context()}

【当前步骤】
步骤 {self.context.current_step}: {subtask.description}

【工具信息】
{json.dumps(tool_info, ensure_ascii=False, indent=2)}

【任务】
根据上下文，生成一个清晰、具体的 prompt，用于指导这个工具的执行。

{"【参考模板】" + chr(10) + prompt_template if prompt_template else ""}

请直接返回生成的 prompt 文本，不要包含任何解释或标记。"""

        try:
            generated_prompt = await self.llm_client.chat(
                [{"role": "user", "content": meta_prompt}],
                temperature=0.3,
                trace_purpose="prompt_gen",
            )
            return generated_prompt.strip()
        except Exception:
            return None

    def get_context(self) -> Optional[ExecutionContext]:
        """获取当前执行上下文"""
        return self.context

    def get_context_summary(self) -> str:
        """获取执行上下文摘要"""
        if not self.context:
            return ""
        return self.context.to_llm_context()

    # ==================== 兼容性方法（委托给子模块）====================

    async def evaluate_and_replan(
        self,
        current_plan: ExecutionPlan,
        execution_history: List[SubTaskResult],
        state: Dict[str, Any],
        context_changed: bool = False,
        current_step_index: int = 0,
        use_incremental: bool = True,
    ) -> Optional[ExecutionPlan]:
        """评估当前计划有效性，必要时动态重规划（兼容旧代码）"""
        if self._replan_manager:
            return await self._replan_manager.evaluate_and_replan(
                current_plan=current_plan,
                execution_history=execution_history,
                state=state,
                context_changed=context_changed,
                current_step_index=current_step_index,
                use_incremental=use_incremental,
            )
        return None

    async def _should_trigger_replan(
        self,
        step: PlanStep,
        result: SubTaskResult,
        execution_strategy: Any,
        current_step_index: int,
        results: List[SubTaskResult],
    ) -> Tuple[bool, str]:
        """判断是否需要触发 replan（兼容旧代码）"""
        if self._replan_manager:
            return await self._replan_manager.should_trigger_replan(
                step=step,
                result=result,
                execution_strategy=execution_strategy,
                current_step_index=current_step_index,
                results=results,
            )
        return False, ""

    async def _extract_working_memory(
        self,
        step: PlanStep,
        result: SubTaskResult,
        state: Dict[str, Any],
    ) -> None:
        """提取工作记忆（兼容旧代码）"""
        if self._post_policy_manager:
            await self._post_policy_manager.extract_working_memory(step, result, state)

    async def _register_consistency_checkpoint(
        self,
        step: PlanStep,
        result: SubTaskResult,
        state: Dict[str, Any],
    ) -> None:
        """注册一致性检查点（兼容旧代码）"""
        if self._consistency_manager:
            await self._consistency_manager.register_consistency_checkpoint(
                step, result, state
            )

    async def _check_consistency(
        self,
        step: PlanStep,
        arguments: Dict[str, Any],
        state: Dict[str, Any],
    ) -> List:
        """检查一致性（兼容旧代码）"""
        if self._consistency_manager:
            return await self._consistency_manager.check_consistency(
                step, arguments, state
            )
        return []

    async def _apply_post_policy(
        self,
        step: PlanStep,
        result: SubTaskResult,
        state: Dict[str, Any],
        execution_strategy: Any,
    ) -> Dict[str, Any]:
        """应用后处理策略（兼容旧代码）"""
        if self._post_policy_manager:
            return await self._post_policy_manager.apply_post_policy(
                step, result, state, execution_strategy
            )
        return {
            "should_extract_memory": False,
            "should_register_checkpoint": False,
            "checkpoint_type": None,
            "compressed_result": None,
        }

    def _get_validation_action(self, tool: Any, validation_passed: bool) -> str:
        """获取验证失败后的动作（兼容旧代码）"""
        if self._post_policy_manager:
            return self._post_policy_manager.get_validation_action(
                tool, validation_passed
            )
        return "retry" if not validation_passed else "continue"
