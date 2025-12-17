"""
会话管理器

支持:
- 多轮对话状态管理
- 会话持久化和恢复
- 用户干预（等待用户输入）
- 自动过期清理
"""

import asyncio
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from auto_agent.session.models import Session, SessionMessage, SessionStatus


class SessionManager:
    """
    会话管理器

    特性:
    1. 基于 session_id 管理会话状态
    2. 支持多轮对话
    3. 支持用户干预（等待用户输入）
    4. 自动过期清理
    """

    def __init__(
        self,
        default_ttl: int = 1800,  # 默认 30 分钟
        max_sessions: int = 1000,
        cleanup_interval: int = 300,  # 5 分钟清理一次
    ):
        self._sessions: Dict[str, Session] = {}
        self._default_ttl = default_ttl
        self._max_sessions = max_sessions
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._on_expire_callbacks: List[Callable] = []

    def create_session(
        self,
        user_id: str,
        initial_query: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        current_time = int(time.time())

        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=current_time,
            updated_at=current_time,
            expires_at=current_time + self._default_ttl,
            status=SessionStatus.ACTIVE,
            messages=[
                SessionMessage(
                    role="user",
                    content=initial_query,
                    timestamp=current_time,
                )
            ],
            state={"query": initial_query},
            metadata=metadata or {},
        )

        self._sessions[session_id] = session

        # 如果超过最大会话数，清理最旧的
        if len(self._sessions) > self._max_sessions:
            self._cleanup_oldest()

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        session = self._sessions.get(session_id)
        if session and int(time.time()) < session.expires_at:
            return session
        elif session:
            session.status = SessionStatus.EXPIRED
        return session

    def get_active_session(self, session_id: str) -> Optional[Session]:
        """获取活跃会话（未过期且状态为 ACTIVE）"""
        session = self.get_session(session_id)
        if session and session.status == SessionStatus.ACTIVE:
            return session
        return None

    def update_session(
        self,
        session_id: str,
        status: Optional[SessionStatus] = None,
        state: Optional[Dict[str, Any]] = None,
        message: Optional[SessionMessage] = None,
        current_step: Optional[int] = None,
    ) -> bool:
        """更新会话"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        current_time = int(time.time())
        session.updated_at = current_time
        session.expires_at = current_time + self._default_ttl

        if status is not None:
            session.status = status
        if state is not None:
            session.state.update(state)
        if message is not None:
            session.messages.append(message)
        if current_step is not None:
            session.current_step = current_step

        return True

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """添加消息"""
        message = SessionMessage(
            role=role,
            content=content,
            timestamp=int(time.time()),
            metadata=metadata or {},
        )
        return self.update_session(session_id, message=message)

    def wait_for_input(self, session_id: str, prompt: str) -> bool:
        """设置会话为等待用户输入状态"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        session.status = SessionStatus.WAITING_INPUT
        session.waiting_prompt = prompt
        session.updated_at = int(time.time())
        return True

    def resume_session(self, session_id: str, user_input: str) -> bool:
        """恢复会话（用户提供输入后）"""
        session = self.get_session(session_id)
        if not session or session.status != SessionStatus.WAITING_INPUT:
            return False

        session.status = SessionStatus.ACTIVE
        session.waiting_prompt = None
        self.add_message(session_id, "user", user_input)
        return True

    def pause_session(self, session_id: str) -> bool:
        """暂停会话"""
        return self.update_session(session_id, status=SessionStatus.PAUSED)

    def complete_session(
        self,
        session_id: str,
        final_result: Optional[str] = None,
    ) -> bool:
        """完成会话"""
        if final_result:
            self.add_message(session_id, "assistant", final_result)
        return self.update_session(session_id, status=SessionStatus.COMPLETED)

    def error_session(self, session_id: str, error: str) -> bool:
        """标记会话错误"""
        self.add_message(session_id, "system", f"Error: {error}")
        return self.update_session(session_id, status=SessionStatus.ERROR)

    def get_user_sessions(
        self,
        user_id: str,
        status: Optional[SessionStatus] = None,
        limit: int = 10,
    ) -> List[Session]:
        """获取用户的会话列表"""
        sessions = [
            s
            for s in self._sessions.values()
            if s.user_id == user_id and (status is None or s.status == status)
        ]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions[:limit]

    def get_conversation_history(
        self,
        session_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """获取对话历史（用于 LLM 上下文）"""
        session = self.get_session(session_id)
        if not session:
            return []

        messages = session.messages[-limit:]
        return [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ["user", "assistant", "system"]
        ]

    def cleanup_expired(self) -> int:
        """清理过期会话"""
        current_time = int(time.time())
        expired = [
            sid for sid, s in self._sessions.items() if current_time > s.expires_at
        ]
        for sid in expired:
            session = self._sessions.pop(sid, None)
            if session:
                for callback in self._on_expire_callbacks:
                    try:
                        callback(session)
                    except Exception:
                        pass
        return len(expired)

    def _cleanup_oldest(self):
        """清理最旧的会话"""
        if not self._sessions:
            return
        oldest = min(self._sessions.values(), key=lambda s: s.updated_at)
        self._sessions.pop(oldest.session_id, None)

    def on_expire(self, callback: Callable[[Session], None]):
        """注册过期回调"""
        self._on_expire_callbacks.append(callback)

    async def start_cleanup_task(self):
        """启动后台清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self):
        """停止后台清理任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def _cleanup_loop(self):
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                count = self.cleanup_expired()
                if count > 0:
                    pass  # 可以添加日志
            except asyncio.CancelledError:
                break
            except Exception:
                pass
