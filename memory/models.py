"""
记忆数据模型
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from auto_agent.models import Message


@dataclass
class WorkingMemory:
    """
    工作记忆

    存储当前任务执行过程中的临时数据
    """

    current_task: Optional[str] = None
    task_history: List[Any] = field(default_factory=list)
    tool_results: Dict[str, Any] = field(default_factory=dict)
    intermediate_steps: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ConversationMemory:
    """
    对话记忆

    存储单次对话的完整信息
    """

    conversation_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    working_memory: WorkingMemory = field(default_factory=WorkingMemory)
    created_at: int = 0
    updated_at: int = 0


@dataclass
class UserMemory:
    """
    用户记忆

    长期存储的用户信息
    """

    user_id: str
    preferences: Dict[str, Any] = field(default_factory=dict)
    knowledge: Dict[str, Any] = field(default_factory=dict)
    interaction_history: List[str] = field(default_factory=list)
    custom_context: str = ""
