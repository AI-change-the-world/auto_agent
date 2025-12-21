"""
Execution Engine（执行引擎）

此文件已重构为模块化结构，实际实现位于 auto_agent/core/executor/ 目录下。

模块结构：
- base.py: ExecutionEngine 核心执行逻辑
- param_builder.py: 参数构造（绑定解析、LLM 推理、验证）
- replan.py: 重规划（模式检测、增量重规划）
- consistency.py: 一致性检查
- post_policy.py: 后处理策略
- state.py: 状态管理

此文件保留用于向后兼容，所有导入都从新模块重新导出。
"""

# 从新模块导入并重新导出
from auto_agent.core.executor.base import ExecutionEngine, ExecutionPattern, PatternType
from auto_agent.core.executor.consistency import ConsistencyManager
from auto_agent.core.executor.param_builder import ParameterBuilder
from auto_agent.core.executor.post_policy import PostPolicyManager
from auto_agent.core.executor.replan import ReplanManager
from auto_agent.core.executor.state import (
    compress_state_for_llm,
    get_nested_value,
    update_state_from_result,
)

__all__ = [
    # 主要类
    "ExecutionEngine",
    "ExecutionPattern",
    "PatternType",
    # 子模块类
    "ParameterBuilder",
    "ReplanManager",
    "ConsistencyManager",
    "PostPolicyManager",
    # 工具函数
    "get_nested_value",
    "compress_state_for_llm",
    "update_state_from_result",
]
