"""
Execution Engine（执行引擎）

核心功能：
- 执行计划中的每个步骤
- 期望验证（ExpectationEvaluator）
- 失败策略解析
- 状态更新
- 内置 ExecutionContext 管理执行上下文
- 支持 LLM 动态生成工具调用 prompt
"""

import asyncio
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
        memory_storage_path: Optional[str] = None,
    ):
        self.tool_registry = tool_registry
        self.retry_controller = RetryController(retry_config, llm_client)
        self.llm_client = llm_client
        self._memory_storage_path = memory_storage_path
        # 内置执行上下文（在 execute_plan_stream 中初始化）
        self.context: Optional[ExecutionContext] = None
    
    def _get_memory_system(self, user_id: str):
        """获取用户的 MemorySystem（由框架内部管理）"""
        from auto_agent.memory.manager import get_memory_manager
        
        if self._memory_storage_path:
            manager = get_memory_manager(self._memory_storage_path)
        else:
            manager = get_memory_manager()
        
        return manager.get_memory_system(user_id)

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
            f"{i+1}. {s.description}" for i, s in enumerate(plan.subtasks)
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
                    tool = self.tool_registry.get_tool(subtask.tool) if subtask.tool else None
                    args = await self._build_tool_arguments(subtask, state, tool) if tool else {}
                    output = await tool_executor(subtask.tool, args)
                    result = SubTaskResult(
                        step_id=subtask.id,
                        success=output.get("success", True),
                        output=output,
                        error=output.get("error"),
                    )
                else:
                    result = await self._execute_subtask(subtask, state, conversation_id)

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
                "results": [{"step_id": r.step_id, "success": r.success, "error": r.error} for r in results],
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
    ) -> SubTaskResult:
        """
        执行单个子任务（带重试和验证）

        参数构造逻辑：
        1. 如果有 read_fields，从 state 中读取数据
        2. 合并 subtask.parameters 中的静态参数
        3. 如果有 LLM client，可以动态构造参数
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

        Args:
            subtask: 计划步骤
            state: 当前状态
            tool: 工具实例

        Returns:
            工具参数字典
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
            arguments = await self._build_arguments_with_llm_v2(subtask, state, tool, arguments)

        return arguments

    async def _build_arguments_with_llm_v2(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        tool: Any,
        existing_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用 LLM 智能构造工具参数（V2 版本）

        核心思路：
        - 首先应用工具定义的 param_aliases（参数别名映射）
        - 然后用 LLM 智能补充剩余缺失参数
        - 完全不硬编码任何工具名或参数映射规则

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

        # 1. 首先应用 param_aliases（工具定义的参数别名映射）
        if tool_def.param_aliases:
            for param_name, aliases in tool_def.param_aliases.items():
                if param_name not in result or result[param_name] is None:
                    # aliases 可能是字符串或列表
                    alias_list = aliases if isinstance(aliases, list) else [aliases]
                    for alias in alias_list:
                        # 先尝试直接从 state 获取
                        if alias in state and state[alias] is not None:
                            result[param_name] = state[alias]
                            break
                        # 再尝试嵌套路径
                        value = self._get_nested_value(state, alias)
                        if value is not None:
                            result[param_name] = value
                            break

        # 2. 收集参数信息和缺失参数
        params_info = []
        missing_params = []
        
        for p in tool_def.parameters:
            param_info = {
                "name": p.name,
                "type": p.type,
                "description": p.description,
                "required": p.required,
            }
            # 如果有别名映射，添加提示
            if tool_def.param_aliases and p.name in tool_def.param_aliases:
                param_info["alias_hint"] = f"可从 state['{tool_def.param_aliases[p.name]}'] 获取"
            params_info.append(param_info)
            
            # 检查哪些必需参数还没有值
            if p.required and (p.name not in result or result[p.name] is None):
                missing_params.append(p.name)

        # 如果所有必需参数都有值了，直接返回
        if not missing_params:
            return result

        # 3. 使用 LLM 智能补充缺失参数
        state_summary = self._compress_state_for_llm(state)

        # 构建 prompt（不硬编码任何工具名或参数映射）
        prompt = f"""你是一个智能参数构造助手。根据当前执行上下文，为工具构造缺失的参数。

【当前步骤】
工具: {subtask.tool}
描述: {subtask.description}

【工具参数定义】
{json.dumps(params_info, ensure_ascii=False, indent=2)}

【已有参数】
{json.dumps(result, ensure_ascii=False, indent=2)}

【需要补充的参数】
{missing_params}

【当前状态（可用数据）】
{state_summary}

【任务】
根据当前状态中的数据，智能决定缺失参数的值。
- 仔细阅读每个参数的 description，理解参数的用途
- 从状态中找到语义上最匹配的数据填充参数
- 如果参数有 alias_hint，优先按提示获取
- 如果状态中没有合适的数据，可以根据步骤描述推断合理的默认值

请返回 JSON 格式，只包含需要补充的参数：
```json
{{"param_name": "value", ...}}
```"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,  # 低温度，更确定性
            )

            # 提取 JSON
            import re
            json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
            if json_match:
                new_args = json.loads(json_match.group())
                # 合并参数（新参数覆盖）
                result.update(new_args)
                return result
        except Exception as e:
            # LLM 失败，使用 fallback
            pass

        # Fallback：使用简单规则（基于 param_aliases 和同名匹配）
        return self._build_arguments_fallback_simple(subtask, state, result, tool_def)

    def _build_arguments_fallback_simple(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        existing_args: Dict[str, Any],
        tool_def: Any = None,
    ) -> Dict[str, Any]:
        """
        简单的 fallback 参数构造（不硬编码工具名）
        
        优先级：
        1. existing_args（已有参数）
        2. param_aliases（工具定义的别名映射）
        3. 同名匹配（state 中与参数同名的字段）
        4. inputs 中的通用参数
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
                
                # 1. 尝试 param_aliases
                if tool_def.param_aliases and param_name in tool_def.param_aliases:
                    aliases = tool_def.param_aliases[param_name]
                    alias_list = aliases if isinstance(aliases, list) else [aliases]
                    found = False
                    for alias in alias_list:
                        # 先尝试直接从 state 获取
                        if alias in state and state[alias] is not None:
                            result[param_name] = state[alias]
                            found = True
                            break
                        # 再尝试嵌套路径
                        value = self._get_nested_value(state, alias)
                        if value is not None:
                            result[param_name] = value
                            found = True
                            break
                    if found:
                        continue
                
                # 2. 尝试同名匹配
                if param_name in state:
                    result[param_name] = state[param_name]
                    continue
                
                # 3. 尝试从 inputs 获取
                if "inputs" in state and param_name in state["inputs"]:
                    result[param_name] = state["inputs"][param_name]
        
        return result

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

    def _compress_state_for_llm(self, state: Dict[str, Any], max_chars: int = 4000) -> str:
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
