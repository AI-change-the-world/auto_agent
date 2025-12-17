"""
分类记忆系统（已弃用）

支持:
- KV 键值对存储
- 分类管理（用户反馈、行为模式、偏好等）
- 全文检索
- 记忆过期和清理

.. deprecated::
    此模块已弃用，请使用新的 L1/L2/L3 三层记忆架构：
    - auto_agent.memory.system.MemorySystem（统一入口）
    - auto_agent.memory.semantic.SemanticMemory（L2 长期语义记忆）
    - auto_agent.memory.working.WorkingMemory（L1 短时记忆）
    - auto_agent.memory.narrative.NarrativeMemoryManager（L3 叙事记忆）
"""

import json
import re
import time
import warnings
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional


def _deprecated_class(cls):
    """类弃用装饰器"""
    original_init = cls.__init__

    @wraps(original_init)
    def new_init(self, *args, **kwargs):
        warnings.warn(
            f"{cls.__name__} 已弃用，请使用 MemorySystem 替代。"
            f"参见 auto_agent.memory.system.MemorySystem",
            DeprecationWarning,
            stacklevel=2,
        )
        original_init(self, *args, **kwargs)

    cls.__init__ = new_init
    return cls


class MemoryCategory(Enum):
    """记忆分类"""

    USER_FEEDBACK = "user_feedback"  # 用户反馈
    BEHAVIOR_PATTERN = "behavior_pattern"  # 行为模式
    PREFERENCE = "preference"  # 用户偏好
    KNOWLEDGE = "knowledge"  # 知识/事实
    CONTEXT = "context"  # 上下文信息
    TASK_HISTORY = "task_history"  # 任务历史
    CUSTOM = "custom"  # 自定义


