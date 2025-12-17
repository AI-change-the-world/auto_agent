"""
长期记忆（Long-term Memory）（已弃用）

基于 Markdown 文件存储，每个用户一个文件

.. deprecated::
    此模块已弃用，请使用新的 L1/L2/L3 三层记忆架构：
    - auto_agent.memory.system.MemorySystem（统一入口）
    - auto_agent.memory.semantic.SemanticMemory（L2 长期语义记忆）
"""

import warnings
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List

from auto_agent.memory.base import BaseMemory
from auto_agent.memory.models import UserMemory


def _deprecated_class(cls):
    """类弃用装饰器"""
    original_init = cls.__init__

    @wraps(original_init)
    def new_init(self, *args, **kwargs):
        warnings.warn(
            f"{cls.__name__} 已弃用，请使用 MemorySystem 或 SemanticMemory 替代。"
            f"参见 auto_agent.memory.system.MemorySystem",
            DeprecationWarning,
            stacklevel=2,
        )
        original_init(self, *args, **kwargs)

    cls.__init__ = new_init
    return cls


@_deprecated_class
class LongTermMemory(BaseMemory):
    """
    长期记忆（已弃用）

    .. deprecated::
        此类已弃用，请使用 MemorySystem 或 SemanticMemory 替代。

        迁移指南：
        - LongTermMemory.add_fact() -> MemorySystem.add_knowledge()
        - LongTermMemory.search_memory() -> MemorySystem.search_memory()
        - LongTermMemory.get_relevant_context() -> MemorySystem.get_context_for_query()

    存储格式：Markdown 文件
    存储位置：{storage_path}/{user_id}/memory.md
    """

    def __init__(self, storage_path: str = "./data/memories"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _get_user_file(self, user_id: str) -> Path:
        """获取用户记忆文件路径"""
        user_dir = self.storage_path / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / "memory.md"

    def load(self, user_id: str) -> str:
        """加载用户记忆"""
        file_path = self._get_user_file(user_id)
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return self._create_default_memory(user_id)

    def save(self, user_id: str, content: str) -> None:
        """保存用户记忆"""
        file_path = self._get_user_file(user_id)
        file_path.write_text(content, encoding="utf-8")

    def update(self, user_id: str, updates: Dict[str, Any]) -> None:
        """更新用户记忆"""
        content = self.load(user_id)
        # 简单实现：追加更新内容
        update_lines = [f"- {k}: {v}" for k, v in updates.items()]
        content += "\n\n## 更新记录\n" + "\n".join(update_lines)
        self.save(user_id, content)

    def delete(self, user_id: str) -> None:
        """删除用户记忆"""
        file_path = self._get_user_file(user_id)
        if file_path.exists():
            file_path.unlink()

    def load_user_memory(self, user_id: str) -> UserMemory:
        """加载用户记忆对象"""
        # 简化实现：返回空对象
        return UserMemory(user_id=user_id)

    def save_user_memory(self, user_id: str, memory: UserMemory) -> None:
        """保存用户记忆对象"""
        # TODO: 将 UserMemory 序列化为 Markdown
        pass

    def update_user_memory(self, user_id: str, updates: Dict[str, Any]) -> None:
        """更新用户记忆"""
        self.update(user_id, updates)

    def search_memory(self, user_id: str, query: str) -> List[str]:
        """搜索记忆"""
        content = self.load(user_id)
        # 简单实现：返回包含查询词的行
        lines = content.split("\n")
        return [line for line in lines if query.lower() in line.lower()]

    def add_fact(self, user_id: str, fact: str, category: str = "facts") -> None:
        """添加事实"""
        content = self.load(user_id)
        content += f"\n\n## {category}\n- {fact}"
        self.save(user_id, content)

    def get_relevant_context(self, user_id: str, task: str) -> str:
        """获取相关上下文"""
        # 简单实现：返回全部内容
        return self.load(user_id)

    def _create_default_memory(self, user_id: str) -> str:
        """创建默认记忆模板"""
        return f"""# User Profile: {user_id}

## Basic Information
- User ID: {user_id}
- Created At: {self._get_timestamp()}
- Last Updated: {self._get_timestamp()}

## Preferences
- Language: zh-CN
- Response Style: detailed

## Knowledge Base

## Interaction History

## Custom Context
"""

    def _get_timestamp(self) -> str:
        from datetime import datetime

        return datetime.now().isoformat()
