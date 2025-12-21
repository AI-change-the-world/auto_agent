"""
参数构造模块

负责工具参数的构造、绑定解析、LLM 推理和验证。
"""

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from auto_agent.core.executor.state import compress_state_for_llm, get_nested_value
from auto_agent.models import (
    BindingFallbackPolicy,
    BindingPlan,
    BindingSourceType,
    ParameterBinding,
    PlanStep,
    StepBindings,
)

if TYPE_CHECKING:
    from auto_agent.core.context import ExecutionContext
    from auto_agent.llm.client import LLMClient


class ParameterBuilder:
    """
    参数构造器

    负责：
    1. 绑定解析（从 BindingPlan 解析参数）
    2. LLM 推理（fallback 时使用 LLM 构造参数）
    3. 参数验证和修正
    """

    def __init__(
        self,
        llm_client: Optional["LLMClient"] = None,
        binding_plan: Optional[BindingPlan] = None,
        step_outputs: Optional[Dict[str, Any]] = None,
        context: Optional["ExecutionContext"] = None,
        tool_registry: Any = None,
    ):
        self.llm_client = llm_client
        self.binding_plan = binding_plan
        self.step_outputs = step_outputs or {}
        self.context = context
        self.tool_registry = tool_registry
        # LLM 构参缓存：避免重试/重复步骤导致的重复调用
        # key: (step_id, tool_name, missing_params_tuple, state_fingerprint)
        self._llm_args_cache: Dict[tuple, Dict[str, Any]] = {}

    def update_step_output(self, step_id: str, output: Any) -> None:
        """更新步骤输出缓存"""
        self.step_outputs[step_id] = output

    # ==================== 绑定解析 ====================

    async def resolve_bindings_with_trace(
        self,
        step_bindings: StepBindings,
        state: Dict[str, Any],
        existing_args: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str], List[Dict[str, Any]]]:
        """
        解析步骤的参数绑定（带详细 tracing）

        Args:
            step_bindings: 步骤绑定配置
            state: 当前状态
            existing_args: 已有的参数

        Returns:
            (resolved_args, fallback_params, binding_details):
            - resolved_args: 解析后的参数
            - fallback_params: 需要 fallback 的参数名列表
            - binding_details: 每个参数的绑定详情（用于 tracing）
        """
        import time

        from auto_agent.tracing import BindingAction, trace_binding_event

        start_time = time.time()
        resolved = {}
        fallback_params = []
        binding_details = []
        threshold = self.binding_plan.confidence_threshold if self.binding_plan else 0.7

        for param_name, binding in step_bindings.bindings.items():
            detail = {
                "param": param_name,
                "source": binding.source,
                "source_type": binding.source_type.value,
                "confidence": binding.confidence,
                "threshold": threshold,
                "reasoning": binding.reasoning,
                "fallback": binding.fallback.value
                if hasattr(binding, "fallback")
                else "llm_infer",
            }

            # 跳过已有值的参数
            if param_name in existing_args and existing_args[param_name] is not None:
                detail["status"] = "skipped"
                detail["reason"] = "already_has_value"
                detail["existing_value_type"] = type(existing_args[param_name]).__name__
                binding_details.append(detail)
                continue

            # 检查置信度
            if binding.confidence < threshold:
                # ERROR 策略：不允许走 LLM fallback，但仍可尝试直接解析；解析失败则报错
                if (
                    getattr(binding, "fallback", BindingFallbackPolicy.LLM_INFER)
                    == BindingFallbackPolicy.ERROR
                ):
                    value, success, resolve_detail = (
                        self._resolve_single_binding_with_trace(binding, state)
                    )
                    detail.update(resolve_detail)
                    if success:
                        detail["status"] = "resolved_low_confidence"
                        detail["reason"] = (
                            f"resolved_under_low_confidence ({binding.confidence:.2f} < {threshold})"
                        )
                        detail["confidence_gap"] = threshold - binding.confidence
                        detail["value_type"] = type(value).__name__
                        detail["value_preview"] = self._get_value_preview(value)
                        resolved[param_name] = value
                        binding_details.append(detail)
                        continue

                    detail["status"] = "error"
                    detail["reason"] = resolve_detail.get(
                        "error", f"low_confidence_and_resolve_failed ({binding.confidence:.2f} < {threshold})"
                    )
                    binding_details.append(detail)
                    raise ValueError(
                        f"Parameter binding ERROR: cannot resolve {step_bindings.tool}.{param_name}"
                    )

                # 如果配置了 USE_DEFAULT 且有默认值，直接使用默认值，无需再调用 LLM
                if (
                    getattr(binding, "fallback", BindingFallbackPolicy.LLM_INFER)
                    == BindingFallbackPolicy.USE_DEFAULT
                    and binding.default_value is not None
                ):
                    detail["status"] = "resolved_default"
                    detail["reason"] = (
                        f"low_confidence_use_default ({binding.confidence:.2f} < {threshold})"
                    )
                    detail["confidence_gap"] = threshold - binding.confidence
                    detail["value_type"] = type(binding.default_value).__name__
                    detail["value_preview"] = self._get_value_preview(
                        binding.default_value
                    )
                    resolved[param_name] = binding.default_value
                    binding_details.append(detail)
                    continue

                detail["status"] = "fallback"
                detail["reason"] = (
                    f"low_confidence ({binding.confidence:.2f} < {threshold})"
                )
                detail["confidence_gap"] = threshold - binding.confidence
                fallback_params.append(param_name)
                binding_details.append(detail)
                continue

            # 根据来源类型解析值
            value, success, resolve_detail = self._resolve_single_binding_with_trace(
                binding, state
            )

            detail.update(resolve_detail)

            if success:
                detail["status"] = "resolved"
                detail["value_type"] = type(value).__name__
                detail["value_preview"] = self._get_value_preview(value)
                resolved[param_name] = value
            else:
                # 如果解析失败但允许使用默认值，则直接使用默认值
                if (
                    getattr(binding, "fallback", BindingFallbackPolicy.LLM_INFER)
                    == BindingFallbackPolicy.USE_DEFAULT
                    and binding.default_value is not None
                ):
                    detail["status"] = "resolved_default"
                    detail["reason"] = resolve_detail.get(
                        "error", "resolve_failed_use_default"
                    )
                    detail["value_type"] = type(binding.default_value).__name__
                    detail["value_preview"] = self._get_value_preview(
                        binding.default_value
                    )
                    resolved[param_name] = binding.default_value
                elif (
                    getattr(binding, "fallback", BindingFallbackPolicy.LLM_INFER)
                    == BindingFallbackPolicy.ERROR
                ):
                    detail["status"] = "error"
                    detail["reason"] = resolve_detail.get("error", "resolve_failed_error_policy")
                    binding_details.append(detail)
                    raise ValueError(
                        f"Parameter binding ERROR: cannot resolve {step_bindings.tool}.{param_name}"
                    )
                else:
                    detail["status"] = "fallback"
                    detail["reason"] = resolve_detail.get("error", "resolve_failed")
                    fallback_params.append(param_name)

            binding_details.append(detail)

        # 记录绑定解析事件
        duration_ms = (time.time() - start_time) * 1000
        trace_binding_event(
            action=BindingAction.RESOLVE,
            step_id=step_bindings.step_id,
            tool_name=step_bindings.tool,
            bindings_count=len(step_bindings.bindings),
            resolved_count=len(resolved),
            fallback_count=len(fallback_params),
            confidence_threshold=threshold,
            binding_details=binding_details,
            duration_ms=duration_ms,
            skipped_count=len(
                [d for d in binding_details if d.get("status") == "skipped"]
            ),
        )

        return resolved, fallback_params, binding_details

    def _resolve_single_binding_with_trace(
        self,
        binding: ParameterBinding,
        state: Dict[str, Any],
    ) -> Tuple[Any, bool, Dict[str, Any]]:
        """
        解析单个参数绑定（带详细 tracing）

        Args:
            binding: 参数绑定配置
            state: 当前状态

        Returns:
            (value, success, detail): 解析的值、是否成功、详细信息
        """
        detail = {}

        try:
            if binding.source_type == BindingSourceType.USER_INPUT:
                # 从 state.inputs 获取
                inputs = state.get("inputs", {})
                value = inputs.get(binding.source)
                detail["resolve_path"] = f"state.inputs.{binding.source}"
                detail["found"] = value is not None
                return value, value is not None, detail

            elif binding.source_type == BindingSourceType.STEP_OUTPUT:
                # 解析 "step_1.output.field" 格式
                value, success = self._resolve_step_output_binding(
                    binding.source, state
                )
                detail["resolve_path"] = binding.source
                detail["found"] = success
                if not success:
                    # 检查步骤输出是否存在
                    parts = binding.source.split(".")
                    if len(parts) >= 2:
                        step_id = parts[0].replace("step_", "")
                        step_in_cache = step_id in self.step_outputs
                        step_in_state = "steps" in state and step_id in state.get(
                            "steps", {}
                        )

                        if not step_in_cache and not step_in_state:
                            detail["error"] = f"step_{step_id} output not found"
                        else:
                            field_path = ".".join(parts[2:]) if len(parts) > 2 else ""
                            detail["error"] = (
                                f"field '{field_path}' not found in step_{step_id}"
                            )
                return value, success, detail

            elif binding.source_type == BindingSourceType.STATE:
                # 从 state 获取
                value = get_nested_value(state, binding.source)
                detail["resolve_path"] = f"state.{binding.source}"
                detail["found"] = value is not None
                return value, value is not None, detail

            elif binding.source_type == BindingSourceType.LITERAL:
                # 使用字面量值
                detail["resolve_path"] = "literal"
                # default_value 为空时认为无法解析，交给 fallback 策略处理
                if binding.default_value is None:
                    detail["found"] = False
                    detail["error"] = "literal_default_value_missing"
                    return None, False, detail
                detail["found"] = True
                return binding.default_value, True, detail

            elif binding.source_type == BindingSourceType.GENERATED:
                # 需要运行时生成，返回失败触发 fallback
                detail["resolve_path"] = "generated"
                detail["found"] = False
                detail["error"] = "requires_llm_generation"
                return None, False, detail

            else:
                detail["error"] = f"unknown_source_type: {binding.source_type}"
                return None, False, detail

        except Exception as e:
            detail["error"] = str(e)
            return None, False, detail

    def _resolve_step_output_binding(
        self,
        source: str,
        state: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, bool]:
        """
        解析步骤输出绑定

        支持两种数据源（按优先级）：
        1. self.step_outputs（执行时缓存，优先）
        2. state["steps"][step_id]["output"]（持久化状态）

        Args:
            source: 来源路径，格式如 "step_1.output.endpoints"
            state: 状态字典（可选）

        Returns:
            (value, success)
        """
        parts = source.split(".")
        if len(parts) < 2:
            return None, False

        step_id = parts[0].replace("step_", "")

        # 处理 "step_1.output.xxx" 格式
        if len(parts) >= 3 and parts[1] == "output":
            field_path = ".".join(parts[2:])
        # 处理 "step_1.xxx" 格式（简化写法）
        elif len(parts) >= 2:
            field_path = ".".join(parts[1:])
        else:
            field_path = ""

        # 优先从 step_outputs 获取（执行时缓存）
        step_output = self.step_outputs.get(step_id)

        # 如果缓存没有，尝试从 state["steps"] 获取
        if step_output is None and state:
            steps = state.get("steps", {})
            step_data = steps.get(step_id, {})
            step_output = step_data.get("output")

        if step_output is None:
            return None, False

        # 获取字段值
        if field_path:
            value = get_nested_value(step_output, field_path)
        else:
            value = step_output

        return value, value is not None

    def _get_value_preview(self, value: Any, max_length: int = 100) -> str:
        """获取值的预览（用于 tracing）"""
        if value is None:
            return "None"
        if isinstance(value, str):
            if len(value) > max_length:
                return value[:max_length] + "..."
            return value
        if isinstance(value, (list, tuple)):
            return f"[{len(value)} items]"
        if isinstance(value, dict):
            return f"{{{len(value)} keys}}"
        return str(value)[:max_length]

    # ==================== LLM 参数推理 ====================

    async def build_arguments_with_llm(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        tool: Any,
        existing_args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用 LLM 智能构造工具参数

        核心思路：
        1. 基于执行历史的语义描述判断参数关联
        2. 支持多步骤结果合并
        3. LLM 完全自主决策参数映射

        Args:
            subtask: 计划步骤
            state: 当前状态
            tool: 工具实例
            existing_args: 已有的参数

        Returns:
            完整的工具参数字典
        """
        import time

        from auto_agent.tracing import (
            BindingAction,
            trace_binding_event,
            trace_llm_call,
        )

        if not self.llm_client:
            return self._build_arguments_fallback_simple(
                subtask, state, existing_args, tool
            )

        start_time = time.time()
        result = dict(existing_args)
        tool_def = tool.definition

        # 1. 收集参数信息和缺失参数
        params_info = []
        missing_params = []
        required_params = []

        for p in tool_def.parameters:
            param_info = {
                "name": p.name,
                "type": p.type,
                "description": p.description,
                "required": p.required,
            }
            params_info.append(param_info)

            if p.required:
                required_params.append(p.name)
                if p.name not in result or result[p.name] is None:
                    missing_params.append(p.name)

        # 如果所有必需参数都有值了，直接返回
        if not missing_params:
            return result

        # 2. 获取语义化的执行历史
        semantic_history = ""
        if self.context:
            semantic_history = self.context.get_semantic_history_text(max_steps=10)

        # 3. 压缩当前状态
        state_summary = compress_state_for_llm(state)

        # 4. 提取原始用户需求
        original_query = state.get("inputs", {}).get("query", "")

        # 4.5 LLM 构参缓存（同一步骤/同缺失参数/同状态摘要）直接复用
        cache_key = (
            subtask.id,
            subtask.tool or "",
            tuple(missing_params),
            hash(state_summary),
        )
        cached = self._llm_args_cache.get(cache_key)
        if cached:
            result.update(cached)
            return result

        # 5. 构建语义驱动的 prompt
        prompt = f"""你是一个智能参数构造助手。根据执行历史和当前状态，为工具智能构造参数。

【原始用户需求】（最重要！）
{original_query if original_query else "无"}

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
根据原始用户需求、执行历史和当前状态，智能决定缺失参数的值。

关键规则：
1. **最重要**：如果参数名是 "requirements" 或类似需求描述的参数，应该使用【原始用户需求】中的完整内容
2. 仔细阅读每个参数的 description，理解参数的语义用途
3. 查看执行历史中每一步的"目标"和"描述"，判断哪些步骤的输出与当前参数相关
4. 参数可能需要从多个步骤的结果中组合
5. 如果历史步骤的输出类型与参数类型匹配，优先使用
6. 从 state 中找到语义上最匹配的数据

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
                trace_purpose="param_build",
            )

            duration_ms = (time.time() - start_time) * 1000

            # 提取 JSON
            json_match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
            if not json_match:
                json_match = re.search(
                    r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL
                )

            if json_match:
                json_str = (
                    json_match.group(1) if "```" in response else json_match.group()
                )
                new_args = json.loads(json_str)

                # 记录每个参数的来源
                param_sources = []
                for key, value in new_args.items():
                    source_info = {
                        "param": key,
                        "value_type": type(value).__name__,
                        "value_preview": self._get_value_preview(value),
                        "source": "llm_inferred",
                    }

                    # 处理 state 路径引用
                    if isinstance(value, str) and value.startswith("state."):
                        path = value[6:]
                        resolved = get_nested_value(state, path)
                        if resolved is not None:
                            new_args[key] = resolved
                            source_info["source"] = f"state.{path}"
                            source_info["value_type"] = type(resolved).__name__
                            source_info["value_preview"] = self._get_value_preview(
                                resolved
                            )

                    param_sources.append(source_info)

                # 记录 LLM 调用详情
                trace_llm_call(
                    purpose="param_build",
                    prompt=prompt,
                    response=response,
                    success=True,
                    duration_ms=duration_ms,
                    metadata={
                        "step_id": subtask.id,
                        "tool": subtask.tool,
                        "missing_params": missing_params,
                        "resolved_params": list(new_args.keys()),
                        "param_sources": param_sources,
                    },
                )

                # 记录 fallback 绑定事件
                trace_binding_event(
                    action=BindingAction.FALLBACK,
                    step_id=subtask.id,
                    tool_name=subtask.tool,
                    bindings_count=len(missing_params),
                    resolved_count=len(new_args),
                    fallback_count=len(missing_params) - len(new_args),
                    confidence_threshold=0.0,  # LLM fallback 没有置信度
                    binding_details=param_sources,
                    duration_ms=duration_ms,
                    fallback_reason="binding_plan_fallback",
                )

                result.update(new_args)
                # 写入缓存（仅缓存“补充的参数”）
                self._llm_args_cache[cache_key] = dict(new_args)
                return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # 记录失败的 LLM 调用
            trace_llm_call(
                purpose="param_build",
                prompt=prompt,
                response="",
                success=False,
                error=str(e),
                duration_ms=duration_ms,
                metadata={
                    "step_id": subtask.id,
                    "tool": subtask.tool,
                    "missing_params": missing_params,
                },
            )

        # Fallback
        return self._build_arguments_fallback_simple(subtask, state, result, tool)

    def _build_arguments_fallback_simple(
        self,
        subtask: PlanStep,
        state: Dict[str, Any],
        existing_args: Dict[str, Any],
        tool: Any = None,
    ) -> Dict[str, Any]:
        """
        简单的 fallback 参数构造（当 LLM 不可用时使用）

        优先级：
        1. existing_args（已有参数）
        2. 从执行历史中按语义匹配
        3. 同名匹配（state 中与参数同名的字段）
        4. inputs 中的通用参数
        """
        result = dict(existing_args)
        tool_def = tool.definition if tool else None

        if tool_def:
            # 0. param_aliases（无 LLM 时也尽量用 state 映射补齐）
            if getattr(tool_def, "param_aliases", None):
                for param_name, state_path in tool_def.param_aliases.items():
                    if param_name in result and result[param_name] is not None:
                        continue
                    if not state_path:
                        continue
                    value = None
                    if isinstance(state_path, str):
                        if state_path.startswith("state."):
                            value = get_nested_value(state, state_path[6:])
                        else:
                            value = (
                                get_nested_value(state, state_path)
                                if "." in state_path
                                else state.get(state_path)
                            )
                    if value is not None:
                        result[param_name] = value

            for param in tool_def.parameters:
                param_name = param.name
                if param_name in result and result[param_name] is not None:
                    continue

                # 0.5 required 参数的 schema 默认值
                if param.required and param.default is not None:
                    result[param_name] = param.default
                    continue

                # 1. 尝试从执行历史中按类型匹配
                if self.context and self.context.history:
                    value = self._match_from_history(
                        param_name, param.type, param.description
                    )
                    if value is not None:
                        result[param_name] = value
                        continue

                # 2. 尝试同名匹配
                if param_name in state:
                    result[param_name] = state[param_name]
                    continue

                # 3. 尝试从 inputs 获取
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

    # ==================== 参数验证 ====================

    def validate_parameters(
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
        - custom: 自定义验证

        Args:
            arguments: 要验证的参数字典
            tool: 工具实例

        Returns:
            (is_valid, error_messages): 验证是否通过，以及错误消息列表
        """
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

            if param_name not in arguments:
                continue

            param_value = arguments[param_name]

            if param_value is None:
                continue

            is_valid = True

            if validation_type == "regex":
                try:
                    if not isinstance(param_value, str):
                        param_value = str(param_value)
                    if not re.match(validation_rule, param_value):
                        is_valid = False
                except re.error:
                    continue

            elif validation_type == "range":
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
                        num_value = float(param_value)
                        if num_value < min_val or num_value > max_val:
                            is_valid = False
                except (ValueError, TypeError):
                    is_valid = False

            elif validation_type == "enum":
                allowed_values = [v.strip() for v in validation_rule.split(",")]
                str_value = str(param_value)
                if str_value not in allowed_values:
                    is_valid = False

            elif validation_type == "custom":
                if (
                    hasattr(tool_def, "validate_function")
                    and tool_def.validate_function
                ):
                    try:
                        validate_fn = tool_def.validate_function
                        if callable(validate_fn):
                            result = validate_fn(param_name, param_value, arguments)
                            if asyncio.iscoroutine(result):
                                continue
                            is_valid = bool(result)
                    except Exception:
                        continue

            if not is_valid:
                errors.append(f"参数 '{param_name}' 验证失败: {error_message}")

        return len(errors) == 0, errors

    async def validate_and_fix_parameters(
        self,
        arguments: Dict[str, Any],
        tool: Any,
        state: Dict[str, Any],
        subtask: PlanStep,
    ) -> Dict[str, Any]:
        """
        验证参数并在失败时尝试修正

        Args:
            arguments: 要验证的参数字典
            tool: 工具实例
            state: 当前状态
            subtask: 计划步骤

        Returns:
            验证通过或修正后的参数字典
        """
        import time

        from auto_agent.tracing import trace_flow_event, trace_llm_call

        max_fix_attempts = 2

        for attempt in range(max_fix_attempts):
            is_valid, errors = self.validate_parameters(arguments, tool)

            if is_valid:
                return arguments

            if not self.llm_client:
                return arguments

            start_time = time.time()

            # 尝试使用 LLM 修正参数
            tool_def = tool.definition

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
{compress_state_for_llm(state)}

【任务】
根据验证规则修正参数值，确保参数能通过验证。

请返回修正后的完整参数 JSON：
```json
{{"param_name": "corrected_value", ...}}
```"""

            try:
                response = await self.llm_client.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1,
                    trace_purpose="param_fix",
                )

                duration_ms = (time.time() - start_time) * 1000

                json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
                if json_match:
                    fixed_args = json.loads(json_match.group())

                    # 记录修正详情
                    fix_details = []
                    for key, new_value in fixed_args.items():
                        old_value = arguments.get(key)
                        if old_value != new_value:
                            fix_details.append(
                                {
                                    "param": key,
                                    "old_value": self._get_value_preview(old_value),
                                    "new_value": self._get_value_preview(new_value),
                                    "old_type": type(old_value).__name__
                                    if old_value
                                    else "None",
                                    "new_type": type(new_value).__name__,
                                }
                            )

                    # 记录 LLM 调用
                    trace_llm_call(
                        purpose="param_fix",
                        prompt=prompt,
                        response=response,
                        success=True,
                        duration_ms=duration_ms,
                        metadata={
                            "step_id": subtask.id,
                            "tool": subtask.tool,
                            "attempt": attempt + 1,
                            "max_attempts": max_fix_attempts,
                            "validation_errors": errors,
                            "fix_details": fix_details,
                            "fixed_params": list(fixed_args.keys()),
                        },
                    )

                    # 记录流程事件
                    if fix_details:
                        trace_flow_event(
                            action="fallback",
                            reason=f"参数验证失败，LLM 修正 {len(fix_details)} 个参数",
                            from_step=subtask.id,
                            attempt=attempt + 1,
                            max_attempts=max_fix_attempts,
                            validation_errors=errors,
                            fix_details=fix_details,
                        )

                    arguments.update(fixed_args)

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000

                # 记录失败的 LLM 调用
                trace_llm_call(
                    purpose="param_fix",
                    prompt=prompt,
                    response="",
                    success=False,
                    error=str(e),
                    duration_ms=duration_ms,
                    metadata={
                        "step_id": subtask.id,
                        "tool": subtask.tool,
                        "attempt": attempt + 1,
                        "validation_errors": errors,
                    },
                )

                return arguments

        return arguments
