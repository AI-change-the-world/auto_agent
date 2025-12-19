"""
Tracing 数据模型

定义追踪系统的核心数据结构
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(Enum):
    """事件类型"""
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    FLOW = "flow"  # 重试/跳转/中止
    MEMORY = "memory"
    ERROR = "error"
    CUSTOM = "custom"


class LLMPurpose(Enum):
    """LLM 调用目的"""
    PLANNING = "planning"  # 任务规划
    BINDING_PLAN = "binding_plan"  # 参数绑定规划
    PARAM_BUILD = "param_build"  # 参数构造
    VALIDATION = "validation"  # 期望验证
    ERROR_ANALYSIS = "error_analysis"  # 错误分析
    PARAM_FIX = "param_fix"  # 参数修正
    MEMORY_QUERY = "memory_query"  # 记忆查询
    MEMORY_SUMMARY = "memory_summary"  # 记忆总结
    PROMPT_GEN = "prompt_gen"  # Prompt 生成
    REPLAN = "replan"  # 重规划
    INCREMENTAL_REPLAN = "incremental_replan"  # 增量重规划
    CONSISTENCY_CHECK = "consistency_check"  # 一致性检查
    CHECKPOINT_REGISTER = "checkpoint_register"  # 检查点注册
    WORKING_MEMORY = "working_memory"  # 工作记忆提取
    OTHER = "other"


class FlowAction(Enum):
    """流程控制动作"""
    RETRY = "retry"
    JUMP = "jump"
    ABORT = "abort"
    FALLBACK = "fallback"
    REPLAN = "replan"


class MemoryAction(Enum):
    """记忆操作类型"""
    READ = "read"
    WRITE = "write"
    SEARCH = "search"
    DELETE = "delete"


@dataclass
class TraceEvent:
    """追踪事件基类"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: EventType = EventType.CUSTOM
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass
class LLMCallEvent(TraceEvent):
    """LLM 调用事件"""
    event_type: EventType = field(default=EventType.LLM_CALL)
    purpose: LLMPurpose = LLMPurpose.OTHER
    model: str = ""
    provider: str = ""
    prompt: str = ""
    prompt_tokens: int = 0
    response: str = ""
    response_tokens: int = 0
    total_tokens: int = 0
    temperature: float = 0.7
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self, truncate: bool = True) -> Dict[str, Any]:
        """
        转换为字典
        
        Args:
            truncate: 是否截断长文本（默认 True）
        """
        base = super().to_dict()
        
        if truncate:
            prompt_display = self.prompt[:500] + "..." if len(self.prompt) > 500 else self.prompt
            response_display = self.response[:500] + "..." if len(self.response) > 500 else self.response
        else:
            prompt_display = self.prompt
            response_display = self.response
        
        base.update({
            "purpose": self.purpose.value,
            "model": self.model,
            "provider": self.provider,
            "prompt": prompt_display,
            "prompt_length": len(self.prompt),
            "prompt_tokens": self.prompt_tokens,
            "response": response_display,
            "response_length": len(self.response),
            "response_tokens": self.response_tokens,
            "total_tokens": self.total_tokens,
            "temperature": self.temperature,
            "success": self.success,
            "error": self.error,
        })
        return base


@dataclass
class ToolCallEvent(TraceEvent):
    """工具调用事件"""
    event_type: EventType = field(default=EventType.TOOL_CALL)
    tool_name: str = ""
    tool_description: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self, truncate: bool = True) -> Dict[str, Any]:
        """
        转换为字典
        
        Args:
            truncate: 是否截断长文本（默认 True）
        """
        base = super().to_dict()
        args_str = str(self.arguments)
        result_str = str(self.result)
        
        if truncate:
            args_display = self.arguments if len(args_str) < 1000 else f"[{len(args_str)} chars]"
            result_display = result_str[:500] + "..." if len(result_str) > 500 else result_str
        else:
            args_display = self.arguments
            result_display = self.result
        
        base.update({
            "tool_name": self.tool_name,
            "tool_description": self.tool_description,
            "arguments": args_display,
            "result": result_display,
            "success": self.success,
            "error": self.error,
        })
        return base


@dataclass
class FlowEvent(TraceEvent):
    """流程控制事件（重试/跳转/中止）"""
    event_type: EventType = field(default=EventType.FLOW)
    action: FlowAction = FlowAction.FALLBACK
    reason: str = ""
    from_step: str = ""
    to_step: Optional[str] = None
    attempt: int = 1
    max_attempts: int = 3
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "action": self.action.value,
            "reason": self.reason,
            "from_step": self.from_step,
            "to_step": self.to_step,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "context": self.context,
        })
        return base


class BindingAction(Enum):
    """参数绑定动作类型"""
    PLAN_CREATE = "plan_create"  # 创建绑定计划
    RESOLVE = "resolve"  # 解析绑定
    FALLBACK = "fallback"  # 回退到 LLM


