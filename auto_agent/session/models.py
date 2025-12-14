"""
会话数据模型
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionStatus(Enum):
    """会话状态"""

    ACTIVE = "active"  # 活跃中
    WAITING_INPUT = "waiting_input"  # 等待用户输入
    PAUSED = "paused"  # 暂停
    COMPLETED = "completed"  # 已完成
    ERROR = "error"  # 错误
    EXPIRED = "expired"  # 已过期


@dataclass
class SessionMessage:
    """会话消息"""

    role: str  # user / assistant / system / tool
    content: str
    timestamp: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """会话数据"""

    session_id: str
    user_id: str
    created_at: int
    updated_at: int
    expires_at: int
    status: SessionStatus = SessionStatus.ACTIVE
    messages: List[SessionMessage] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 执行相关
    current_step: int = 0
    execution_plan: Optional[Dict[str, Any]] = None
    execution_results: List[Dict[str, Any]] = field(default_factory=list)
    # 等待输入相关
    waiting_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "status": self.status.value,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "metadata": m.metadata,
                }
                for m in self.messages
            ],
            "state": self.state,
            "metadata": self.metadata,
            "current_step": self.current_step,
        }
