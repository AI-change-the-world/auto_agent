"""
Agent Tracing System - 智能体执行追踪系统

提供细粒度的执行追踪能力，包括：
- LLM 调用追踪（prompt/response/tokens/耗时）
- 工具调用追踪（参数/结果/耗时）
- 流程控制追踪（重试/跳转/中止原因）
- 记忆操作追踪（读/写）

使用方式：
    from auto_agent.tracing import Tracer, get_current_trace
    
    # 开始追踪
    with Tracer.start("user_query") as trace:
        # 执行逻辑...
        pass
    
    # 获取追踪结果
    report = trace.to_dict()
"""

from auto_agent.tracing.models import (
    TraceEvent,
    LLMCallEvent,
    ToolCallEvent,
    FlowEvent,
    MemoryEvent,
    TraceSpan,
    TraceContext,
)
from auto_agent.tracing.context import (
    Tracer,
    get_current_trace,
    get_current_span,
    trace_llm_call,
    trace_tool_call,
    trace_flow_event,
    trace_memory_event,
    start_span
)

__all__ = [
    # 数据模型
    "TraceEvent",
    "LLMCallEvent",
    "ToolCallEvent",
    "FlowEvent",
    "MemoryEvent",
    "TraceSpan",
    "TraceContext",
    # 追踪工具
    "Tracer",
    "get_current_trace",
    "get_current_span",
    "trace_llm_call",
    "trace_tool_call",
    "trace_flow_event",
    "trace_memory_event",
    "start_span"
]