@dataclass
class BindingEvent(TraceEvent):
    """参数绑定事件"""
    event_type: EventType = field(default=EventType.CUSTOM)
    action: BindingAction = BindingAction.RESOLVE
    step_id: str = ""
    tool_name: str = ""
    bindings_count: int = 0
    resolved_count: int = 0
    fallback_count: int = 0
    confidence_threshold: float = 0.7
    binding_details: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self, truncate: bool = True) -> Dict[str, Any]:
        """转换为字典"""
        base = super().to_dict()
        base.update({
            "action": self.action.value,
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "bindings_count": self.bindings_count,
            "resolved_count": self.resolved_count,
            "fallback_count": self.fallback_count,
            "confidence_threshold": self.confidence_threshold,
            "binding_details": self.binding_details if not truncate else self.binding_details[:5],
        })
        return base


@dataclass
class MemoryEvent(TraceEvent):
    """记忆操作事件"""
    event_type: EventType = field(default=EventType.MEMORY)
    action: MemoryAction = MemoryAction.READ
    memory_layer: str = ""  # L1/L2/L3
    query: str = ""
    result_count: int = 0
    content_preview: str = ""
    
    def to_dict(self, truncate: bool = True) -> Dict[str, Any]:
        """
        转换为字典
        
        Args:
            truncate: 是否截断长文本（默认 True）
        """
        base = super().to_dict()
        
        if truncate:
            query_display = self.query[:200] + "..." if len(self.query) > 200 else self.query
            content_display = self.content_preview[:300] + "..." if len(self.content_preview) > 300 else self.content_preview
        else:
            query_display = self.query
            content_display = self.content_preview
        
        base.update({
            "action": self.action.value,
            "memory_layer": self.memory_layer,
            "query": query_display,
            "result_count": self.result_count,
            "content_preview": content_display,
        })
        return base


@dataclass
class TraceSpan:
    """
    追踪跨度（一个逻辑单元）
    
    例如：planning, step_1, memory_load
    """
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: Optional[str] = None
    name: str = ""
    span_type: str = ""  # planning, step, memory, validation
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    events: List[TraceEvent] = field(default_factory=list)
    children: List["TraceSpan"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> float:
        """计算耗时（毫秒）"""
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000
    
    def add_event(self, event: TraceEvent):
        """添加事件"""
        self.events.append(event)
    
    def create_child(self, name: str, span_type: str = "") -> "TraceSpan":
        """创建子跨度"""
        child = TraceSpan(
            parent_id=self.span_id,
            name=name,
            span_type=span_type,
        )
        self.children.append(child)
        return child
    
    def end(self):
        """结束跨度"""
        self.end_time = time.time()
    
    def to_dict(self, truncate: bool = True) -> Dict[str, Any]:
        """
        转换为字典
        
        Args:
            truncate: 是否截断长文本（默认 True）
        """
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "span_type": self.span_type,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "events": [self._event_to_dict(e, truncate) for e in self.events],
            "children": [c.to_dict(truncate=truncate) for c in self.children],
            "metadata": self.metadata,
        }
    
    def _event_to_dict(self, event: TraceEvent, truncate: bool) -> Dict[str, Any]:
        """将事件转换为字典，支持 truncate 参数"""
        try:
            return event.to_dict(truncate=truncate)
        except TypeError:
            # 如果 to_dict 不支持 truncate 参数，使用默认调用
            return event.to_dict()
    
    def get_llm_stats(self) -> Dict[str, Any]:
        """获取 LLM 调用统计"""
        llm_events = [e for e in self.events if isinstance(e, LLMCallEvent)]
        
        # 递归统计子跨度
        for child in self.children:
            child_stats = child.get_llm_stats()
            # 这里简化处理，只统计当前层
        
        return {
            "count": len(llm_events),
            "total_tokens": sum(e.total_tokens for e in llm_events),
            "prompt_tokens": sum(e.prompt_tokens for e in llm_events),
            "response_tokens": sum(e.response_tokens for e in llm_events),
            "total_duration_ms": sum(e.duration_ms for e in llm_events),
        }


