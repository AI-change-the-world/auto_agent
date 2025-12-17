"""
Memory 模块

三层记忆架构：
- L1: WorkingMemory (短时记忆) - 单次任务执行上下文
- L2: SemanticMemory (长期语义记忆) - JSON 结构化，支持反馈学习
- L3: NarrativeMemoryManager (叙事记忆) - Markdown 语义表达

统一接口：
- MemorySystem: 整合三层记忆的统一系统
- MemoryRouter: 记忆路由与注入控制

"""

from auto_agent.memory.manager import create_memory_system
from auto_agent.memory.models import (
    MemoryCategory,
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
from auto_agent.memory.system import MemorySystem
from auto_agent.memory.working import WorkingMemory

__all__ = [
    # 新架构 - 核心
    "MemorySystem",
    "MemoryRouter",
    "QueryIntent",
    "create_memory_system",
    # 新架构 - L1 短时记忆
    "WorkingMemory",
    "WorkingMemoryItem",
    # 新架构 - L2 语义记忆
    "SemanticMemory",
    "SemanticMemoryItem",
    # 新架构 - L3 叙事记忆
    "NarrativeMemoryManager",
    "NarrativeMemory",
    # 新架构 - 模型
    "MemoryCategory",
    "MemoryLayer",
    "MemorySource",
    "UserFeedback",
]
