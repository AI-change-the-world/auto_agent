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


# ==================== 任务复杂度分级 ====================


class TaskComplexity(Enum):
    """任务复杂度等级"""

    SIMPLE = "simple"  # 单步或线性任务（查天气、算数）
    MODERATE = "moderate"  # 多步但独立（搜索+总结）
    COMPLEX = "complex"  # 多步且有依赖（研究报告）
    PROJECT = "project"  # 项目级（写完整项目、重构代码库）


@dataclass
class TaskProfile:
    """
    任务画像

    在规划阶段由 LLM 分析用户输入生成，用于决定后续执行策略
    """

    complexity: TaskComplexity
    estimated_steps: int
    has_code_generation: bool  # 是否涉及代码生成
    has_cross_dependencies: bool  # 步骤间是否有交叉依赖
    requires_consistency: bool  # 是否需要一致性保证（如接口定义）
    is_reversible: bool  # 错误是否容易回滚
    reasoning: str = ""  # LLM 的判断理由

    def to_dict(self) -> Dict[str, Any]:
        return {
            "complexity": self.complexity.value,
            "estimated_steps": self.estimated_steps,
            "has_code_generation": self.has_code_generation,
            "has_cross_dependencies": self.has_cross_dependencies,
            "requires_consistency": self.requires_consistency,
            "is_reversible": self.is_reversible,
            "reasoning": self.reasoning,
        }


@dataclass
class ExecutionStrategy:
    """
    执行策略

    根据 TaskProfile 决定的全局执行策略
    """

    # Replan 相关
    enable_replan: bool = True
    replan_trigger: str = "on_failure"  # "on_failure" / "periodic" / "proactive"
    replan_interval: int = 5  # 周期性检查间隔（仅 periodic 模式）

    # 一致性检查相关
    enable_consistency_check: bool = False
    consistency_check_on: List[str] = field(
        default_factory=list
    )  # ["code_generation", "interface_definition"]

    # 前瞻规划
    enable_lookahead: bool = False

    # 检查点
    checkpoint_interval: int = 0  # 0 表示不设检查点

    # 阶段审查（仅 PROJECT 级）
    require_phase_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enable_replan": self.enable_replan,
            "replan_trigger": self.replan_trigger,
            "replan_interval": self.replan_interval,
            "enable_consistency_check": self.enable_consistency_check,
            "consistency_check_on": self.consistency_check_on,
            "enable_lookahead": self.enable_lookahead,
            "checkpoint_interval": self.checkpoint_interval,
            "require_phase_review": self.require_phase_review,
        }


# ==================== 工具级 Replan 策略 ====================


@dataclass
class ToolReplanPolicy:
    """
    工具级别的 Replan 策略

    允许每个工具定义自己的后处理策略，覆盖全局策略
    """

    # 执行后是否强制触发 replan 检查
    force_replan_check: bool = False

    # 执行后是否需要一致性验证
    requires_consistency_check: bool = False

    # 这个工具的输出是否会影响后续多个步骤（高影响力工具）
    high_impact: bool = False

    # 自定义的 replan 触发条件（自然语言，让 LLM 判断）
    # 例: "如果生成的代码超过 100 行，或涉及多个文件"
    replan_condition: Optional[str] = None

    # 需要与哪些类型的历史步骤做一致性检查
    # 例: ["interface_definition", "schema_design"]
    consistency_check_against: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "force_replan_check": self.force_replan_check,
            "requires_consistency_check": self.requires_consistency_check,
            "high_impact": self.high_impact,
            "replan_condition": self.replan_condition,
            "consistency_check_against": self.consistency_check_against,
        }


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

    # 任务画像和执行策略（阶段一新增）
    task_profile: Optional["TaskProfile"] = None
    execution_strategy: Optional["ExecutionStrategy"] = None


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


# ==================== 错误恢复配置 ====================


@dataclass
class ErrorRecoveryStrategy:
    """
    错误恢复策略配置

    用于定义工具执行失败时的恢复策略

    Attributes:
        error_pattern: 错误匹配模式（正则表达式）
        recovery_action: 恢复动作类型
            - "retry_with_fix": 修正参数后重试
            - "use_alternative": 使用替代工具
            - "skip": 跳过当前步骤
            - "abort": 中止执行
        fix_suggestion: 修正建议（供 LLM 参考）
        max_attempts: 最大尝试次数
    """

    error_pattern: str  # 错误匹配模式（正则表达式）
    recovery_action: (
        str  # 恢复动作: "retry_with_fix", "use_alternative", "skip", "abort"
    )
    fix_suggestion: Optional[str] = None  # 修正建议（供 LLM 参考）
    max_attempts: int = 3

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "error_pattern": self.error_pattern,
            "recovery_action": self.recovery_action,
            "fix_suggestion": self.fix_suggestion,
            "max_attempts": self.max_attempts,
        }