@dataclass
class TraceContext:
    """
    完整追踪上下文
    
    代表一次完整的 Agent 执行追踪
    """
    trace_id: str = field(default_factory=lambda: f"tr_{uuid.uuid4().hex[:12]}")
    user_id: str = ""
    query: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    root_span: TraceSpan = field(default_factory=lambda: TraceSpan(name="root", span_type="root"))
    current_span: Optional[TraceSpan] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.current_span is None:
            self.current_span = self.root_span
    
    @property
    def duration_ms(self) -> float:
        """计算总耗时（毫秒）"""
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000
    
    def start_span(self, name: str, span_type: str = "") -> TraceSpan:
        """开始新的跨度"""
        span = self.current_span.create_child(name, span_type)
        self.current_span = span
        return span
    
    def end_span(self):
        """结束当前跨度，返回父跨度"""
        if self.current_span:
            self.current_span.end()
            # 找到父跨度
            parent = self._find_span_by_id(self.current_span.parent_id)
            if parent:
                self.current_span = parent
            else:
                self.current_span = self.root_span
    
    def _find_span_by_id(self, span_id: Optional[str]) -> Optional[TraceSpan]:
        """根据 ID 查找跨度"""
        if span_id is None:
            return None
        return self._find_span_recursive(self.root_span, span_id)
    
    def _find_span_recursive(self, span: TraceSpan, span_id: str) -> Optional[TraceSpan]:
        """递归查找跨度"""
        if span.span_id == span_id:
            return span
        for child in span.children:
            found = self._find_span_recursive(child, span_id)
            if found:
                return found
        return None
    
    def add_event(self, event: TraceEvent):
        """添加事件到当前跨度"""
        if self.current_span:
            self.current_span.add_event(event)
    
    def end(self):
        """结束追踪"""
        self.end_time = time.time()
        self.root_span.end()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取追踪摘要"""
        all_events = self._collect_all_events(self.root_span)
        
        llm_events = [e for e in all_events if isinstance(e, LLMCallEvent)]
        tool_events = [e for e in all_events if isinstance(e, ToolCallEvent)]
        flow_events = [e for e in all_events if isinstance(e, FlowEvent)]
        memory_events = [e for e in all_events if isinstance(e, MemoryEvent)]
        binding_events = [e for e in all_events if isinstance(e, BindingEvent)]
        
        # 统计绑定事件
        binding_stats = {
            "plan_creates": 0,
            "resolves": 0,
            "fallbacks": 0,
            "total_bindings": 0,
            "resolved_bindings": 0,
            "fallback_bindings": 0,
        }
        for e in binding_events:
            if e.action == BindingAction.PLAN_CREATE:
                binding_stats["plan_creates"] += 1
            elif e.action == BindingAction.RESOLVE:
                binding_stats["resolves"] += 1
            elif e.action == BindingAction.FALLBACK:
                binding_stats["fallbacks"] += 1
            binding_stats["total_bindings"] += e.bindings_count
            binding_stats["resolved_bindings"] += e.resolved_count
            binding_stats["fallback_bindings"] += e.fallback_count
        
        return {
            "trace_id": self.trace_id,
            "duration_ms": self.duration_ms,
            "llm_calls": {
                "count": len(llm_events),
                "total_tokens": sum(e.total_tokens for e in llm_events),
                "prompt_tokens": sum(e.prompt_tokens for e in llm_events),
                "response_tokens": sum(e.response_tokens for e in llm_events),
                "by_purpose": self._group_llm_by_purpose(llm_events),
            },
            "tool_calls": {
                "count": len(tool_events),
                "success": sum(1 for e in tool_events if e.success),
                "failed": sum(1 for e in tool_events if not e.success),
            },
            "flow_events": {
                "retries": sum(1 for e in flow_events if e.action == FlowAction.RETRY),
                "jumps": sum(1 for e in flow_events if e.action == FlowAction.JUMP),
                "aborts": sum(1 for e in flow_events if e.action == FlowAction.ABORT),
                "replans": sum(1 for e in flow_events if e.action == FlowAction.REPLAN),
            },
            "memory_ops": {
                "reads": sum(1 for e in memory_events if e.action == MemoryAction.READ),
                "writes": sum(1 for e in memory_events if e.action == MemoryAction.WRITE),
                "searches": sum(1 for e in memory_events if e.action == MemoryAction.SEARCH),
            },
            "binding_ops": binding_stats,
        }
    
    def _collect_all_events(self, span: TraceSpan) -> List[TraceEvent]:
        """递归收集所有事件"""
        events = list(span.events)
        for child in span.children:
            events.extend(self._collect_all_events(child))
        return events
    
    def _group_llm_by_purpose(self, events: List[LLMCallEvent]) -> Dict[str, Dict[str, Any]]:
        """按目的分组 LLM 调用"""
        groups: Dict[str, List[LLMCallEvent]] = {}
        for e in events:
            key = e.purpose.value
            if key not in groups:
                groups[key] = []
            groups[key].append(e)
        
        return {
            purpose: {
                "count": len(evts),
                "tokens": sum(e.total_tokens for e in evts),
            }
            for purpose, evts in groups.items()
        }
    
    def to_dict(self, truncate: bool = True) -> Dict[str, Any]:
        """
        转换为完整字典
        
        Args:
            truncate: 是否截断长文本（默认 True）
                - True: 截断 prompt/response 等长文本，适合日志和概览
                - False: 保留完整内容，适合详细报告
        """
        if truncate:
            query_display = self.query[:500] + "..." if len(self.query) > 500 else self.query
        else:
            query_display = self.query
        
        return {
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "query": query_display,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "summary": self.get_summary(),
            "spans": self.root_span.to_dict(truncate=truncate),
            "metadata": self.metadata,
        }
