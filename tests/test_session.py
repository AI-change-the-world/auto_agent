"""
会话管理器测试
"""

import time

import pytest

from auto_agent.session.manager import SessionManager
from auto_agent.session.models import SessionStatus


class TestSessionManager:
    """会话管理器测试"""

    def setup_method(self):
        """每个测试前初始化"""
        self.manager = SessionManager(default_ttl=60)

    def test_create_session_success(self):
        """测试创建会话成功"""
        session = self.manager.create_session(
            user_id="user_001",
            initial_query="你好",
        )

        assert session.session_id is not None
        assert session.user_id == "user_001"
        assert session.status == SessionStatus.ACTIVE
        assert len(session.messages) == 1
        assert session.messages[0].content == "你好"

    def test_get_session_exists(self):
        """测试获取存在的会话"""
        session = self.manager.create_session("user_001", "测试")
        retrieved = self.manager.get_session(session.session_id)

        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_get_session_not_exists(self):
        """测试获取不存在的会话"""
        retrieved = self.manager.get_session("non_existent_id")
        assert retrieved is None

    def test_update_session_state(self):
        """测试更新会话状态"""
        session = self.manager.create_session("user_001", "测试")

        result = self.manager.update_session(
            session.session_id,
            state={"key": "value"},
        )

        assert result is True
        updated = self.manager.get_session(session.session_id)
        assert updated.state["key"] == "value"

    def test_add_message(self):
        """测试添加消息"""
        session = self.manager.create_session("user_001", "第一条")

        self.manager.add_message(
            session.session_id,
            role="assistant",
            content="回复内容",
        )

        updated = self.manager.get_session(session.session_id)
        assert len(updated.messages) == 2
        assert updated.messages[1].role == "assistant"
        assert updated.messages[1].content == "回复内容"

    def test_wait_for_input(self):
        """测试等待用户输入"""
        session = self.manager.create_session("user_001", "测试")

        result = self.manager.wait_for_input(
            session.session_id,
            prompt="请输入更多信息",
        )

        assert result is True
        updated = self.manager.get_session(session.session_id)
        assert updated.status == SessionStatus.WAITING_INPUT
        assert updated.waiting_prompt == "请输入更多信息"

    def test_resume_session(self):
        """测试恢复会话"""
        session = self.manager.create_session("user_001", "测试")
        self.manager.wait_for_input(session.session_id, "请输入")

        result = self.manager.resume_session(session.session_id, "用户输入")

        assert result is True
        updated = self.manager.get_session(session.session_id)
        assert updated.status == SessionStatus.ACTIVE
        assert updated.waiting_prompt is None
        assert len(updated.messages) == 2

    def test_resume_session_not_waiting(self):
        """测试恢复非等待状态的会话"""
        session = self.manager.create_session("user_001", "测试")

        result = self.manager.resume_session(session.session_id, "用户输入")

        assert result is False

    def test_complete_session(self):
        """测试完成会话"""
        session = self.manager.create_session("user_001", "测试")

        result = self.manager.complete_session(
            session.session_id,
            final_result="任务完成",
        )

        assert result is True
        updated = self.manager.get_session(session.session_id)
        assert updated.status == SessionStatus.COMPLETED

    def test_get_user_sessions(self):
        """测试获取用户会话列表"""
        self.manager.create_session("user_001", "会话1")
        self.manager.create_session("user_001", "会话2")
        self.manager.create_session("user_002", "其他用户")

        sessions = self.manager.get_user_sessions("user_001")

        assert len(sessions) == 2

    def test_get_conversation_history(self):
        """测试获取对话历史"""
        session = self.manager.create_session("user_001", "问题1")
        self.manager.add_message(session.session_id, "assistant", "回答1")
        self.manager.add_message(session.session_id, "user", "问题2")

        history = self.manager.get_conversation_history(session.session_id)

        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_cleanup_expired(self):
        """测试清理过期会话"""
        # 创建一个立即过期的管理器
        manager = SessionManager(default_ttl=-1)  # 负数TTL表示已过期
        session = manager.create_session("user_001", "测试")

        count = manager.cleanup_expired()
        assert count == 1

        # 会话应该被清理，get_session 返回 None 或状态为 EXPIRED
        result = manager.get_session(session.session_id)
        assert result is None or result.status == SessionStatus.EXPIRED
