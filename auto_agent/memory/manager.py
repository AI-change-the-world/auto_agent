"""
Memory 便捷函数

注意：推荐直接使用 MemorySystem 类，而不是这些全局函数。
ExecutionEngine 会自动创建和管理 MemorySystem。

这些函数仅用于：
- 独立使用记忆系统（不通过 ExecutionEngine）
- 测试和调试
"""

from pathlib import Path
from typing import Any, Optional

from auto_agent.memory.system import MemorySystem


def create_memory_system(
    user_id: str,
    storage_base_path: str = "./auto_agent_memory",
    llm_client: Optional[Any] = None,
    auto_save: bool = True,
    token_budget: int = 2000,
) -> MemorySystem:
    """
    创建用户的 MemorySystem
    
    推荐：直接使用 MemorySystem 类
    
    Args:
        user_id: 用户 ID
        storage_base_path: 存储根路径
        llm_client: LLM 客户端（用于智能记忆检索）
        auto_save: 是否自动保存
        token_budget: 默认 Token 预算
    
    Returns:
        MemorySystem 实例
    """
    storage_path = Path(storage_base_path) / user_id
    storage_path.mkdir(parents=True, exist_ok=True)
    
    return MemorySystem(
        storage_path=str(storage_path),
        auto_save=auto_save,
        token_budget=token_budget,
        llm_client=llm_client,
    )
