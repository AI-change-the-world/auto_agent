"""
记忆基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseMemory(ABC):
    """记忆基类"""

    @abstractmethod
    def load(self, key: str) -> Any:
        """加载记忆"""
        pass

    @abstractmethod
    def save(self, key: str, value: Any) -> None:
        """保存记忆"""
        pass

    @abstractmethod
    def update(self, key: str, updates: Dict[str, Any]) -> None:
        """更新记忆"""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除记忆"""
        pass
