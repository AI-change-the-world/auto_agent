"""
重试控制器
"""

import asyncio
import json
import traceback
from typing import Any, Callable, Dict, List, Optional

from auto_agent.llm.client import LLMClient
from auto_agent.models import ToolDefinition
from auto_agent.retry.models import (
    ErrorAnalysis,
    ErrorRecoveryRecord,
    ErrorType,
    ParameterFix,
    RetryConfig,
    RetryStrategy,
)
from auto_agent.retry.strategies import (
    exponential_backoff_delay,
    immediate_delay,
    linear_backoff_delay,
)


class RetryController:
    """
    重试控制器

    支持多种重试策略和智能错误分析
    """

    def __init__(
        self, config: RetryConfig, llm_client: Optional[LLMClient] = None
    ):
        self.config = config
        self.llm_client = llm_client

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs,
    ) -> Any:
        """
        带重试的执行

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果

        Raises:
            最后一次失败的异常
        """
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                # 执行函数
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return result

            except Exception as e:
                last_exception = e

                # 判断是否应该重试
                if not await self.should_retry(e, attempt, {}):
                    raise

                # 如果是最后一次尝试，直接抛出异常
                if attempt >= self.config.max_retries:
                    raise

                # 计算延迟时间
                delay = self.get_delay(attempt)
                await asyncio.sleep(delay)

        # 理论上不应该到达这里
        if last_exception:
            raise last_exception

    async def should_retry(
        self,
        exception: Exception,
        attempt: int,
        context: Dict[str, Any],
    ) -> bool:
        """
        判断是否应该重试

        Args:
            exception: 异常对象
            attempt: 当前尝试次数
            context: 上下文信息

        Returns:
            是否应该重试
        """
        # 检查是否达到最大重试次数
        if attempt >= self.config.max_retries:
            return False

        # 检查异常类型
        if self.config.retry_on_exceptions:
            if not any(
                isinstance(exception, exc_type)
                for exc_type in self.config.retry_on_exceptions
            ):
                return False

        # 如果有自定义回调，使用回调判断
        if self.config.should_retry_callback:
            return self.config.should_retry_callback(exception, attempt, context)

        # 默认重试
        return True

    async def analyze_error(
        self,
        exception: Exception,
        context: Dict[str, Any],
        tool_definition: Optional[ToolDefinition] = None,
        memory_system: Optional[Any] = None,
        user_id: str = "default",
    ) -> ErrorAnalysis:
        """
        使用 LLM 智能分析错误

        分析优先级：
        1. 先查询记忆系统中的历史恢复策略
        2. 如果有匹配的历史策略，直接使用
        3. 如果没有历史策略，使用 LLM 进行深度分析
        4. 如果 LLM 不可用，使用基于规则的 fallback 分析

        Args:
            exception: 异常对象
            context: 执行上下文（包含 state、tool_args 等）
            tool_definition: 工具定义（可选，用于理解参数要求）
            memory_system: 记忆系统实例（可选，用于查询历史策略）
            user_id: 用户 ID（默认 "default"）

        Returns:
            ErrorAnalysis: 包含错误类型、可恢复性、修正建议等的分析结果
        """
        # 1. 优先查询记忆系统中的历史恢复策略
        tool_name = tool_definition.name if tool_definition else None
        historical_analysis = await self._query_historical_recovery(
            exception=exception,
            tool_name=tool_name,
            memory_system=memory_system,
            user_id=user_id,
        )
        
        if historical_analysis:
            # 有匹配的历史策略，直接使用
            return historical_analysis

        # 2. 如果没有 LLM 客户端，使用 fallback 分析
        if not self.llm_client:
            return self._fallback_error_analysis(exception)

        try:
            # 3. 构建分析 prompt
            prompt = self._build_error_analysis_prompt(
                exception, context, tool_definition
            )

            # 调用 LLM 分析
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # 使用较低温度以获得更一致的分析结果
            )

            # 解析分析结果
            return self._parse_error_analysis(response, exception)

        except Exception as llm_error:
            # 4. LLM 调用失败时，使用 fallback 分析
            fallback_result = self._fallback_error_analysis(exception)
            fallback_result.reasoning = (
                f"LLM 分析失败 ({type(llm_error).__name__}: {str(llm_error)}), "
                f"使用规则匹配 fallback: {fallback_result.reasoning}"
            )
            return fallback_result

    async def suggest_parameter_fixes(
        self,
        failed_params: Dict[str, Any],
        error_analysis: ErrorAnalysis,
        context: Dict[str, Any],
        tool_definition: Optional[ToolDefinition] = None,
    ) -> Dict[str, Any]:
        """
        基于错误分析建议参数修正
        
        当错误类型为 PARAMETER_ERROR 时，使用 LLM 推断正确的参数值。
        如果 LLM 不可用或调用失败，则尝试使用错误分析中已有的修正建议。
        
        Args:
            failed_params: 失败的参数字典
            error_analysis: 错误分析结果
            context: 执行上下文（包含 state 等可用信息）
            tool_definition: 工具定义（可选，用于理解参数要求）
            
        Returns:
            Dict[str, Any]: 修正后的参数字典
        """
        # 如果不是参数错误，直接返回原参数
        if error_analysis.error_type != ErrorType.PARAMETER_ERROR:
            return failed_params
        
        # 如果没有 LLM 客户端，尝试使用已有的修正建议
        if not self.llm_client:
            return self._apply_existing_fixes(failed_params, error_analysis)
        
        try:
            # 构建参数修正 prompt
            prompt = self._build_parameter_fix_prompt(
                failed_params, error_analysis, context, tool_definition
            )
            
            # 调用 LLM 获取修正建议
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,  # 使用较低温度以获得更确定的修正结果
            )
            
            # 解析修正结果
            return self._parse_parameter_fix_response(response, failed_params)
            
        except Exception as llm_error:
            # LLM 调用失败时，尝试使用已有的修正建议
            return self._apply_existing_fixes(failed_params, error_analysis)

    async def record_successful_recovery(
        self,
        original_error: Exception,
        tool_name: str,
        original_params: Dict[str, Any],
        fixed_params: Dict[str, Any],
        memory_system: Optional[Any] = None,
        user_id: str = "default",
    ) -> Optional[ErrorRecoveryRecord]:
        """
        记录成功的错误恢复策略到记忆系统
        
        将有效的修正策略记录到 L2 语义记忆中，供后续类似错误时参考。
        
        Args:
            original_error: 原始异常对象
            tool_name: 工具名称
            original_params: 原始参数
            fixed_params: 修正后的参数
            memory_system: 记忆系统实例（可选）
            user_id: 用户 ID（默认 "default"）
            
        Returns:
            ErrorRecoveryRecord: 创建的恢复记录，如果记忆系统不可用则返回 None
        """
        import time
        from auto_agent.memory.models import MemoryCategory, MemorySource
        
        # 创建恢复记录
        record = ErrorRecoveryRecord(
            error_type=type(original_error).__name__,
            error_message=str(original_error),
            tool_name=tool_name,
            original_params=original_params,
            fixed_params=fixed_params,
            recovery_successful=True,
            timestamp=time.time(),
        )
        
        # 如果有记忆系统，记录到 L2 语义记忆
        if memory_system:
            try:
                # 构建记忆内容摘要
                content = self._build_recovery_memory_content(record)
                
                # 构建详细内容（用于 Markdown）
                detail_content = self._build_recovery_detail_content(record)
                
                # 添加到语义记忆
                memory_system.semantic.add(
                    user_id=user_id,
                    content=content,
                    category=MemoryCategory.STRATEGY,
                    subcategory="error_recovery",
                    tags=[
                        "error_recovery",
                        f"tool:{tool_name}",
                        f"error:{record.error_type}",
                    ],
                    source=MemorySource.TASK_RESULT,
                    confidence=0.7,  # 成功恢复的策略有较高置信度
                    metadata=record.to_memory_content(),
                    detail_content=detail_content,
                )
            except Exception as e:
                # 记忆系统错误不应影响主流程
                pass
        
        return record

    def _build_recovery_memory_content(self, record: ErrorRecoveryRecord) -> str:
        """
        构建恢复策略的记忆摘要内容
        
        Args:
            record: 错误恢复记录
            
        Returns:
            str: 简短的记忆摘要
        """
        # 找出被修正的参数
        changed_params = []
        for key in record.fixed_params:
            if key in record.original_params:
                if record.original_params[key] != record.fixed_params[key]:
                    changed_params.append(key)
            else:
                changed_params.append(key)
        
        params_str = ", ".join(changed_params) if changed_params else "参数"
        
        return (
            f"工具 {record.tool_name} 遇到 {record.error_type} 错误时，"
            f"通过修正 {params_str} 成功恢复"
        )

    def _build_recovery_detail_content(self, record: ErrorRecoveryRecord) -> str:
        """
        构建恢复策略的详细 Markdown 内容
        
        Args:
            record: 错误恢复记录
            
        Returns:
            str: 详细的 Markdown 内容
        """
        import json
        
        lines = [
            f"# 错误恢复策略: {record.tool_name}",
            "",
            "## 错误信息",
            f"- **错误类型**: {record.error_type}",
            f"- **错误消息**: {record.error_message}",
            "",
            "## 原始参数",
            "```json",
            json.dumps(record.original_params, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "## 修正后参数",
            "```json",
            json.dumps(record.fixed_params, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "## 修正说明",
        ]
        
        # 找出具体的修正
        for key in record.fixed_params:
            original = record.original_params.get(key, "<未设置>")
            fixed = record.fixed_params[key]
            if original != fixed:
                lines.append(f"- `{key}`: `{original}` → `{fixed}`")
        
        return "\n".join(lines)

    async def _query_historical_recovery(
        self,
        exception: Exception,
        tool_name: Optional[str] = None,
        memory_system: Optional[Any] = None,
        user_id: str = "default",
    ) -> Optional[ErrorAnalysis]:
        """
        查询记忆系统中类似错误的历史恢复策略
        
        按成功率和使用次数排序，返回最匹配的历史恢复策略。
        
        Args:
            exception: 当前异常对象
            tool_name: 工具名称（可选，用于更精确匹配）
            memory_system: 记忆系统实例
            user_id: 用户 ID
            
        Returns:
            ErrorAnalysis: 基于历史策略的错误分析，如果没有匹配则返回 None
        """
        if not memory_system:
            return None
        
        try:
            from auto_agent.memory.models import MemoryCategory
            
            error_type = type(exception).__name__
            error_message = str(exception).lower()
            
            # 构建搜索查询
            search_query = f"error_recovery {error_type}"
            if tool_name:
                search_query += f" {tool_name}"
            
            # 搜索相关的恢复策略记忆
            memories = memory_system.semantic.search(
                user_id=user_id,
                query=search_query,
                category=MemoryCategory.STRATEGY,
                limit=10,
            )
            
            # 过滤出错误恢复相关的记忆
            recovery_memories = []
            for mem in memories:
                if "error_recovery" in mem.tags:
                    # 计算匹配分数
                    match_score = self._calculate_recovery_match_score(
                        mem, error_type, tool_name, error_message
                    )
                    if match_score > 0:
                        recovery_memories.append((match_score, mem))
            
            if not recovery_memories:
                return None
            
            # 按匹配分数排序（综合考虑匹配度、置信度和访问次数）
            recovery_memories.sort(
                key=lambda x: (
                    x[0],  # 匹配分数
                    x[1].confidence,  # 置信度
                    x[1].access_count,  # 使用次数
                ),
                reverse=True,
            )
            
            # 获取最佳匹配
            best_match = recovery_memories[0][1]
            
            # 从记忆元数据中提取恢复策略
            return self._build_analysis_from_memory(best_match, exception)
            
        except Exception as e:
            # 查询失败不应影响主流程
            return None

    def _calculate_recovery_match_score(
        self,
        memory: Any,
        error_type: str,
        tool_name: Optional[str],
        error_message: str,
    ) -> float:
        """
        计算恢复策略记忆的匹配分数
        
        Args:
            memory: 记忆条目
            error_type: 错误类型名称
            tool_name: 工具名称
            error_message: 错误消息
            
        Returns:
            float: 匹配分数 (0.0-1.0)
        """
        score = 0.0
        
        # 检查标签匹配
        tags = memory.tags or []
        
        # 错误类型匹配（权重最高）
        if f"error:{error_type}" in tags:
            score += 0.5
        
        # 工具名称匹配
        if tool_name and f"tool:{tool_name}" in tags:
            score += 0.3
        
        # 检查元数据中的错误消息相似度
        metadata = memory.metadata or {}
        stored_error_msg = str(metadata.get("error_message", "")).lower()
        if stored_error_msg:
            # 简单的关键词匹配
            error_words = set(error_message.split())
            stored_words = set(stored_error_msg.split())
            if error_words and stored_words:
                overlap = len(error_words & stored_words)
                similarity = overlap / max(len(error_words), len(stored_words))
                score += similarity * 0.2
        
        return score

    def _build_analysis_from_memory(
        self,
        memory: Any,
        exception: Exception,
    ) -> ErrorAnalysis:
        """
        从历史记忆构建错误分析结果
        
        Args:
            memory: 记忆条目
            exception: 当前异常
            
        Returns:
            ErrorAnalysis: 基于历史策略的错误分析
        """
        metadata = memory.metadata or {}
        fix_pattern = metadata.get("fix_pattern", {})
        original_params = fix_pattern.get("original", {})
        fixed_params = fix_pattern.get("fixed", {})
        
        # 构建参数修正建议
        suggested_fixes = []
        for key in fixed_params:
            original_value = original_params.get(key)
            fixed_value = fixed_params[key]
            if original_value != fixed_value:
                suggested_fixes.append(
                    ParameterFix(
                        parameter_name=key,
                        current_value=original_value,
                        suggested_value=fixed_value,
                        fix_reason=f"基于历史成功恢复策略 (记忆ID: {memory.memory_id})",
                        confidence=memory.confidence,
                    )
                )
        
        # 确定错误类型
        stored_error_type = metadata.get("error_type", "")
        try:
            error_type = ErrorType(stored_error_type.lower().replace(" ", "_"))
        except ValueError:
            # 尝试从异常类型推断
            error_type = self._infer_error_type_from_exception(exception)
        
        return ErrorAnalysis(
            error_type=error_type,
            is_recoverable=True,  # 历史上成功恢复过
            root_cause=f"历史记录显示此类错误可通过参数修正恢复 (来源: {memory.content})",
            suggested_fixes=suggested_fixes,
            retry_strategy="immediate",  # 有历史策略时立即重试
            confidence=memory.confidence,
            reasoning=f"使用历史恢复策略 (记忆ID: {memory.memory_id}, 访问次数: {memory.access_count})",
        )

    def _infer_error_type_from_exception(self, exception: Exception) -> ErrorType:
        """
        从异常类型推断 ErrorType
        
        Args:
            exception: 异常对象
            
        Returns:
            ErrorType: 推断的错误类型
        """
        exception_type = type(exception).__name__.lower()
        
        if "timeout" in exception_type:
            return ErrorType.TIMEOUT_ERROR
        elif "connection" in exception_type or "network" in exception_type:
            return ErrorType.NETWORK_ERROR
        elif "permission" in exception_type or "auth" in exception_type:
            return ErrorType.PERMISSION_ERROR
        elif "value" in exception_type or "type" in exception_type:
            return ErrorType.PARAMETER_ERROR
        else:
            return ErrorType.UNKNOWN_ERROR

    def _apply_existing_fixes(
        self,
        failed_params: Dict[str, Any],
        error_analysis: ErrorAnalysis,
    ) -> Dict[str, Any]:
        """
        应用错误分析中已有的修正建议
        
        当 LLM 不可用时的 fallback 方案。
        
        Args:
            failed_params: 失败的参数字典
            error_analysis: 错误分析结果
            
        Returns:
            Dict[str, Any]: 应用修正后的参数字典
        """
        if not error_analysis.suggested_fixes:
            return failed_params
        
        # 复制参数字典
        fixed_params = dict(failed_params)
        
        # 应用每个修正建议
        for fix in error_analysis.suggested_fixes:
            if fix.parameter_name and fix.suggested_value is not None:
                # 只应用置信度较高的修正
                if fix.confidence >= 0.5:
                    fixed_params[fix.parameter_name] = fix.suggested_value
        
        return fixed_params

    def _parse_parameter_fix_response(
        self,
        llm_response: str,
        failed_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        解析 LLM 返回的参数修正结果
        
        Args:
            llm_response: LLM 返回的响应字符串
            failed_params: 原始失败参数（用于 fallback）
            
        Returns:
            Dict[str, Any]: 修正后的参数字典
        """
        try:
            # 从响应中提取 JSON
            json_str = self._extract_json_from_response(llm_response)
            data = json.loads(json_str)
            
            # 获取修正后的参数
            fixed_params = data.get("fixed_params", {})
            
            # 如果解析成功且有修正参数，返回修正后的参数
            if fixed_params and isinstance(fixed_params, dict):
                # 合并原参数和修正参数，确保不丢失未修正的参数
                result = dict(failed_params)
                result.update(fixed_params)
                return result
            
            # 如果没有 fixed_params，返回原参数
            return failed_params
            
        except (json.JSONDecodeError, KeyError, TypeError):
            # 解析失败时返回原参数
            return failed_params

    def get_delay(self, attempt: int) -> float:
        """
        计算延迟时间

        Args:
            attempt: 当前尝试次数

        Returns:
            延迟时间（秒）
        """
        if self.config.strategy == RetryStrategy.IMMEDIATE:
            return immediate_delay()
        elif self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            return exponential_backoff_delay(
                attempt,
                self.config.base_delay,
                self.config.backoff_factor,
                self.config.max_delay,
            )
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            return linear_backoff_delay(
                attempt, self.config.base_delay, self.config.max_delay
            )
        else:
            return self.config.base_delay

    def _build_error_analysis_prompt(
        self,
        exception: Exception,
        context: Dict[str, Any],
        tool_definition: Optional[ToolDefinition] = None,
    ) -> str:
        """
        构建 LLM 错误分析 prompt

        Args:
            exception: 异常对象
            context: 执行上下文（包含 state、tool_args 等）
            tool_definition: 工具定义（可选，用于理解参数要求）

        Returns:
            str: 构建好的 prompt 字符串
        """
        # 获取异常详细信息
        exception_type = type(exception).__name__
        exception_message = str(exception)
        exception_traceback = traceback.format_exc()

        # 构建工具定义部分
        tool_info = ""
        if tool_definition:
            tool_info = f"""
## 工具定义
- 工具名称: {tool_definition.name}
- 工具描述: {tool_definition.description}
- 参数定义:
{self._format_tool_parameters(tool_definition)}
"""

        # 构建上下文部分
        context_info = ""
        if context:
            # 安全地序列化上下文，避免敏感信息泄露
            safe_context = self._sanitize_context(context)
            context_info = f"""
## 执行上下文
```json
{json.dumps(safe_context, ensure_ascii=False, indent=2, default=str)}
```
"""

        # 构建完整 prompt
        prompt = f"""你是一个专业的错误分析助手。请分析以下工具执行错误，并提供详细的分析结果。

## 错误信息
- 异常类型: {exception_type}
- 错误消息: {exception_message}
- 堆栈跟踪:
```
{exception_traceback}
```
{tool_info}{context_info}
## 错误类型说明
请从以下错误类型中选择最匹配的一个：
- parameter_error: 参数错误（参数格式、类型、范围错误，可通过修正参数恢复）
- network_error: 网络错误（网络超时、连接失败，可通过重试恢复）
- timeout_error: 超时错误（操作超时，可通过重试恢复）
- resource_error: 资源错误（资源不可用、配额超限，需等待或切换资源）
- logic_error: 逻辑错误（业务逻辑错误，需要重规划）
- dependency_error: 依赖错误（依赖未满足，需要解决依赖）
- permission_error: 权限错误（权限不足，通常不可恢复）
- unknown_error: 未知错误

## 输出要求
请以 JSON 格式返回分析结果，包含以下字段：
```json
{{
    "error_type": "错误类型（从上述类型中选择）",
    "is_recoverable": true/false,
    "root_cause": "根本原因分析",
    "suggested_fixes": [
        {{
            "parameter_name": "需要修正的参数名",
            "current_value": "当前值",
            "suggested_value": "建议值",
            "fix_reason": "修正原因",
            "confidence": 0.0-1.0
        }}
    ],
    "retry_strategy": "immediate/exponential_backoff/linear_backoff/null",
    "confidence": 0.0-1.0,
    "reasoning": "推理过程说明"
}}
```

请只返回 JSON，不要包含其他内容。"""

        return prompt

    def _format_tool_parameters(self, tool_definition: ToolDefinition) -> str:
        """格式化工具参数定义为可读字符串"""
        if not tool_definition.parameters:
            return "  无参数"
        
        lines = []
        for param in tool_definition.parameters:
            required_str = "必需" if param.required else "可选"
            default_str = f", 默认值: {param.default}" if param.default is not None else ""
            enum_str = f", 可选值: {param.enum}" if param.enum else ""
            lines.append(
                f"  - {param.name} ({param.type}, {required_str}): {param.description}{default_str}{enum_str}"
            )
        return "\n".join(lines)

    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理上下文，移除敏感信息并限制大小
        
        Args:
            context: 原始上下文
            
        Returns:
            清理后的上下文
        """
        safe_context = {}
        sensitive_keys = {"password", "token", "secret", "api_key", "credential"}
        
        for key, value in context.items():
            # 跳过敏感字段
            if any(s in key.lower() for s in sensitive_keys):
                safe_context[key] = "[REDACTED]"
            elif isinstance(value, dict):
                # 递归处理嵌套字典
                safe_context[key] = self._sanitize_context(value)
            elif isinstance(value, str) and len(value) > 500:
                # 截断过长的字符串
                safe_context[key] = value[:500] + "...[truncated]"
            else:
                safe_context[key] = value
        
        return safe_context

    def _parse_error_analysis(
        self,
        llm_response: str,
        exception: Exception,
    ) -> ErrorAnalysis:
        """
        解析 LLM 返回的 JSON 结果为 ErrorAnalysis 对象

        Args:
            llm_response: LLM 返回的响应字符串
            exception: 原始异常对象（用于 fallback）

        Returns:
            ErrorAnalysis: 解析后的错误分析对象
        """
        try:
            # 尝试从响应中提取 JSON
            json_str = self._extract_json_from_response(llm_response)
            data = json.loads(json_str)

            # 解析错误类型
            error_type_str = data.get("error_type", "unknown_error")
            try:
                error_type = ErrorType(error_type_str)
            except ValueError:
                error_type = ErrorType.UNKNOWN_ERROR

            # 解析参数修正建议
            suggested_fixes = []
            for fix_data in data.get("suggested_fixes", []):
                if isinstance(fix_data, dict):
                    suggested_fixes.append(
                        ParameterFix(
                            parameter_name=fix_data.get("parameter_name", ""),
                            current_value=fix_data.get("current_value"),
                            suggested_value=fix_data.get("suggested_value"),
                            fix_reason=fix_data.get("fix_reason", ""),
                            confidence=float(fix_data.get("confidence", 0.0)),
                        )
                    )

            return ErrorAnalysis(
                error_type=error_type,
                is_recoverable=bool(data.get("is_recoverable", False)),
                root_cause=str(data.get("root_cause", str(exception))),
                suggested_fixes=suggested_fixes,
                retry_strategy=data.get("retry_strategy"),
                confidence=float(data.get("confidence", 0.0)),
                reasoning=str(data.get("reasoning", "")),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # 解析失败时返回基于异常的默认分析
            return ErrorAnalysis(
                error_type=ErrorType.UNKNOWN_ERROR,
                is_recoverable=True,
                root_cause=f"LLM 响应解析失败: {e}. 原始错误: {str(exception)}",
                suggested_fixes=[],
                retry_strategy="exponential_backoff",
                confidence=0.3,
                reasoning="LLM 响应解析失败，使用默认分析",
            )

    def _extract_json_from_response(self, response: str) -> str:
        """
        从 LLM 响应中提取 JSON 字符串
        
        处理可能包含 markdown 代码块或其他文本的响应
        
        Args:
            response: LLM 响应字符串
            
        Returns:
            提取的 JSON 字符串
        """
        response = response.strip()
        
        # 尝试直接解析
        if response.startswith("{"):
            # 找到匹配的结束括号
            brace_count = 0
            for i, char in enumerate(response):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return response[: i + 1]
            return response
        
        # 尝试从 markdown 代码块中提取
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()
        
        # 尝试从普通代码块中提取
        if "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end > start:
                content = response[start:end].strip()
                if content.startswith("{"):
                    return content
        
        # 尝试找到 JSON 对象
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            return response[start:end]
        
        return response

    def _build_parameter_fix_prompt(
        self,
        failed_params: Dict[str, Any],
        error_analysis: ErrorAnalysis,
        context: Dict[str, Any],
        tool_definition: Optional[ToolDefinition] = None,
    ) -> str:
        """
        构建参数修正 prompt
        
        包含失败参数、错误分析结果和可用状态信息，
        用于让 LLM 推断正确的参数值。
        
        Args:
            failed_params: 失败的参数字典
            error_analysis: 错误分析结果
            context: 执行上下文（包含 state 等可用信息）
            tool_definition: 工具定义（可选，用于理解参数要求）
            
        Returns:
            str: 构建好的参数修正 prompt
        """
        # 构建工具定义部分
        tool_info = ""
        if tool_definition:
            tool_info = f"""
## 工具定义
- 工具名称: {tool_definition.name}
- 工具描述: {tool_definition.description}
- 参数定义:
{self._format_tool_parameters(tool_definition)}
"""

        # 构建失败参数部分
        failed_params_str = json.dumps(
            failed_params, ensure_ascii=False, indent=2, default=str
        )

        # 构建错误分析部分
        error_info = f"""
## 错误分析结果
- 错误类型: {error_analysis.error_type.value}
- 根本原因: {error_analysis.root_cause}
- 推理过程: {error_analysis.reasoning}
"""
        
        # 如果已有修正建议，也包含进来
        if error_analysis.suggested_fixes:
            fixes_info = "\n- 已有修正建议:\n"
            for fix in error_analysis.suggested_fixes:
                fixes_info += f"  - {fix.parameter_name}: {fix.current_value} -> {fix.suggested_value} ({fix.fix_reason})\n"
            error_info += fixes_info

        # 构建可用状态部分
        state_info = ""
        if context:
            # 提取 state 信息
            state = context.get("state", {})
            if state:
                safe_state = self._sanitize_context(state)
                state_info = f"""
## 可用执行状态
以下是当前执行状态中可用的数据，可以从中提取正确的参数值：
```json
{json.dumps(safe_state, ensure_ascii=False, indent=2, default=str)}
```
"""
            
            # 提取其他上下文信息
            other_context = {k: v for k, v in context.items() if k != "state"}
            if other_context:
                safe_other = self._sanitize_context(other_context)
                state_info += f"""
## 其他上下文信息
```json
{json.dumps(safe_other, ensure_ascii=False, indent=2, default=str)}
```
"""

        # 构建完整 prompt
        prompt = f"""你是一个专业的参数修正助手。请根据错误分析结果和可用状态，推断正确的参数值。

## 失败的参数
```json
{failed_params_str}
```
{error_info}{tool_info}{state_info}
## 任务要求
1. 分析失败参数与工具定义的不匹配之处
2. 从可用执行状态中查找可能的正确值
3. 根据错误分析结果推断修正方案
4. 对于无法确定的参数，保持原值不变

## 输出要求
请以 JSON 格式返回修正后的完整参数字典：
```json
{{
    "fixed_params": {{
        "参数名1": "修正后的值1",
        "参数名2": "修正后的值2"
    }},
    "fixes_applied": [
        {{
            "parameter_name": "被修正的参数名",
            "original_value": "原始值",
            "fixed_value": "修正后的值",
            "fix_reason": "修正原因",
            "confidence": 0.0-1.0
        }}
    ],
    "reasoning": "整体修正思路说明"
}}
```

请只返回 JSON，不要包含其他内容。"""

        return prompt

    def _fallback_error_analysis(self, exception: Exception) -> ErrorAnalysis:
        """
        当 LLM 不可用时的规则匹配 fallback 分析
        
        基于异常类型名称和消息进行简单分类
        
        Args:
            exception: 异常对象
            
        Returns:
            ErrorAnalysis: 基于规则的错误分析结果
        """
        exception_type = type(exception).__name__.lower()
        exception_message = str(exception).lower()
        
        # 网络相关错误
        network_keywords = [
            "connection", "network", "socket", "dns", "host",
            "refused", "unreachable", "reset", "broken pipe"
        ]
        if any(kw in exception_type or kw in exception_message for kw in network_keywords):
            return ErrorAnalysis(
                error_type=ErrorType.NETWORK_ERROR,
                is_recoverable=True,
                root_cause=f"网络错误: {str(exception)}",
                suggested_fixes=[],
                retry_strategy="exponential_backoff",
                confidence=0.7,
                reasoning="基于异常类型和消息关键词匹配为网络错误",
            )
        
        # 超时相关错误
        timeout_keywords = ["timeout", "timed out", "deadline", "exceeded"]
        if any(kw in exception_type or kw in exception_message for kw in timeout_keywords):
            return ErrorAnalysis(
                error_type=ErrorType.TIMEOUT_ERROR,
                is_recoverable=True,
                root_cause=f"超时错误: {str(exception)}",
                suggested_fixes=[],
                retry_strategy="exponential_backoff",
                confidence=0.7,
                reasoning="基于异常类型和消息关键词匹配为超时错误",
            )
        
        # 参数相关错误
        param_keywords = [
            "parameter", "argument", "invalid", "missing", "required",
            "type", "value", "format", "validation", "typeerror", "valueerror"
        ]
        if any(kw in exception_type or kw in exception_message for kw in param_keywords):
            return ErrorAnalysis(
                error_type=ErrorType.PARAMETER_ERROR,
                is_recoverable=True,
                root_cause=f"参数错误: {str(exception)}",
                suggested_fixes=[],
                retry_strategy="immediate",
                confidence=0.6,
                reasoning="基于异常类型和消息关键词匹配为参数错误",
            )
        
        # 权限相关错误
        permission_keywords = [
            "permission", "denied", "forbidden", "unauthorized",
            "access", "auth", "403", "401"
        ]
        if any(kw in exception_type or kw in exception_message for kw in permission_keywords):
            return ErrorAnalysis(
                error_type=ErrorType.PERMISSION_ERROR,
                is_recoverable=False,
                root_cause=f"权限错误: {str(exception)}",
                suggested_fixes=[],
                retry_strategy=None,
                confidence=0.7,
                reasoning="基于异常类型和消息关键词匹配为权限错误",
            )
        
        # 资源相关错误
        resource_keywords = [
            "resource", "quota", "limit", "memory", "disk",
            "full", "exhausted", "capacity", "429", "rate"
        ]
        if any(kw in exception_type or kw in exception_message for kw in resource_keywords):
            return ErrorAnalysis(
                error_type=ErrorType.RESOURCE_ERROR,
                is_recoverable=True,
                root_cause=f"资源错误: {str(exception)}",
                suggested_fixes=[],
                retry_strategy="exponential_backoff",
                confidence=0.6,
                reasoning="基于异常类型和消息关键词匹配为资源错误",
            )
        
        # 依赖相关错误
        dependency_keywords = [
            "dependency", "import", "module", "not found", "missing",
            "undefined", "unresolved"
        ]
        if any(kw in exception_type or kw in exception_message for kw in dependency_keywords):
            return ErrorAnalysis(
                error_type=ErrorType.DEPENDENCY_ERROR,
                is_recoverable=False,
                root_cause=f"依赖错误: {str(exception)}",
                suggested_fixes=[],
                retry_strategy=None,
                confidence=0.6,
                reasoning="基于异常类型和消息关键词匹配为依赖错误",
            )
        
        # 逻辑相关错误
        logic_keywords = [
            "assertion", "logic", "state", "inconsistent",
            "unexpected", "illegal"
        ]
        if any(kw in exception_type or kw in exception_message for kw in logic_keywords):
            return ErrorAnalysis(
                error_type=ErrorType.LOGIC_ERROR,
                is_recoverable=False,
                root_cause=f"逻辑错误: {str(exception)}",
                suggested_fixes=[],
                retry_strategy=None,
                confidence=0.5,
                reasoning="基于异常类型和消息关键词匹配为逻辑错误",
            )
        
        # 默认：未知错误
        return ErrorAnalysis(
            error_type=ErrorType.UNKNOWN_ERROR,
            is_recoverable=True,
            root_cause=f"未知错误: {str(exception)}",
            suggested_fixes=[],
            retry_strategy="exponential_backoff",
            confidence=0.3,
            reasoning="无法匹配到已知错误类型，使用默认分析",
        )
