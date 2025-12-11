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
from auto_agent.llm.client import LLMClient
from auto_agent.memory.long_term import LongTermMemory
from auto_agent.memory.short_term import ShortTermMemory
from auto_agent.models import (
    AgentResponse,
    ExecutionPlan,
    FailAction,
    Message,
    PlanStep,
    SubTaskResult,
    ToolDefinition,
    ToolParameter,
    ValidationMode,
)
from auto_agent.retry.models import RetryConfig, RetryStrategy
from auto_agent.tools.base import BaseTool
from auto_agent.tools.registry import ToolRegistry, get_global_registry, tool

__version__ = "0.1.0"

__all__ = [
    # 核心
    "AutoAgent",
    "LLMClient",
    # 工具
    "ToolRegistry",
    "BaseTool",
    "tool",
    "get_global_registry",
    "ToolDefinition",
    "ToolParameter",
    # 记忆
    "LongTermMemory",
    "ShortTermMemory",
    # 模型
    "Message",
    "PlanStep",
    "ExecutionPlan",
    "SubTaskResult",
    "AgentResponse",
    "FailAction",
    "ValidationMode",
    # 重试
    "RetryConfig",
    "RetryStrategy",
]
