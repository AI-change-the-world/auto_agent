"""
公共数据模型

包含 Agent 执行过程中需要的所有核心数据结构
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ==================== 验证模式枚举 ====================


class ValidationMode(Enum):
    """验证模式枚举"""

    NONE = "none"  # 不校验
    LOOSE = "loose"  # 宽松模式
    STRICT = "strict"  # 严格模式


# ==================== 消息模型 ====================


@dataclass
class Message:
    """消息模型"""

    role: str  # user/assistant/system/tool
    content: str
    timestamp: int
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== 执行计划模型 ====================


@dataclass
class PlanStep:
    """
    执行计划步骤

    核心改进：
    - 支持自然语言期望描述
    - 支持失败策略定义
    - 支持固定步骤标记
    """

    id: str
    description: str
    tool: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    # 自然语言期望（如 "检索到至少5个文档"）
    expectations: Optional[str] = None

    # 失败策略（如 "重试最多3次"、"回退到步骤2"）
    on_fail_strategy: Optional[str] = None

    # 读写字段声明
    read_fields: List[str] = field(default_factory=list)
    write_fields: List[str] = field(default_factory=list)

    # 固定步骤支持
    is_pinned: bool = False
    pinned_parameters: Optional[Dict[str, Any]] = None
    parameter_template: Optional[Dict[str, Any]] = None
    template_variables: Optional[Dict[str, str]] = None


@dataclass
class ExecutionPlan:
    """执行计划"""

    intent: str
    subtasks: List[PlanStep] = field(default_factory=list)
    expected_outcome: Optional[str] = None
    state_schema: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ==================== 执行结果模型 ====================


@dataclass
class SubTaskResult:
    """子任务执行结果"""

    step_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 期望验证结果
    expectation_failed: bool = False
    evaluation_reason: Optional[str] = None

    # LLM 调用记录
    llm_calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentResponse:
    """Agent 响应"""

    content: str
    conversation_id: str
    plan: ExecutionPlan
    execution_results: List[SubTaskResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 执行统计
    iterations: int = 0
    record_id: Optional[str] = None


# ==================== 失败策略动作 ====================


@dataclass
class FailAction:
    """失败策略解析结果"""

    type: str  # retry / goto / fallback / abort
    target_step: Optional[str] = None
    max_retries: int = 3
    reason: Optional[str] = None


# ==================== 工具定义增强 ====================


@dataclass
class ToolParameter:
    """工具参数"""

    name: str
    type: str  # string, number, boolean, object, array
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[Any]] = None


@dataclass
class ToolDefinition:
    """
    工具定义（增强版）

    支持：
    - validate_function: 自定义验证函数
    - compress_function: 自定义结果压缩函数
    """

    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    returns: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    output_schema: Optional[Dict[str, Any]] = None

    # 验证函数：(result, expectations, state, mode: ValidationMode, llm_client, db) -> (passed, reason)
    validate_function: Optional[Callable] = None

    # 压缩函数：(result, state) -> compressed_result
    compress_function: Optional[Callable] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "enum": p.enum,
                }
                for p in self.parameters
            ],
            "returns": self.returns,
            "category": self.category,
            "tags": self.tags,
            "examples": self.examples,
            "output_schema": self.output_schema,
        }

    def to_openai_schema(self) -> Dict[str, Any]:
        """转换为 OpenAI function calling 格式"""
        properties = {}
        required = []

        for p in self.parameters:
            properties[p.name] = {
                "type": p.type,
                "description": p.description,
            }
            if p.enum:
                properties[p.name]["enum"] = p.enum
            if p.default is not None:
                properties[p.name]["default"] = p.default
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
