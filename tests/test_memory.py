"""
分类记忆系统测试
"""

import tempfile
import time

import pytest

from auto_agent.memory.categorized import (
    CategorizedMemory,
    MemoryCategory,
    MemoryItem,
)


class TestCategorizedMemory:
    """分类记忆系统测试"""

    def setup_method(self):
        """每个测试前初始化"""
        self.memory = CategorizedMemory(storage_path=None, auto_save=False)

    def test_set_and_get(self):
        """测试设置和获取记忆"""
        self.memory.set(
            user_id="user_001",
            key="test_key",
            value="test_value",
        )

        result = self.memory.get("user_001", "test_key")
        assert result == "test_value"

    def test_get_not_exists(self):
        """测试获取不存在的记忆"""
        result = self.memory.get("user_001", "non_existent")
        assert result is None

    def test_set_with_category(self):
        """测试设置带分类的记忆"""
        item = self.memory.set(
            user_id="user_001",
            key="feedback_1",
            value="很好",
            category=MemoryCategory.USER_FEEDBACK,
        )

        assert item.category == MemoryCategory.USER_FEEDBACK

    def test_set_with_ttl_expired(self):
        """测试设置带过期时间的记忆"""
        self.memory.set(
            user_id="user_001",
            key="temp_key",
            value="temp_value",
            ttl=-1,  # 已过期（负数TTL）
        )

        result = self.memory.get("user_001", "temp_key")
        assert result is None

    def test_set_with_tags(self):
        """测试设置带标签的记忆"""
        item = self.memory.set(
            user_id="user_001",
            key="tagged_item",
            value="value",
            tags=["tag1", "tag2"],
        )

        assert "tag1" in item.tags
        assert "tag2" in item.tags

    def test_delete(self):
        """测试删除记忆"""
        self.memory.set("user_001", "to_delete", "value")

        result = self.memory.delete("user_001", "to_delete")
        assert result is True

        value = self.memory.get("user_001", "to_delete")
        assert value is None

    def test_delete_not_exists(self):
        """测试删除不存在的记忆"""
        result = self.memory.delete("user_001", "non_existent")
        assert result is False

    def test_get_by_category(self):
        """测试按分类获取记忆"""
        self.memory.set(
            "user_001", "fb1", "反馈1",
            category=MemoryCategory.USER_FEEDBACK,
        )
        self.memory.set(
            "user_001", "fb2", "反馈2",
            category=MemoryCategory.USER_FEEDBACK,
        )
        self.memory.set(
            "user_001", "pref1", "偏好1",
            category=MemoryCategory.PREFERENCE,
        )

        feedbacks = self.memory.get_by_category(
            "user_001",
            MemoryCategory.USER_FEEDBACK,
        )

        assert len(feedbacks) == 2

    def test_get_by_tags(self):
        """测试按标签获取记忆"""
        self.memory.set("user_001", "item1", "v1", tags=["a", "b"])
        self.memory.set("user_001", "item2", "v2", tags=["b", "c"])
        self.memory.set("user_001", "item3", "v3", tags=["c", "d"])

        # 任意匹配
        results = self.memory.get_by_tags("user_001", ["a", "c"])
        assert len(results) == 3

        # 全部匹配
        results = self.memory.get_by_tags("user_001", ["b", "c"], match_all=True)
        assert len(results) == 1

    def test_search(self):
        """测试全文检索"""
        self.memory.set("user_001", "doc1", "Python 编程入门")
        self.memory.set("user_001", "doc2", "Java 开发指南")
        self.memory.set("user_001", "doc3", "Python 高级技巧")

        results = self.memory.search("user_001", "Python")

        assert len(results) == 2

    def test_search_with_category(self):
        """测试带分类的全文检索"""
        self.memory.set(
            "user_001", "k1", {"fact": "Python 是编程语言"},
            category=MemoryCategory.KNOWLEDGE,
        )
        self.memory.set(
            "user_001", "f1", {"feedback": "Python 很好用"},
            category=MemoryCategory.USER_FEEDBACK,
        )

        results = self.memory.search(
            "user_001", "Python",
            category=MemoryCategory.KNOWLEDGE,
        )

        assert len(results) == 1

    def test_add_feedback(self):
        """测试添加用户反馈"""
        item = self.memory.add_feedback(
            user_id="user_001",
            feedback="服务很好",
            rating=5,
        )

        assert item.category == MemoryCategory.USER_FEEDBACK
        assert item.value["feedback"] == "服务很好"
        assert item.value["rating"] == 5

    def test_add_behavior(self):
        """测试记录用户行为"""
        item = self.memory.add_behavior(
            user_id="user_001",
            action="search",
            details={"query": "AI"},
        )

        assert item.category == MemoryCategory.BEHAVIOR_PATTERN
        assert item.value["action"] == "search"
        assert "behavior" in item.tags

    def test_set_and_get_preference(self):
        """测试设置和获取用户偏好"""
        self.memory.set_preference("user_001", "language", "zh-CN")

        result = self.memory.get_preference("user_001", "language")
        assert result == "zh-CN"

    def test_get_preference_default(self):
        """测试获取不存在的偏好返回默认值"""
        result = self.memory.get_preference("user_001", "theme", default="light")
        assert result == "light"

    def test_add_knowledge(self):
        """测试添加知识"""
        item = self.memory.add_knowledge(
            user_id="user_001",
            fact="地球是圆的",
            source="科学常识",
            tags=["地理"],
        )

        assert item.category == MemoryCategory.KNOWLEDGE
        assert item.value["fact"] == "地球是圆的"
        assert "地理" in item.tags

    def test_cleanup_expired(self):
        """测试清理过期记忆"""
        self.memory.set("user_001", "temp1", "v1", ttl=-1)  # 已过期
        self.memory.set("user_001", "temp2", "v2", ttl=-1)  # 已过期
        self.memory.set("user_001", "perm", "v3")  # 永不过期

        count = self.memory.cleanup_expired("user_001")

        assert count == 2
        assert self.memory.get("user_001", "perm") == "v3"

    def test_get_context_summary(self):
        """测试获取用户上下文摘要"""
        self.memory.set_preference("user_001", "language", "中文")
        self.memory.add_feedback("user_001", "很好用")
        self.memory.add_knowledge("user_001", "用户是开发者")

        summary = self.memory.get_context_summary("user_001")

        assert "用户偏好" in summary
        assert "language" in summary
        assert "最近反馈" in summary
        assert "已知信息" in summary

    def test_persistence(self):
        """测试持久化存储"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建并保存
            memory1 = CategorizedMemory(storage_path=tmpdir, auto_save=True)
            memory1.set("user_001", "key1", "value1")

            # 重新加载
            memory2 = CategorizedMemory(storage_path=tmpdir, auto_save=False)
            result = memory2.get("user_001", "key1")

            assert result == "value1"

    def test_memory_item_to_dict(self):
        """测试 MemoryItem 序列化"""
        item = MemoryItem(
            key="test",
            value="value",
            category=MemoryCategory.CUSTOM,
            created_at=1000,
            updated_at=1000,
            tags=["tag1"],
        )

        data = item.to_dict()

        assert data["key"] == "test"
        assert data["category"] == "custom"
        assert data["tags"] == ["tag1"]

    def test_memory_item_from_dict(self):
        """测试 MemoryItem 反序列化"""
        data = {
            "key": "test",
            "value": "value",
            "category": "preference",
            "created_at": 1000,
            "updated_at": 1000,
            "tags": ["tag1"],
        }

        item = MemoryItem.from_dict(data)

        assert item.key == "test"
        assert item.category == MemoryCategory.PREFERENCE
