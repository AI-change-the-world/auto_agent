"""
Auto-Agent 智能体框架

基于 LLM 的自主智能体框架，提供自主规划、工具调用、记忆管理等核心能力。

核心特性：
- 🤖 自主规划：基于 LLM 的任务分解和执行计划生成
- 🔧 工具系统：灵活的工具注册和调用机制（支持装饰器）
- 🔄 重试机制：智能错误处理和自动重试
- 🧠 双层记忆：长期记忆（用户级）+ 短期记忆（对话级，支持智能压缩）
- ✅ 期望验证：自然语言期望描述 + 自定义验证函数
- 📊 结果压缩：工具级自定义压缩函数，避免 LLM 上下文溢出
"""

from auto_agent.core.agent import AutoAgent
from auto_agent.core.context import ExecutionContext, StepRecord
from auto_agent.core.editor.parser import AgentDefinition, AgentMarkdownParser
from auto_agent.core.executor import ExecutionEngine
from auto_agent.core.planner import TaskPlanner
from auto_agent.core.report.generator import ExecutionReportGenerator
from auto_agent.core.router.intent import IntentHandler, IntentResult, IntentRouter
from auto_agent.llm.client import LLMClient
from auto_agent.llm.providers.openai import OpenAIClient
from auto_agent.memory.manager import create_memory_system
from auto_agent.memory.models import (
    MemoryLayer,
    MemorySource,
    NarrativeMemory,
    SemanticMemoryItem,
    UserFeedback,
    WorkingMemoryItem,
)
from auto_agent.memory.narrative import NarrativeMemoryManager
from auto_agent.memory.router import MemoryRouter, QueryIntent
from auto_agent.memory.semantic import SemanticMemory

# 新记忆系统 (L1/L2/L3 架构)
from auto_agent.memory.system import MemorySystem
from auto_agent.memory.working import WorkingMemory
from auto_agent.models import (
    AgentResponse,
    ExecutionPlan,
    FailAction,
    Message,
    PlanStep,
    StepResultData,
    SubTaskResult,
    ToolDefinition,
    ToolParameter,
    ValidationMode,
)
from auto_agent.retry.models import RetryConfig, RetryStrategy
from auto_agent.tools.base import BaseTool
from auto_agent.tools.registry import ToolRegistry, func_tool, get_global_registry, tool

__version__ = "0.1.0"

__all__ = [
    # 核心
    "AutoAgent",
    "ExecutionContext",
    "StepRecord",
    "ExecutionEngine",
    "TaskPlanner",
    "LLMClient",
    "OpenAIClient",
    # 报告和编辑
    "ExecutionReportGenerator",
    "AgentMarkdownParser",
    "AgentDefinition",
    # 路由
    "IntentRouter",
    "IntentHandler",
    "IntentResult",
    # 工具
    "ToolRegistry",
    "BaseTool",
    "tool",
    "func_tool",
    "get_global_registry",
    "ToolDefinition",
    "ToolParameter",
    # 记忆 (新架构 L1/L2/L3)
    "MemorySystem",
    "WorkingMemory",
    "SemanticMemory",
    "NarrativeMemoryManager",
    "MemoryRouter",
    "QueryIntent",
    "create_memory_system",
    "MemoryLayer",
    "MemorySource",
    "SemanticMemoryItem",
    "WorkingMemoryItem",
    "NarrativeMemory",
    "UserFeedback",
    # 模型
    "Message",
    "PlanStep",
    "StepResultData",
    "ExecutionPlan",
    "SubTaskResult",
    "AgentResponse",
    "FailAction",
    "ValidationMode",
    # 重试
    "RetryConfig",
    "RetryStrategy",
]
