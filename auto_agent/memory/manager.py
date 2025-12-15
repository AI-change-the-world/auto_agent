"""
全局 Memory 管理器

由 auto_agent 框架内部维护，用户只需传 user_id
自动处理记忆的创建、加载、持久化
"""

import os
from pathlib import Path
from typing import Dict, Optional

from auto_agent.memory.system import MemorySystem


class MemoryManager:
    """
    全局 Memory 管理器（单例模式）
    
    功能：
    - 按 user_id 管理 MemorySystem 实例
    - 自动创建/加载用户记忆
    - 提供统一的增删改查接口
    - 支持配置存储路径
    """
    
    _instance: Optional["MemoryManager"] = None
    
    def __init__(
        self,
        storage_base_path: str = "./auto_agent_memory",
        auto_save: bool = True,
        token_budget: int = 2000,
    ):
        self._storage_base_path = Path(storage_base_path)
        self._auto_save = auto_save
        self._token_budget = token_budget
        self._user_memories: Dict[str, MemorySystem] = {}
        
        # 确保存储目录存在
        self._storage_base_path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def get_instance(
        cls,
        storage_base_path: str = "./auto_agent_memory",
        **kwargs,
    ) -> "MemoryManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(storage_base_path=storage_base_path, **kwargs)
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        storage_base_path: str = "./auto_agent_memory",
        auto_save: bool = True,
        token_budget: int = 2000,
    ):
        """配置全局 Memory 管理器"""
        cls._instance = cls(
            storage_base_path=storage_base_path,
            auto_save=auto_save,
            token_budget=token_budget,
        )
        return cls._instance
    
    def get_memory_system(self, user_id: str) -> MemorySystem:
        """
        获取用户的 MemorySystem
        
        如果不存在则自动创建
        """
        if user_id not in self._user_memories:
            user_storage_path = self._storage_base_path / user_id
            self._user_memories[user_id] = MemorySystem(
                storage_path=str(user_storage_path),
                auto_save=self._auto_save,
                token_budget=self._token_budget,
            )
        return self._user_memories[user_id]
    
    def has_user(self, user_id: str) -> bool:
        """检查用户是否有记忆"""
        # 检查内存中
        if user_id in self._user_memories:
            return True
        # 检查磁盘
        user_path = self._storage_base_path / user_id
        return user_path.exists()
    
    def list_users(self) -> list:
        """列出所有有记忆的用户"""
        users = set(self._user_memories.keys())
        # 扫描磁盘
        if self._storage_base_path.exists():
            for p in self._storage_base_path.iterdir():
                if p.is_dir():
                    users.add(p.name)
        return list(users)
    
    def delete_user_memory(self, user_id: str) -> bool:
        """删除用户的所有记忆"""
        # 从内存中移除
        if user_id in self._user_memories:
            del self._user_memories[user_id]
        
        # 从磁盘删除
        user_path = self._storage_base_path / user_id
        if user_path.exists():
            import shutil
            shutil.rmtree(user_path)
            return True
        return False
    
    def get_user_stats(self, user_id: str) -> dict:
        """获取用户记忆统计"""
        ms = self.get_memory_system(user_id)
        return ms.get_stats(user_id)


# 全局实例（延迟初始化）
_global_manager: Optional[MemoryManager] = None


def get_memory_manager(storage_base_path: str = "./auto_agent_memory") -> MemoryManager:
    """获取全局 Memory 管理器"""
    global _global_manager
    if _global_manager is None:
        _global_manager = MemoryManager(storage_base_path=storage_base_path)
    return _global_manager


def configure_memory(
    storage_base_path: str = "./auto_agent_memory",
    auto_save: bool = True,
    token_budget: int = 2000,
) -> MemoryManager:
    """配置全局 Memory 管理器"""
    global _global_manager
    _global_manager = MemoryManager(
        storage_base_path=storage_base_path,
        auto_save=auto_save,
        token_budget=token_budget,
    )
    return _global_manager


def get_user_memory(user_id: str) -> MemorySystem:
    """获取用户的 MemorySystem（便捷方法）"""
    return get_memory_manager().get_memory_system(user_id)