@dataclass
class ParameterValidator:
    """
    参数验证器

    用于在工具执行前验证参数有效性

    Attributes:
        parameter_name: 要验证的参数名称
        validation_type: 验证类型
            - "regex": 正则表达式匹配
            - "range": 数值范围检查
            - "enum": 枚举值检查
            - "custom": 自定义验证
        validation_rule: 验证规则
            - regex: 正则表达式字符串
            - range: "min,max" 格式的范围
            - enum: 逗号分隔的有效值列表
            - custom: 自定义验证函数名
        error_message: 验证失败时的错误消息
    """

    parameter_name: str
    validation_type: str  # "regex", "range", "enum", "custom"
    validation_rule: str
    error_message: str

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "parameter_name": self.parameter_name,
            "validation_type": self.validation_type,
            "validation_rule": self.validation_rule,
            "error_message": self.error_message,
        }


# ==================== 工具定义增强 ====================


@dataclass
class StepResultData:
    """
    步骤执行结果的结构化数据

    用于 LLM 语义理解参数映射，每个步骤执行后生成此结构

    Attributes:
        step_id: 步骤 ID
        tool_name: 工具名称
        target: 这一步的目标（简短描述）
        description: 对结果/过程的语义描述（供 LLM 判断相关性）
        input_data: 输入数据结构
        output_data: 输出数据结构
        success: 是否成功
        error: 错误信息（如果失败）
    """

    step_id: str
    tool_name: str
    target: str  # 这一步的目标，如 "查找相关文档"
    description: str  # 语义描述，如 "找到了3个文档，相关性分别是0.9/0.8/0.7"
    input_data: Dict[str, Any] = field(
        default_factory=dict
    )  # {"type": "list", "value": [...]}
    output_data: Dict[str, Any] = field(
        default_factory=dict
    )  # {"type": "dict", "value": {...}}
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "target": self.target,
            "description": self.description,
            "input": self.input_data,
            "output": self.output_data,
            "success": self.success,
            "error": self.error,
        }

    def to_llm_summary(self) -> str:
        """生成供 LLM 理解的摘要"""
        status = "✓" if self.success else f"✗ ({self.error})"
        return f"[{self.tool_name}] {status} 目标: {self.target} | 结果: {self.description}"


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

    # 参数别名映射：{param_name: state_field_name}
    # 例如 {"input_text": "query"} 表示从 state["query"] 读取值赋给 input_text 参数
    #
    # ⚠️ DEPRECATED: 此参数将在未来版本中移除
    # 推荐使用 LLM 语义理解自动完成参数映射，而不是手动定义别名
    # 新的参数构造机制会基于 StepResultData 的 description 字段进行语义匹配
    param_aliases: Dict[str, str] = field(default_factory=dict)

    # 状态写入映射：{result_field: state_field}
    # 例如 {"search_query": "search_queries"} 表示将 result["search_query"] 写入 state["search_queries"]
    state_mapping: Dict[str, str] = field(default_factory=dict)

    # Prompt 模板：用于 LLM 动态生成工具调用 prompt
    # 支持 {变量名} 占位符，变量从 ExecutionContext.state 中获取
    # 例如 "根据以下大纲 {outline} 和用户需求 {inputs.query}，生成一份专业的 {document_type}"
    prompt_template: Optional[str] = None

    # 是否启用动态 prompt 生成（让 LLM 根据上下文自动生成 prompt）
    dynamic_prompt: bool = False

    # === 错误恢复配置（新增） ===

    # 错误恢复策略列表：定义不同错误类型的恢复策略
    error_recovery_strategies: List["ErrorRecoveryStrategy"] = field(
        default_factory=list
    )

    # 替代工具列表：当本工具失败时可尝试的替代方案
    alternative_tools: List[str] = field(default_factory=list)

    # 参数验证器列表：在执行前验证参数有效性
    parameter_validators: List["ParameterValidator"] = field(default_factory=list)

    # === 工具级 Replan 策略 ===
    replan_policy: Optional["ToolReplanPolicy"] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
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

        # 添加错误恢复配置（仅当有配置时）
        if self.error_recovery_strategies:
            result["error_recovery_strategies"] = [
                s.to_dict() for s in self.error_recovery_strategies
            ]

        if self.alternative_tools:
            result["alternative_tools"] = self.alternative_tools

        if self.parameter_validators:
            result["parameter_validators"] = [
                v.to_dict() for v in self.parameter_validators
            ]

        return result

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
