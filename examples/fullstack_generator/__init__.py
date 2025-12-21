"""
全栈项目生成器 Demo

用于测试 auto-agent 的跨步骤智能重规划功能：
- 任务复杂度分级
- 工作记忆 (CrossStepWorkingMemory)
- 全局一致性检查 (GlobalConsistencyChecker)
- 增量重规划
- 统一后处理策略 (ToolPostPolicy)

场景：生成一个完整的 REST API 项目
1. 需求分析 -> 提取实体和关系
2. API 设计 -> 定义端点和接口
3. 数据模型生成 -> 生成 Pydantic 模型
4. 服务层实现 -> 实现业务逻辑
5. 路由层实现 -> 实现 FastAPI 路由
6. 测试用例生成 -> 生成单元测试

每个步骤都会：
- 注册一致性检查点
- 提取工作记忆（设计决策、约束、接口定义）
- 检查与前序步骤的一致性
"""

from .runner import FullstackGeneratorRunner
from .tools import (
    AnalyzeRequirementsTool,
    DesignAPITool,
    GenerateModelsTool,
    GenerateRouterTool,
    GenerateServiceTool,
    GenerateTestsTool,
    ValidateProjectTool,
)
from .tools_writer import CodeWriterTool, ProjectInitTool

__all__ = [
    "AnalyzeRequirementsTool",
    "DesignAPITool",
    "GenerateModelsTool",
    "GenerateServiceTool",
    "GenerateRouterTool",
    "GenerateTestsTool",
    "ValidateProjectTool",
    "CodeWriterTool",
    "ProjectInitTool",
    "FullstackGeneratorRunner",
]
