"""
Tracing Context - 追踪上下文管理

使用 ContextVar 实现协程安全的追踪上下文传递
提供装饰器和工具函数简化追踪埋点
"""

import asyncio
import functools
import time
from contextvars import ContextVar
from typing import Any, Callable, Dict, Optional, TypeVar, Union

from auto_agent.tracing.models import (
    EventType,
    FlowAction,
    FlowEvent,
    LLMCallEvent,
    LLMPurpose,
    MemoryAction,
    MemoryEvent,
    BindingEvent,
    BindingAction,
    ToolCallEvent,
    TraceContext,
    TraceEvent,
    TraceSpan,
)

# 全局 ContextVar，存储当前追踪上下文
_trace_ctx: ContextVar[Optional[TraceContext]] = ContextVar("trace_ctx", default=None)

# 类型变量
F = TypeVar("F", bound=Callable[..., Any])


class Tracer:
    """
    追踪器
    
    用于管理追踪上下文的生命周期
    
    使用示例：
        with Tracer.start("user_query", user_id="u1") as trace:
            # 执行逻辑
            pass
        
        # 获取结果
        report = trace.to_dict()
    """
    
    @staticmethod
    def start(
        query: str = "",
        user_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TracerContextManager":
        """开始追踪"""
        return TracerContextManager(query, user_id, metadata)
    
    @staticmethod
    def get_current() -> Optional[TraceContext]:
        """获取当前追踪上下文"""
        return _trace_ctx.get()
    
    @staticmethod
    def set_current(ctx: Optional[TraceContext]):
        """设置当前追踪上下文"""
        _trace_ctx.set(ctx)


class TracerContextManager:
    """追踪上下文管理器"""
    
    def __init__(
        self,
        query: str = "",
        user_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.query = query
        self.user_id = user_id
        self.metadata = metadata or {}
        self.trace: Optional[TraceContext] = None
        self._token = None
    
    def __enter__(self) -> TraceContext:
        self.trace = TraceContext(
            query=self.query,
            user_id=self.user_id,
            metadata=self.metadata,
        )
        self._token = _trace_ctx.set(self.trace)
        return self.trace
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.trace:
            self.trace.end()
        if self._token is not None:
            _trace_ctx.reset(self._token)
        return False
    
    async def __aenter__(self) -> TraceContext:
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


class SpanContextManager:
    """Span 上下文管理器"""
    
    def __init__(self, name: str, span_type: str = "", metadata: Optional[Dict[str, Any]] = None):
        self.name = name
        self.span_type = span_type
        self.metadata = metadata or {}
        self.span: Optional[TraceSpan] = None
    
    def __enter__(self) -> Optional[TraceSpan]:
        trace = get_current_trace()
        if trace:
            self.span = trace.start_span(self.name, self.span_type)
            self.span.metadata.update(self.metadata)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        trace = get_current_trace()
        if trace and self.span:
            trace.end_span()
        return False
    
    async def __aenter__(self) -> Optional[TraceSpan]:
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


# ==================== 便捷函数 ====================

def get_current_trace() -> Optional[TraceContext]:
    """获取当前追踪上下文"""
    return _trace_ctx.get()


def get_current_span() -> Optional[TraceSpan]:
    """获取当前跨度"""
    trace = get_current_trace()
    return trace.current_span if trace else None


def start_span(name: str, span_type: str = "", **metadata) -> SpanContextManager:
    """开始新的跨度"""
    return SpanContextManager(name, span_type, metadata)


# ==================== 事件记录函数 ====================

def trace_llm_call(
    purpose: Union[LLMPurpose, str],
    model: str = "",
    provider: str = "",
    prompt: str = "",
    response: str = "",
    prompt_tokens: int = 0,
    response_tokens: int = 0,
    total_tokens: int = 0,
    temperature: float = 0.7,
    duration_ms: float = 0,
    success: bool = True,
    error: Optional[str] = None,
    **metadata,
):
    """
    记录 LLM 调用事件
    
    可以作为函数调用，也可以作为装饰器使用
    """
    trace = get_current_trace()
    if not trace:
        return
    
    if isinstance(purpose, str):
        try:
            purpose = LLMPurpose(purpose)
        except ValueError:
            purpose = LLMPurpose.OTHER
    
    event = LLMCallEvent(
        purpose=purpose,
        model=model,
        provider=provider,
        prompt=prompt,
        response=response,
        prompt_tokens=prompt_tokens,
        response_tokens=response_tokens,
        total_tokens=total_tokens or (prompt_tokens + response_tokens),
        temperature=temperature,
        duration_ms=duration_ms,
        success=success,
        error=error,
        metadata=metadata,
    )
    trace.add_event(event)


def trace_tool_call(
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    result: Any = None,
    duration_ms: float = 0,
    success: bool = True,
    error: Optional[str] = None,
    tool_description: str = "",
    **metadata,
):
    """记录工具调用事件"""
    trace = get_current_trace()
    if not trace:
        return
    
    event = ToolCallEvent(
        tool_name=tool_name,
        tool_description=tool_description,
        arguments=arguments or {},
        result=result,
        duration_ms=duration_ms,
        success=success,
        error=error,
        metadata=metadata,
    )
    trace.add_event(event)


def trace_flow_event(
    action: Union[FlowAction, str],
    reason: str = "",
    from_step: str = "",
    to_step: Optional[str] = None,
    attempt: int = 1,
    max_attempts: int = 3,
    **context,
):
    """记录流程控制事件（重试/跳转/中止）"""
    trace = get_current_trace()
    if not trace:
        return
    
    if isinstance(action, str):
        try:
            action = FlowAction(action)
        except ValueError:
            action = FlowAction.FALLBACK
    
    event = FlowEvent(
        action=action,
        reason=reason,
        from_step=from_step,
        to_step=to_step,
        attempt=attempt,
        max_attempts=max_attempts,
        context=context,
    )
    trace.add_event(event)


def trace_memory_event(
    action: Union[MemoryAction, str],
    memory_layer: str = "",
    query: str = "",
    result_count: int = 0,
    content_preview: str = "",
    duration_ms: float = 0,
    **metadata,
):
    """记录记忆操作事件"""
    trace = get_current_trace()
    if not trace:
        return
    
    if isinstance(action, str):
        try:
            action = MemoryAction(action)
        except ValueError:
            action = MemoryAction.READ
    
    event = MemoryEvent(
        action=action,
        memory_layer=memory_layer,
        query=query,
        result_count=result_count,
        content_preview=content_preview,
        duration_ms=duration_ms,
        metadata=metadata,
    )
    trace.add_event(event)


def trace_binding_event(
    action: Union[BindingAction, str],
    step_id: str = "",
    tool_name: str = "",
    bindings_count: int = 0,
    resolved_count: int = 0,
    fallback_count: int = 0,
    confidence_threshold: float = 0.7,
    binding_details: list = None,
    duration_ms: float = 0,
    **metadata,
):
    """
    记录参数绑定事件
    
    Args:
        action: 绑定动作类型 (plan_create, resolve, fallback)
        step_id: 步骤 ID
        tool_name: 工具名称
        bindings_count: 绑定总数
        resolved_count: 成功解析数
        fallback_count: 需要 fallback 数
        confidence_threshold: 置信度阈值
        binding_details: 绑定详情列表
        duration_ms: 耗时（毫秒）
    """
    trace = get_current_trace()
    if not trace:
        return
    
    if isinstance(action, str):
        try:
            action = BindingAction(action)
        except ValueError:
            action = BindingAction.RESOLVE
    
    event = BindingEvent(
        action=action,
        step_id=step_id,
        tool_name=tool_name,
        bindings_count=bindings_count,
        resolved_count=resolved_count,
        fallback_count=fallback_count,
        confidence_threshold=confidence_threshold,
        binding_details=binding_details or [],
        duration_ms=duration_ms,
        metadata=metadata,
    )
    trace.add_event(event)


# ==================== 装饰器 ====================

def traced_llm(purpose: Union[LLMPurpose, str] = LLMPurpose.OTHER):
    """
    LLM 调用追踪装饰器
    
    自动记录 LLM 调用的 prompt、response、tokens、耗时
    
    使用示例：
        @traced_llm(purpose=LLMPurpose.PARAM_BUILD)
        async def build_params(self, prompt: str) -> str:
            return await self.llm_client.chat(...)
    
    注意：被装饰的函数需要返回包含以下字段的字典或对象：
        - response: str
        - prompt_tokens: int (可选)
        - response_tokens: int (可选)
        - total_tokens: int (可选)
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            result = None
            error = None
            success = True
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                success = False
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                
                # 尝试从结果中提取信息
                response = ""
                prompt_tokens = 0
                response_tokens = 0
                total_tokens = 0
                
                if isinstance(result, dict):
                    response = result.get("response", result.get("content", str(result)))
                    prompt_tokens = result.get("prompt_tokens", 0)
                    response_tokens = result.get("response_tokens", 0)
                    total_tokens = result.get("total_tokens", 0)
                elif isinstance(result, str):
                    response = result
                
                trace_llm_call(
                    purpose=purpose,
                    response=response,
                    prompt_tokens=prompt_tokens,
                    response_tokens=response_tokens,
                    total_tokens=total_tokens,
                    duration_ms=duration_ms,
                    success=success,
                    error=error,
                )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            result = None
            error = None
            success = True
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                success = False
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                
                response = ""
                if isinstance(result, dict):
                    response = result.get("response", result.get("content", str(result)))
                elif isinstance(result, str):
                    response = result
                
                trace_llm_call(
                    purpose=purpose,
                    response=response,
                    duration_ms=duration_ms,
                    success=success,
                    error=error,
                )
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore
    
    return decorator


def traced_tool(tool_name: Optional[str] = None):
    """
    工具调用追踪装饰器
    
    自动记录工具调用的参数、结果、耗时
    
    使用示例：
        @traced_tool("search_documents")
        async def search(self, query: str) -> Dict:
            ...
    """
    def decorator(func: F) -> F:
        name = tool_name or func.__name__
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            result = None
            error = None
            success = True
            
            try:
                result = await func(*args, **kwargs)
                if isinstance(result, dict):
                    success = result.get("success", True)
                    error = result.get("error")
                return result
            except Exception as e:
                error = str(e)
                success = False
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                trace_tool_call(
                    tool_name=name,
                    arguments=kwargs,
                    result=result,
                    duration_ms=duration_ms,
                    success=success,
                    error=error,
                )
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            result = None
            error = None
            success = True
            
            try:
                result = func(*args, **kwargs)
                if isinstance(result, dict):
                    success = result.get("success", True)
                    error = result.get("error")
                return result
            except Exception as e:
                error = str(e)
                success = False
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                trace_tool_call(
                    tool_name=name,
                    arguments=kwargs,
                    result=result,
                    duration_ms=duration_ms,
                    success=success,
                    error=error,
                )
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore
    
    return decorator


def traced_span(name: str, span_type: str = ""):
    """
    Span 追踪装饰器
    
    自动创建和管理 span 生命周期
    
    使用示例：
        @traced_span("planning", span_type="planning")
        async def create_plan(self, query: str) -> ExecutionPlan:
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with start_span(name, span_type):
                return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with start_span(name, span_type):
                return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore
    
    return decorator