@dataclass
class MemoryItem:
    """记忆条目"""

    key: str
    value: Any
    category: MemoryCategory
    created_at: int
    updated_at: int
    expires_at: Optional[int] = None  # None 表示永不过期
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return int(time.time()) > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "category": self.category.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        return cls(
            key=data["key"],
            value=data["value"],
            category=MemoryCategory(data["category"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            expires_at=data.get("expires_at"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


@_deprecated_class
class CategorizedMemory:
    """
    分类记忆系统（已弃用）

    .. deprecated::
        此类已弃用，请使用 MemorySystem 替代。

        迁移指南：
        - CategorizedMemory.set_preference() -> MemorySystem.set_preference()
        - CategorizedMemory.add_knowledge() -> MemorySystem.add_knowledge()
        - CategorizedMemory.search() -> MemorySystem.search_memory()
        - CategorizedMemory.get_context_summary() -> MemorySystem.get_context_summary()

    特性:
    1. KV 键值对存储
    2. 按分类管理记忆
    3. 全文检索支持
    4. 持久化存储
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        auto_save: bool = True,
    ):
        self._memories: Dict[
            str, Dict[str, MemoryItem]
        ] = {}  # user_id -> {key -> item}
        self._storage_path = Path(storage_path) if storage_path else None
        self._auto_save = auto_save

        if self._storage_path:
            self._storage_path.mkdir(parents=True, exist_ok=True)

    def set(
        self,
        user_id: str,
        key: str,
        value: Any,
        category: MemoryCategory = MemoryCategory.CUSTOM,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        """设置记忆"""
        current_time = int(time.time())

        if user_id not in self._memories:
            self._memories[user_id] = {}

        item = MemoryItem(
            key=key,
            value=value,
            category=category,
            created_at=current_time,
            updated_at=current_time,
            expires_at=current_time + ttl if ttl else None,
            tags=tags or [],
            metadata=metadata or {},
        )

        self._memories[user_id][key] = item

        if self._auto_save and self._storage_path:
            self._save_user(user_id)

        return item

    def get(self, user_id: str, key: str) -> Optional[Any]:
        """获取记忆值"""
        item = self.get_item(user_id, key)
        return item.value if item else None

    def get_item(self, user_id: str, key: str) -> Optional[MemoryItem]:
        """获取记忆条目"""
        if user_id not in self._memories:
            self._load_user(user_id)

        item = self._memories.get(user_id, {}).get(key)
        if item and item.is_expired():
            self.delete(user_id, key)
            return None
        return item

    def delete(self, user_id: str, key: str) -> bool:
        """删除记忆"""
        if user_id in self._memories and key in self._memories[user_id]:
            del self._memories[user_id][key]
            if self._auto_save and self._storage_path:
                self._save_user(user_id)
            return True
        return False

    def get_by_category(
        self,
        user_id: str,
        category: MemoryCategory,
        limit: int = 100,
    ) -> List[MemoryItem]:
        """按分类获取记忆"""
        if user_id not in self._memories:
            self._load_user(user_id)

        items = [
            item
            for item in self._memories.get(user_id, {}).values()
            if item.category == category and not item.is_expired()
        ]
        items.sort(key=lambda x: x.updated_at, reverse=True)
        return items[:limit]

    def get_by_tags(
        self,
        user_id: str,
        tags: List[str],
        match_all: bool = False,
    ) -> List[MemoryItem]:
        """按标签获取记忆"""
        if user_id not in self._memories:
            self._load_user(user_id)

        results = []
        for item in self._memories.get(user_id, {}).values():
            if item.is_expired():
                continue
            if match_all:
                if all(tag in item.tags for tag in tags):
                    results.append(item)
            else:
                if any(tag in item.tags for tag in tags):
                    results.append(item)
        return results

    def search(
        self,
        user_id: str,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 20,
    ) -> List[MemoryItem]:
        """全文检索"""
        if user_id not in self._memories:
            self._load_user(user_id)

        query_lower = query.lower()
        query_words = set(re.findall(r"\w+", query_lower))
        results = []

        for item in self._memories.get(user_id, {}).values():
            if item.is_expired():
                continue
            if category and item.category != category:
                continue

            # 计算匹配分数
            score = 0
            searchable = f"{item.key} {json.dumps(item.value, ensure_ascii=False)} {' '.join(item.tags)}"
            searchable_lower = searchable.lower()

            # 完整匹配
            if query_lower in searchable_lower:
                score += 10

            # 词匹配
            for word in query_words:
                if word in searchable_lower:
                    score += 1

            if score > 0:
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def get_all(self, user_id: str) -> Dict[str, MemoryItem]:
        """获取用户所有记忆"""
        if user_id not in self._memories:
            self._load_user(user_id)
        return {
            k: v
            for k, v in self._memories.get(user_id, {}).items()
            if not v.is_expired()
        }

    def cleanup_expired(self, user_id: str) -> int:
        """清理过期记忆"""
        if user_id not in self._memories:
            return 0

        expired_keys = [
            key for key, item in self._memories[user_id].items() if item.is_expired()
        ]

        for key in expired_keys:
            del self._memories[user_id][key]

        if expired_keys and self._auto_save and self._storage_path:
            self._save_user(user_id)

        return len(expired_keys)

    # ==================== 便捷方法 ====================

    def add_feedback(
        self,
        user_id: str,
        feedback: str,
        context: Optional[str] = None,
        rating: Optional[int] = None,
    ) -> MemoryItem:
        """添加用户反馈"""
        key = f"feedback_{int(time.time())}"
        return self.set(
            user_id=user_id,
            key=key,
            value={
                "feedback": feedback,
                "context": context,
                "rating": rating,
            },
            category=MemoryCategory.USER_FEEDBACK,
            tags=["feedback"],
        )

    def add_behavior(
        self,
        user_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        """记录用户行为"""
        key = f"behavior_{int(time.time())}"
        return self.set(
            user_id=user_id,
            key=key,
            value={
                "action": action,
                "details": details or {},
            },
            category=MemoryCategory.BEHAVIOR_PATTERN,
            tags=["behavior", action],
        )

    def set_preference(
        self,
        user_id: str,
        pref_key: str,
        pref_value: Any,
    ) -> MemoryItem:
        """设置用户偏好"""
        return self.set(
            user_id=user_id,
            key=f"pref_{pref_key}",
            value=pref_value,
            category=MemoryCategory.PREFERENCE,
            tags=["preference", pref_key],
        )

    def get_preference(self, user_id: str, pref_key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        value = self.get(user_id, f"pref_{pref_key}")
        return value if value is not None else default

    def add_knowledge(
        self,
        user_id: str,
        fact: str,
        source: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> MemoryItem:
        """添加知识/事实"""
        key = f"knowledge_{int(time.time())}"
        return self.set(
            user_id=user_id,
            key=key,
            value={
                "fact": fact,
                "source": source,
            },
            category=MemoryCategory.KNOWLEDGE,
            tags=["knowledge"] + (tags or []),
        )

    # ==================== 持久化 ====================

    def _get_user_file(self, user_id: str) -> Path:
        return self._storage_path / f"{user_id}.json"

    def _save_user(self, user_id: str):
        """保存用户记忆到文件"""
        if not self._storage_path:
            return

        file_path = self._get_user_file(user_id)
        data = {
            key: item.to_dict() for key, item in self._memories.get(user_id, {}).items()
        }
        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _load_user(self, user_id: str):
        """从文件加载用户记忆"""
        if not self._storage_path:
            self._memories[user_id] = {}
            return

        file_path = self._get_user_file(user_id)
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text())
                self._memories[user_id] = {
                    key: MemoryItem.from_dict(item_data)
                    for key, item_data in data.items()
                }
            except Exception:
                self._memories[user_id] = {}
        else:
            self._memories[user_id] = {}

    def save_all(self):
        """保存所有用户记忆"""
        if not self._storage_path:
            return
        for user_id in self._memories:
            self._save_user(user_id)

    def get_context_summary(
        self,
        user_id: str,
        max_items: int = 10,
    ) -> str:
        """获取用户上下文摘要（用于 LLM）"""
        lines = []

        # 偏好
        prefs = self.get_by_category(user_id, MemoryCategory.PREFERENCE, limit=5)
        if prefs:
            lines.append("用户偏好:")
            for p in prefs:
                key = p.key.replace("pref_", "")
                lines.append(f"  - {key}: {p.value}")

        # 最近反馈
        feedbacks = self.get_by_category(user_id, MemoryCategory.USER_FEEDBACK, limit=3)
        if feedbacks:
            lines.append("最近反馈:")
            for f in feedbacks:
                lines.append(f"  - {f.value.get('feedback', '')[:100]}")

        # 知识
        knowledge = self.get_by_category(user_id, MemoryCategory.KNOWLEDGE, limit=5)
        if knowledge:
            lines.append("已知信息:")
            for k in knowledge:
                lines.append(f"  - {k.value.get('fact', '')[:100]}")

        return "\n".join(lines) if lines else "无用户上下文"
