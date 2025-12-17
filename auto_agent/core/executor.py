"""
Execution Engine（执行引擎）

核心功能：
- 执行计划中的每个步骤
- 期望验证（ExpectationEvaluator）
- 失败策略解析
- 状态更新
- 内置 ExecutionContext 管理执行上下文
- 支持 LLM 动态生成工具调用 prompt
- 执行模式检测（循环依赖、重复失败等）
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from auto_agent.core.context import ExecutionContext
from auto_agent.llm.client import LLMClient
from auto_agent.models import (
    ExecutionPlan,
    FailAction,
    PlanStep,
    SubTaskResult,
    ValidationMode,
)
from auto_agent.retry.controller import RetryController
from auto_agent.retry.models import ErrorRecoveryRecord, ErrorType, RetryConfig
from auto_agent.tools.registry import ToolRegistry


class PatternType(Enum):
    """执行模式类型"""

    CIRCULAR_DEPENDENCY = "circular_dependency"  # 循环依赖
    REPEATED_FAILURE = "repeated_failure"  # 重复失败
    INEFFICIENT_SEQUENCE = "inefficient_sequence"  # 低效序列
    RESOURCE_BOTTLENECK = "resource_bottleneck"  # 资源瓶颈


@dataclass
class ExecutionPattern:
    """检测到的执行模式"""

    pattern_type: PatternType
    description: str
    frequency: int
    success_rate: float
    suggested_optimization: Optional[str] = None


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
        memory_storage_path: Optional[str] = None,
    ):
        self.tool_registry = tool_registry
        self.retry_controller = RetryController(retry_config, llm_client)
        self.llm_client = llm_client
        self._memory_storage_path = memory_storage_path
        # 内置执行上下文（在 execute_plan_stream 中初始化）
        self.context: Optional[ExecutionContext] = None
        # 缓存已创建的 MemorySystem（按 user_id）
        self._memory_systems: Dict[str, Any] = {}

    def _get_memory_system(self, user_id: str):
        """
        获取用户的 MemorySystem

        直接创建，不使用 MemoryManager
        LLM client 直接从 ExecutionEngine 传入
        """
        if user_id in self._memory_systems:
            return self._memory_systems[user_id]

        from pathlib import Path

        from auto_agent.memory.system import MemorySystem

        # 确定存储路径
        if self._memory_storage_path:
            storage_path = Path(self._memory_storage_path) / user_id
        else:
            storage_path = Path("./auto_agent_memory") / user_id

        storage_path.mkdir(parents=True, exist_ok=True)

        # 直接创建 MemorySystem，传入 llm_client
        memory_system = MemorySystem(
            storage_path=str(storage_path),
            auto_save=True,
            llm_client=self.llm_client,  # 直接使用 ExecutionEngine 的 llm_client
        )

        self._memory_systems[user_id] = memory_system
        return memory_system

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

    async def execute_plan_stream(
        self,
        plan: ExecutionPlan,
        state: Dict[str, Any],
        conversation_id: str,
        tool_executor: Optional[Callable] = None,
        agent_info: Optional[Dict[str, Any]] = None,
    ):
        """
        流式执行计划（AsyncGenerator）

        与 execute_plan 的区别：
        - 返回 AsyncGenerator，每个步骤完成后 yield 事件
        - 支持自定义 tool_executor（用于传递上下文，如数据库连接）
        - 内置 ExecutionContext 管理执行上下文

        Args:
            plan: 执行计划
            state: 初始状态字典
            conversation_id: 对话ID
            tool_executor: 自定义工具执行器，签名: async (tool_name, args) -> result
            agent_info: Agent 信息（可选），包含 name, description, goals, constraints

        Yields:
            Dict: 事件字典，包含 event 和 data 字段
        """
        # 初始化 ExecutionContext（整合 Memory 系统）
        query = state.get("inputs", {}).get("query", "")
        user_id = agent_info.get("user_id", "default") if agent_info else "default"
        plan_summary = "\n".join(
            f"{i + 1}. {s.description}" for i, s in enumerate(plan.subtasks)
        )

        # 获取用户的 MemorySystem（由框架内部管理）
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

        results = []
        current_step_index = 0
        max_iterations = state.get("control", {}).get("max_iterations", 20)
        iterations = 0

        while current_step_index < len(plan.subtasks) and iterations < max_iterations:
            iterations += 1
            step_num = current_step_index + 1
            subtask = plan.subtasks[current_step_index]

            # 更新 context 当前步骤
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
                # 执行步骤
                if tool_executor:
                    # 使用自定义执行器
                    tool = (
                        self.tool_registry.get_tool(subtask.tool)
                        if subtask.tool
                        else None
                    )
                    args = (
                        await self._build_tool_arguments(subtask, state, tool)
                        if tool
                        else {}
                    )
                    output = await tool_executor(subtask.tool, args)
                    result = SubTaskResult(
                        step_id=subtask.id,
                        success=output.get("success", True),
                        output=output,
                        error=output.get("error"),
                    )
                else:
                    result = await self._execute_subtask(
                        subtask, state, conversation_id
                    )

                results.append(result)

                # 更新状态
                if result.success:
                    self._update_state_from_result(subtask.tool, result.output, state)

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
                        yield {
                            "event": "stage_abort",
                            "data": {
                                "step": step_num,
                                "message": "执行中止",
                            },
                        }
                        break

            except Exception as e:
                yield {
                    "event": "stage_error",
                    "data": {
                        "step": step_num,
                        "name": subtask.tool,
                        "error": str(e),
                    },
                }
                # 记录异常到结果中用于重规划检测
                results.append(
                    SubTaskResult(
                        step_id=subtask.id,
                        success=False,
                        error=str(e),
                    )
                )

            # 每步执行后检查是否需要重规划
            # Requirements: 7.1, 7.3
            if len(results) >= 3:  # 至少有 3 次执行记录才检查
                new_plan = await self.evaluate_and_replan(
                    current_plan=plan,
                    execution_history=results,
                    state=state,
                )

                if new_plan is not None:
                    # 发送重规划事件通知
                    yield {
                        "event": "stage_replan",
                        "data": {
                            "step": step_num,
                            "reason": new_plan.warnings[0]
                            if new_plan.warnings
                            else "检测到执行问题，触发重规划",
                            "new_plan_intent": new_plan.intent,
                            "new_steps_count": len(new_plan.subtasks),
                            "message": f"执行计划已重新规划，新计划包含 {len(new_plan.subtasks)} 个步骤",
                        },
                    }

                    # 切换到新计划
                    plan = new_plan
                    current_step_index = 0
                    # 重置迭代计数器，但保留执行历史
                    continue

            current_step_index += 1

        state["control"]["iterations"] = iterations

        # 结束任务，清理短期记忆
        # 注意：默认不自动提炼执行历史到 L2，执行记录由应用层（DocHive）管理
        if self.context:
            self.context.end_task(promote_to_long_term=False)

        # 返回最终结果
        yield {
            "event": "execution_complete",
            "data": {
                "results": [
                    {"step_id": r.step_id, "success": r.success, "error": r.error}
                    for r in results
                ],
                "iterations": iterations,
                "state": state,
                "context": self.context,  # 返回完整的执行上下文
            },
        }

    async def _execute_subtask(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        conversation_id: str,
        use_smart_retry: bool = True,
    ) -> SubTaskResult:
        """
        执行单个子任务（带重试和验证）

        参数构造逻辑：
        1. 如果有 read_fields，从 state 中读取数据
        2. 合并 subtask.parameters 中的静态参数
        3. 如果有 LLM client，可以动态构造参数

        Args:
            subtask: 计划步骤
            state: 当前状态字典
            conversation_id: 对话ID
            use_smart_retry: 是否使用智能重试（默认 True）
                - True: 使用 LLM 驱动的智能错误分析和参数修正
                - False: 使用传统的简单重试逻辑（向后兼容）
        """
        # 如果启用智能重试，委托给智能重试方法
        if use_smart_retry:
            return await self._execute_subtask_with_smart_retry(
                subtask, state, conversation_id
            )

        # 以下是传统的简单重试逻辑（向后兼容）
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

        # 构造工具参数（从 state 读取 + 静态参数合并）
        arguments = await self._build_tool_arguments(subtask, state, tool)

        # 执行工具（带重试）
        try:
            output = await self.retry_controller.execute_with_retry(
                tool.execute,
                **arguments,
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

    async def _execute_subtask_with_smart_retry(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        conversation_id: str,
    ) -> SubTaskResult:
        """
        带智能重试的子任务执行

        增强点：
        1. 失败时使用 LLM 分析错误
        2. 如果是参数错误，尝试修正参数后重试
        3. 成功恢复后记录到记忆系统

        Args:
            subtask: 计划步骤
            state: 当前状态字典
            conversation_id: 对话ID

        Returns:
            SubTaskResult: 子任务执行结果
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

        # 构造工具参数
        arguments = await self._build_tool_arguments(subtask, state, tool)
        original_arguments = dict(arguments)  # 保存原始参数用于记录

        last_exception: Optional[Exception] = None
        max_retries = self.retry_controller.config.max_retries

        for attempt in range(max_retries + 1):
            try:
                # 执行工具
                if asyncio.iscoroutinefunction(tool.execute):
                    output = await tool.execute(**arguments)
                else:
                    output = tool.execute(**arguments)

                # 如果是重试成功（attempt > 0），记录恢复策略到记忆系统
                if attempt > 0 and last_exception is not None:
                    await self._record_successful_recovery(
                        exception=last_exception,
                        tool_name=subtask.tool,
                        original_params=original_arguments,
                        fixed_params=arguments,
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
                last_exception = e

                # 如果是最后一次尝试，尝试替代工具
                if attempt >= max_retries:
                    # 尝试使用替代工具 (Requirements: 6.3)
                    alt_result = await self._try_alternative_tool(
                        original_tool_name=subtask.tool,
                        subtask=subtask,
                        state=state,
                        original_error=str(e),
                    )
                    if alt_result is not None:
                        return alt_result

                    # 所有替代工具也失败，返回原始错误
                    return SubTaskResult(
                        step_id=subtask.id,
                        success=False,
                        error=str(e),
                    )

                # 智能错误分析
                error_analysis = await self.retry_controller.analyze_error(
                    exception=e,
                    context={"state": state, "arguments": arguments},
                    tool_definition=tool.definition
                    if hasattr(tool, "definition")
                    else None,
                )

                # 如果错误不可恢复，尝试替代工具 (Requirements: 6.3)
                if not error_analysis.is_recoverable:
                    alt_result = await self._try_alternative_tool(
                        original_tool_name=subtask.tool,
                        subtask=subtask,
                        state=state,
                        original_error=str(e),
                    )
                    if alt_result is not None:
                        return alt_result

                    # 所有替代工具也失败，返回原始错误
                    return SubTaskResult(
                        step_id=subtask.id,
                        success=False,
                        error=f"{str(e)} (不可恢复: {error_analysis.root_cause})",
                    )

                # 如果是参数错误，尝试修正参数
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
                    # 只有当参数确实被修改时才更新
                    if fixed_arguments != arguments:
                        arguments = fixed_arguments

                # 计算延迟时间并等待
                delay = self.retry_controller.get_delay(attempt)
                await asyncio.sleep(delay)

        # 理论上不应该到达这里，但如果到达，尝试替代工具
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
        """
        当工具失败且有 alternative_tools 时尝试替代工具

        遍历工具定义中的 alternative_tools 列表，依次尝试执行替代工具，
        直到成功或所有替代工具都失败。

        Args:
            original_tool_name: 原始失败的工具名称
            subtask: 计划步骤
            state: 当前状态字典
            original_error: 原始错误信息

        Returns:
            SubTaskResult: 替代工具执行结果，如果所有替代工具都失败则返回 None

        Requirements: 6.3, 7.2
        """
        # 获取原始工具定义
        original_tool = self.tool_registry.get_tool(original_tool_name)
        if not original_tool or not hasattr(original_tool, "definition"):
            return None

        tool_def = original_tool.definition
        alternative_tools = (
            tool_def.alternative_tools if tool_def.alternative_tools else []
        )

        if not alternative_tools:
            return None

        # 依次尝试替代工具
        for alt_tool_name in alternative_tools:
            alt_tool = self.tool_registry.get_tool(alt_tool_name)
            if not alt_tool:
                # 替代工具不存在，跳过
                continue

            try:
                # 构造替代工具的参数
                # 创建一个临时的 subtask，使用替代工具名
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

                # 构造参数
                arguments = await self._build_tool_arguments(
                    alt_subtask, state, alt_tool
                )

                # 执行替代工具
                if asyncio.iscoroutinefunction(alt_tool.execute):
                    output = await alt_tool.execute(**arguments)
                else:
                    output = alt_tool.execute(**arguments)

                # 检查执行结果
                if output.get("success", True):
                    # 替代工具执行成功
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
                else:
                    # 替代工具执行失败，继续尝试下一个
                    continue

            except Exception:
                # 替代工具执行异常，继续尝试下一个
                continue

        # 所有替代工具都失败
        return None

    async def _record_successful_recovery(
        self,
        exception: Exception,
        tool_name: str,
        original_params: Dict[str, Any],
        fixed_params: Dict[str, Any],
    ) -> None:
        """
        记录成功的错误恢复策略到记忆系统

        Args:
            exception: 原始异常
            tool_name: 工具名称
            original_params: 原始参数
            fixed_params: 修正后的参数
        """
        import time

        # 如果没有记忆系统，跳过记录
        if not self.context or not self.context.memory_system:
            return

        try:
            # 创建恢复记录
            recovery_record = ErrorRecoveryRecord(
                error_type=type(exception).__name__,
                error_message=str(exception),
                tool_name=tool_name,
                original_params=original_params,
                fixed_params=fixed_params,
                recovery_successful=True,
                timestamp=time.time(),
            )

            # 转换为记忆内容
            memory_content = recovery_record.to_memory_content()

            # 记录到 L2 语义记忆
            memory_system = self.context.memory_system
            if hasattr(memory_system, "add_experience"):
                await memory_system.add_experience(
                    category="error_recovery",
                    content=memory_content,
                )
            elif hasattr(memory_system, "l2_semantic") and hasattr(
                memory_system.l2_semantic, "add"
            ):
                # 直接使用 L2 语义记忆
                memory_system.l2_semantic.add(
                    content=str(memory_content),
                    metadata={"category": "error_recovery", "tool_name": tool_name},
                )
        except Exception:
            # 记录失败不应影响主流程
            pass

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
        validate_fn = (
            tool.definition.validate_function if hasattr(tool, "definition") else None
        )

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

        state["control"]["failed_steps"].append(
            {
                "step": subtask.id,
                "name": subtask.tool,
                "error": result.error,
            }
        )

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

        if (
            "回退" in strategy_lower
            or "返回" in strategy_lower
            or "goto" in strategy_lower
        ):
            # 尝试提取步骤号
            import re

            match = re.search(r"步骤\s*(\d+)", strategy)
            if match:
                return FailAction(type="goto", target_step=match.group(1))
            return FailAction(type="retry")  # 找不到步骤号，改为重试

        if (
            "停止" in strategy_lower
            or "终止" in strategy_lower
            or "abort" in strategy_lower
        ):
            return FailAction(type="abort")

        # 默认：使用 fallback
        return FailAction(type="fallback")

    async def _build_tool_arguments(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        tool: Any,
    ) -> Dict[str, Any]:
        """
        构造工具参数

        核心思路：让 LLM 智能决定参数值

        逻辑：
        1. 如果有 pinned_parameters（固定参数），直接使用
        2. 如果有 read_fields，从 state 中读取
        3. 使用 LLM 智能构造剩余参数
        4. 验证参数，验证失败时尝试修正

        Args:
            subtask: 计划步骤
            state: 当前状态
            tool: 工具实例

        Returns:
            工具参数字典

        Requirements: 5.1, 5.4
        """
        arguments = {}

        # 1. 处理 pinned_parameters（固定参数，最高优先级）
        if subtask.pinned_parameters:
            arguments.update(subtask.pinned_parameters)

        # 2. 合并静态参数
        if subtask.parameters:
            arguments.update(subtask.parameters)

        # 3. 从 state 中读取 read_fields
        if subtask.read_fields:
            for field in subtask.read_fields:
                if field in state:
                    arguments[field] = state[field]
                elif "." in field:
                    value = self._get_nested_value(state, field)
                    if value is not None:
                        param_name = field.split(".")[-1]
                        arguments[param_name] = value

        # 4. 使用 LLM 智能构造参数（核心改进）
        if self.llm_client and tool:
            arguments = await self._build_arguments_with_llm_v2(
                subtask, state, tool, arguments
            )

        # 5. 验证参数，验证失败时尝试修正
        if tool:
            arguments = await self._validate_and_fix_parameters(
                arguments, tool, state, subtask
            )

        return arguments

    async def _validate_and_fix_parameters(
        self,
        arguments: Dict[str, Any],
        tool: Any,
        state: Dict[str, Any],
        subtask: PlanStep,
    ) -> Dict[str, Any]:
        """
        验证参数并在失败时尝试修正

        逻辑：
        1. 使用 _validate_parameters 验证参数
        2. 如果验证失败且有 LLM client，尝试使用 LLM 修正参数
        3. 修正后再次验证，最多尝试 2 次

        Args:
            arguments: 要验证的参数字典
            tool: 工具实例
            state: 当前状态
            subtask: 计划步骤

        Returns:
            验证通过或修正后的参数字典

        Requirements: 5.1, 5.4
        """
        import json

        max_fix_attempts = 2

        for attempt in range(max_fix_attempts):
            # 验证参数
            is_valid, errors = self._validate_parameters(arguments, tool)

            if is_valid:
                return arguments

            # 如果没有 LLM client，无法修正，直接返回
            if not self.llm_client:
                return arguments

            # 尝试使用 LLM 修正参数
            tool_def = tool.definition

            # 构建验证器信息
            validators_info = []
            if tool_def.parameter_validators:
                for v in tool_def.parameter_validators:
                    validators_info.append(
                        {
                            "parameter": v.parameter_name,
                            "type": v.validation_type,
                            "rule": v.validation_rule,
                            "error_message": v.error_message,
                        }
                    )

            # 构建参数信息
            params_info = []
            for p in tool_def.parameters:
                params_info.append(
                    {
                        "name": p.name,
                        "type": p.type,
                        "description": p.description,
                        "required": p.required,
                    }
                )

            # 构建修正 prompt
            prompt = f"""你是一个参数修正助手。当前工具参数验证失败，请根据验证规则修正参数。

【工具】
名称: {tool_def.name}
描述: {tool_def.description}

【参数定义】
{json.dumps(params_info, ensure_ascii=False, indent=2)}

【验证规则】
{json.dumps(validators_info, ensure_ascii=False, indent=2)}

【当前参数】
{json.dumps(arguments, ensure_ascii=False, indent=2)}

【验证错误】
{chr(10).join(errors)}

【当前状态（可用数据）】
{self._compress_state_for_llm(state)}

【任务】
根据验证规则修正参数值，确保参数能通过验证。
- 仔细阅读验证规则，理解参数的约束条件
- 从状态中找到符合约束的数据
- 如果是范围验证，确保数值在允许范围内
- 如果是枚举验证，确保值在允许的选项中
- 如果是正则验证，确保值匹配正则表达式

请返回修正后的完整参数 JSON：
```json
{{"param_name": "corrected_value", ...}}
```"""

            try:
                response = await self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1,
                )

                # 提取 JSON
                import re

                json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
                if json_match:
                    fixed_args = json.loads(json_match.group())
                    # 合并修正后的参数
                    arguments.update(fixed_args)
            except Exception:
                # LLM 修正失败，返回原参数
                return arguments

        # 达到最大尝试次数，返回当前参数
        return arguments

    async def _build_arguments_with_llm_v2(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        tool: Any,
        existing_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用 LLM 智能构造工具参数（V3 版本 - 完全语义驱动）

        核心思路：
        1. 基于执行历史的语义描述（description）判断参数关联
        2. 支持多步骤结果合并（如 step1 + step2 的结果组合成当前参数）
        3. param_aliases 仅作为 fallback（已废弃，未来移除）
        4. LLM 完全自主决策参数映射

        Args:
            subtask: 计划步骤
            state: 当前状态
            tool: 工具实例
            existing_args: 已有的参数（pinned_parameters 等）

        Returns:
            完整的工具参数字典
        """
        import json

        result = dict(existing_args)
        tool_def = tool.definition

        # 1. 收集参数信息和缺失参数
        params_info = []
        missing_params = []

        for p in tool_def.parameters:
            param_info = {
                "name": p.name,
                "type": p.type,
                "description": p.description,
                "required": p.required,
            }
            params_info.append(param_info)

            # 检查哪些必需参数还没有值
            if p.required and (p.name not in result or result[p.name] is None):
                missing_params.append(p.name)

        # 如果所有必需参数都有值了，直接返回
        if not missing_params:
            return result

        # 2. 获取语义化的执行历史
        semantic_history = ""
        if self.context:
            semantic_history = self.context.get_semantic_history_text(max_steps=10)

        # 3. 压缩当前状态
        state_summary = self._compress_state_for_llm(state)

        # 4. 构建语义驱动的 prompt
        prompt = f"""你是一个智能参数构造助手。根据执行历史和当前状态，为工具智能构造参数。

【当前步骤】
工具: {subtask.tool}
描述: {subtask.description}

【工具参数定义】
{json.dumps(params_info, ensure_ascii=False, indent=2)}

【已有参数】
{json.dumps(result, ensure_ascii=False, indent=2)}

【需要补充的参数】
{missing_params}

【执行历史（语义摘要）】
{semantic_history if semantic_history else "无历史记录"}

【当前状态】
{state_summary}

【任务】
根据执行历史和当前状态，智能决定缺失参数的值。

关键规则：
1. 仔细阅读每个参数的 description，理解参数的语义用途
2. 查看执行历史中每一步的"目标"和"描述"，判断哪些步骤的输出与当前参数相关
3. 参数可能需要从多个步骤的结果中组合（如合并多个搜索结果）
4. 如果历史步骤的输出类型与参数类型匹配，优先使用
5. 从 state 中找到语义上最匹配的数据
6. 如果确实没有合适的数据，可以根据步骤描述推断合理的默认值

示例思考过程：
- 参数 "documents" 需要文档列表 → 查看历史中哪些步骤输出了文档
- 参数 "query" 需要查询文本 → 可能来自 inputs.query 或之前的分析结果
- 参数 "outline" 需要大纲 → 查看是否有步骤生成了大纲

请返回 JSON 格式，只包含需要补充的参数：
```json
{{"param_name": "value_or_state_path", ...}}
```

注意：
- 如果值来自 state，直接写值（不是路径）
- 如果需要合并多个来源，在 JSON 中体现合并后的结果
- 如果是复杂对象，确保 JSON 格式正确"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
            )

            # 提取 JSON（支持嵌套对象）
            import re

            # 尝试匹配完整的 JSON 对象
            json_match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
            if not json_match:
                # 尝试直接匹配 JSON
                json_match = re.search(
                    r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL
                )

            if json_match:
                json_str = (
                    json_match.group(1) if "```" in response else json_match.group()
                )
                new_args = json.loads(json_str)

                # 处理 state 路径引用（如 "state.documents"）
                for key, value in new_args.items():
                    if isinstance(value, str) and value.startswith("state."):
                        path = value[6:]  # 去掉 "state." 前缀
                        resolved = self._get_nested_value(state, path)
                        if resolved is not None:
                            new_args[key] = resolved

                result.update(new_args)
                return result

        except Exception:
            # LLM 失败，使用 fallback
            pass

        # Fallback：使用 param_aliases（已废弃，仅作为兜底）
        return self._build_arguments_fallback_simple(subtask, state, result, tool_def)

    def _build_arguments_fallback_simple(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        existing_args: Dict[str, Any],
        tool_def: Any = None,
    ) -> Dict[str, Any]:
        """
        简单的 fallback 参数构造（当 LLM 不可用时使用）

        ⚠️ 注意：此方法仅作为 LLM 失败时的兜底方案
        param_aliases 已废弃，未来版本将移除

        优先级：
        1. existing_args（已有参数）
        2. 从执行历史中按语义匹配（简单规则）
        3. param_aliases（已废弃，仅兜底）
        4. 同名匹配（state 中与参数同名的字段）
        5. inputs 中的通用参数
        """

        result = dict(existing_args)

        # 获取工具定义
        if tool_def is None:
            tool = self.tool_registry.get_tool(subtask.tool) if subtask.tool else None
            tool_def = tool.definition if tool else None

        if tool_def:
            for param in tool_def.parameters:
                param_name = param.name
                if param_name in result and result[param_name] is not None:
                    continue

                # 1. 尝试从执行历史中按类型匹配
                if self.context and self.context.history:
                    value = self._match_from_history(
                        param_name, param.type, param.description
                    )
                    if value is not None:
                        result[param_name] = value
                        continue

                # 2. 尝试 param_aliases（已废弃）
                if tool_def.param_aliases and param_name in tool_def.param_aliases:
                    # 发出废弃警告（仅在调试模式下）
                    # warnings.warn(
                    #     f"param_aliases 已废弃，建议使用 LLM 语义映射。"
                    #     f"工具 {tool_def.name} 的参数 {param_name} 使用了 alias 映射。",
                    #     DeprecationWarning,
                    #     stacklevel=2,
                    # )
                    aliases = tool_def.param_aliases[param_name]
                    alias_list = aliases if isinstance(aliases, list) else [aliases]
                    found = False
                    for alias in alias_list:
                        if alias in state and state[alias] is not None:
                            result[param_name] = state[alias]
                            found = True
                            break
                        value = self._get_nested_value(state, alias)
                        if value is not None:
                            result[param_name] = value
                            found = True
                            break
                    if found:
                        continue

                # 3. 尝试同名匹配
                if param_name in state:
                    result[param_name] = state[param_name]
                    continue

                # 4. 尝试从 inputs 获取
                if "inputs" in state and param_name in state["inputs"]:
                    result[param_name] = state["inputs"][param_name]

        return result

    def _match_from_history(
        self,
        param_name: str,
        param_type: str,
        param_description: str,
    ) -> Any:
        """
        从执行历史中按类型和语义简单匹配参数值

        这是一个简单的规则匹配，作为 LLM 不可用时的兜底

        Args:
            param_name: 参数名
            param_type: 参数类型
            param_description: 参数描述

        Returns:
            匹配到的值，或 None
        """
        if not self.context or not self.context.history:
            return None

        # 关键词匹配规则
        keywords_map = {
            "document": ["documents", "docs", "doc_list"],
            "outline": ["outline", "structure", "sections"],
            "query": ["query", "search_query", "keywords"],
            "content": ["content", "text", "body"],
            "result": ["results", "search_results", "findings"],
        }

        # 找到与参数名相关的关键词
        related_keys = []
        param_lower = param_name.lower()
        for key, aliases in keywords_map.items():
            if key in param_lower or param_lower in aliases:
                related_keys.extend(aliases)
                related_keys.append(key)

        if not related_keys:
            related_keys = [param_name]

        # 从最近的历史记录中查找
        for record in reversed(self.context.history):
            if not record.success or not record.output:
                continue

            output = record.output
            if isinstance(output, dict):
                for key in related_keys:
                    if key in output:
                        return output[key]

        return None

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """从嵌套字典中获取值，支持点号路径"""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def _compress_state_for_llm(
        self, state: Dict[str, Any], max_chars: int = 4000
    ) -> str:
        """压缩状态信息供 LLM 使用"""
        import json

        compressed = {}
        for key, value in state.items():
            if key == "control":
                continue
            if key == "documents" and isinstance(value, list):
                compressed["documents"] = f"[{len(value)} documents]"
                if value:
                    compressed["document_ids"] = [d.get("id") for d in value[:10]]
            elif key == "document_ids" and isinstance(value, list):
                compressed["document_ids"] = value[:20]
            elif isinstance(value, dict) and len(str(value)) > 500:
                compressed[key] = f"{{...{len(value)} keys}}"
            elif isinstance(value, list) and len(value) > 10:
                compressed[key] = f"[{len(value)} items]"
            else:
                compressed[key] = value

        result = json.dumps(compressed, ensure_ascii=False, indent=2)
        if len(result) > max_chars:
            result = result[:max_chars] + "..."
        return result

    async def generate_tool_prompt(
        self,
        subtask: PlanStep,
        tool: Any,
        prompt_template: Optional[str] = None,
    ) -> Optional[str]:
        """
        让 LLM 根据执行上下文动态生成工具调用的 prompt

        这个方法允许 LLM 根据当前上下文（用户输入、执行历史、当前状态）
        智能生成最适合当前步骤的 prompt，而不是使用固定的 prompt 模板。

        Args:
            subtask: 当前步骤
            tool: 工具实例
            prompt_template: 可选的 prompt 模板（包含 {变量名} 占位符）

        Returns:
            生成的 prompt 字符串，如果生成失败返回 None
        """
        if not self.llm_client or not self.context:
            return None

        import json

        # 获取工具信息
        tool_def = tool.definition
        tool_info = {
            "name": tool_def.name,
            "description": tool_def.description,
            "parameters": [
                {"name": p.name, "type": p.type, "description": p.description}
                for p in tool_def.parameters
            ],
        }

        # 构建生成 prompt 的请求
        meta_prompt = f"""你是一个智能 prompt 生成助手。根据当前执行上下文，为工具调用生成最合适的 prompt。

【执行上下文】
{self.context.to_llm_context()}

【当前步骤】
步骤 {self.context.current_step}: {subtask.description}

【工具信息】
{json.dumps(tool_info, ensure_ascii=False, indent=2)}

【任务】
根据上下文，生成一个清晰、具体的 prompt，用于指导这个工具的执行。
- prompt 应该包含用户的原始意图
- prompt 应该结合之前步骤的输出结果
- prompt 应该明确说明期望的输出格式和内容
- 如果是生成类工具（如写文档），prompt 应该包含具体的写作要求

{"【参考模板】" + chr(10) + prompt_template if prompt_template else ""}

请直接返回生成的 prompt 文本，不要包含任何解释或标记。"""

        try:
            generated_prompt = await self.llm_client.chat(
                [{"role": "user", "content": meta_prompt}],
                temperature=0.3,
            )
            return generated_prompt.strip()
        except Exception:
            return None

    def get_context(self) -> Optional[ExecutionContext]:
        """获取当前执行上下文"""
        return self.context

    def get_context_summary(self) -> str:
        """获取执行上下文摘要（供外部使用）"""
        if not self.context:
            return ""
        return self.context.to_llm_context()

    def _detect_execution_patterns(
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

        # 1. 检测重复失败模式（最近 5 次中 3 次以上失败）
        recent_results = (
            execution_history[-5:] if len(execution_history) >= 5 else execution_history
        )
        recent_failures = [r for r in recent_results if not r.success]

        if len(recent_failures) >= 3:
            # 计算成功率
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

        # 2. 检测循环依赖（同一步骤执行超过 3 次）
        step_counts: Dict[str, int] = {}
        for r in execution_history:
            step_id = r.step_id
            step_counts[step_id] = step_counts.get(step_id, 0) + 1

        for step_id, count in step_counts.items():
            if count > 3:
                # 计算该步骤的成功率
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

    async def _generate_alternative_plan(
        self,
        current_plan: ExecutionPlan,
        patterns: List[ExecutionPattern],
        state: Dict[str, Any],
        execution_history: List[SubTaskResult],
    ) -> Optional[ExecutionPlan]:
        """
        当检测到问题模式时生成替代计划

        使用 LLM 分析失败原因并建议新策略

        Args:
            current_plan: 当前执行计划
            patterns: 检测到的问题模式列表
            state: 当前状态字典
            execution_history: 执行历史记录

        Returns:
            新的执行计划，如果无法生成则返回 None

        Requirements: 7.1, 7.2
        """
        import json

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
        for r in execution_history[-10:]:  # 只取最近 10 条
            history_summary.append(
                {
                    "step_id": r.step_id,
                    "success": r.success,
                    "error": r.error[:200] if r.error else None,  # 截断错误信息
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

        # 获取可用工具列表
        tools_catalog = (
            self.tool_registry.get_tools_catalog()
            if self.tool_registry
            else "无可用工具信息"
        )

        # 构建 LLM prompt
        prompt = f"""你是一个智能任务规划器。当前执行计划遇到了问题，需要生成替代方案。

【检测到的问题模式】
{patterns_description}

【当前计划】
{json.dumps(plan_summary, ensure_ascii=False, indent=2)}

【执行历史（最近 10 条）】
{json.dumps(history_summary, ensure_ascii=False, indent=2)}

【当前状态摘要】
{self._compress_state_for_llm(state)}

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
                temperature=0.3,  # 较低温度，更稳定的输出
            )

            # 提取 JSON
            import re

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
            else:
                # 尝试直接解析
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    response = json_match.group()

            plan_json = json.loads(response)

            # 转换为 ExecutionPlan
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
                state_schema=current_plan.state_schema,  # 保留原有的 state schema
                warnings=[
                    f"这是替代计划，原因: {plan_json.get('analysis', '检测到执行问题')}"
                ],
            )

        except Exception:
            # LLM 调用失败，返回 None
            return None

    async def evaluate_and_replan(
        self,
        current_plan: ExecutionPlan,
        execution_history: List[SubTaskResult],
        state: Dict[str, Any],
        context_changed: bool = False,
    ) -> Optional[ExecutionPlan]:
        """
        评估当前计划有效性，必要时动态重规划

        触发条件：
        1. 连续失败超过阈值（最近 5 次中 3 次以上失败）
        2. 检测到循环模式（同一步骤执行超过 3 次）
        3. 上下文发生重大变化（context_changed=True）

        Args:
            current_plan: 当前执行计划
            execution_history: 执行历史记录列表
            state: 当前状态字典
            context_changed: 上下文是否发生变化

        Returns:
            新的执行计划（如果需要重规划），否则返回 None

        Requirements: 7.1, 7.2, 7.3
        """
        # 如果上下文发生变化，强制重规划
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
        patterns = self._detect_execution_patterns(execution_history)

        # 如果没有检测到问题模式，不需要重规划
        if not patterns:
            return None

        # 检查是否有需要触发重规划的模式
        problem_patterns = [
            p
            for p in patterns
            if p.pattern_type
            in [
                PatternType.CIRCULAR_DEPENDENCY,
                PatternType.REPEATED_FAILURE,
            ]
        ]

        if not problem_patterns:
            return None

        # 生成替代计划
        return await self._generate_alternative_plan(
            current_plan, problem_patterns, state, execution_history
        )

    def _validate_parameters(
        self,
        arguments: Dict[str, Any],
        tool: Any,
    ) -> Tuple[bool, List[str]]:
        """
        根据工具定义的 parameter_validators 验证参数

        支持的验证类型：
        - regex: 正则表达式匹配
        - range: 数值范围检查（格式: "min,max"）
        - enum: 枚举值检查（格式: "value1,value2,value3"）
        - custom: 自定义验证（调用工具定义的验证函数）

        Args:
            arguments: 要验证的参数字典
            tool: 工具实例

        Returns:
            (is_valid, error_messages): 验证是否通过，以及错误消息列表

        Requirements: 5.1
        """
        import re

        if not tool or not hasattr(tool, "definition"):
            return True, []

        tool_def = tool.definition
        validators = (
            tool_def.parameter_validators if tool_def.parameter_validators else []
        )

        if not validators:
            return True, []

        errors: List[str] = []

        for validator in validators:
            param_name = validator.parameter_name
            validation_type = validator.validation_type
            validation_rule = validator.validation_rule
            error_message = validator.error_message

            # 如果参数不存在，跳过验证（必需参数检查由其他逻辑处理）
            if param_name not in arguments:
                continue

            param_value = arguments[param_name]

            # 如果参数值为 None，跳过验证
            if param_value is None:
                continue

            is_valid = True

            if validation_type == "regex":
                # 正则表达式验证
                try:
                    if not isinstance(param_value, str):
                        param_value = str(param_value)
                    if not re.match(validation_rule, param_value):
                        is_valid = False
                except re.error:
                    # 正则表达式无效，跳过验证
                    continue

            elif validation_type == "range":
                # 数值范围验证（格式: "min,max"）
                try:
                    parts = validation_rule.split(",")
                    if len(parts) == 2:
                        min_val = (
                            float(parts[0].strip())
                            if parts[0].strip()
                            else float("-inf")
                        )
                        max_val = (
                            float(parts[1].strip())
                            if parts[1].strip()
                            else float("inf")
                        )

                        # 尝试将参数值转换为数值
                        num_value = float(param_value)

                        if num_value < min_val or num_value > max_val:
                            is_valid = False
                except (ValueError, TypeError):
                    # 无法转换为数值，验证失败
                    is_valid = False

            elif validation_type == "enum":
                # 枚举值验证（格式: "value1,value2,value3"）
                allowed_values = [v.strip() for v in validation_rule.split(",")]
                str_value = str(param_value)
                if str_value not in allowed_values:
                    is_valid = False

            elif validation_type == "custom":
                # 自定义验证（调用工具定义的验证函数）
                # validation_rule 是验证函数的名称
                if (
                    hasattr(tool_def, "validate_function")
                    and tool_def.validate_function
                ):
                    try:
                        # 自定义验证函数签名: (param_name, param_value, arguments) -> bool
                        validate_fn = tool_def.validate_function
                        if callable(validate_fn):
                            result = validate_fn(param_name, param_value, arguments)
                            if asyncio.iscoroutine(result):
                                # 如果是协程，这里不能直接 await，标记为需要异步验证
                                # 在同步上下文中，我们跳过异步验证
                                continue
                            is_valid = bool(result)
                    except Exception:
                        # 验证函数执行失败，跳过
                        continue

            if not is_valid:
                errors.append(f"参数 '{param_name}' 验证失败: {error_message}")

        return len(errors) == 0, errors

    def _update_state_from_result(
        self,
        tool_name: Optional[str],
        result: Dict[str, Any],
        state: Dict[str, Any],
    ):
        """
        根据工具执行结果更新状态字典

        通用逻辑（不硬编码任何工具名）：
        1. 应用工具的 state_mapping（字段名映射，最高优先级）
        2. 根据工具的 output_schema 定义，将结果字段写入 state
        3. 如果工具没有 output_schema，将所有非 success/error 字段写入 state

        state_mapping 示例：
        - {"search_query": "search_queries"} 表示将 result["search_query"] 写入 state["search_queries"]
        - 这允许工具输出字段名与 state 字段名不同
        """
        if not result or not result.get("success"):
            return

        if not tool_name:
            return

        # 获取工具定义
        tool = self.tool_registry.get_tool(tool_name)

        # 需要排除的通用字段
        exclude_keys = {"success", "error", "message"}

        # 获取 state_mapping（如果有）
        state_mapping = {}
        if tool and hasattr(tool, "definition") and tool.definition.state_mapping:
            state_mapping = tool.definition.state_mapping

        # 确定要写入的字段
        fields_to_write = set()
        if tool and tool.definition.output_schema:
            fields_to_write = set(tool.definition.output_schema.keys()) - exclude_keys
        else:
            fields_to_write = set(result.keys()) - exclude_keys

        # 写入 state
        for key in fields_to_write:
            if key in result:
                # 应用 state_mapping（如果有映射则用映射后的 key，否则用原 key）
                target_key = state_mapping.get(key, key)
                state[target_key] = result[key]
