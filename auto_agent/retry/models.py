"""
重试配置模型
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type


class RetryStrategy(str, Enum):
    """重试策略"""

    IMMEDIATE = "immediate"  # 立即重试
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 指数退避
    LINEAR_BACKOFF = "linear_backoff"  # 线性退避


class ErrorType(str, Enum):
    """错误类型枚举
    
    用于智能错误分析，根据错误类型选择合适的恢复策略。
    """

    PARAMETER_ERROR = "parameter_error"      # 参数错误（可通过修正参数恢复）
    NETWORK_ERROR = "network_error"          # 网络错误（可通过重试恢复）
    TIMEOUT_ERROR = "timeout_error"          # 超时错误（可通过重试恢复）
    RESOURCE_ERROR = "resource_error"        # 资源错误（需等待或切换资源）
    LOGIC_ERROR = "logic_error"              # 逻辑错误（需要重规划）
    DEPENDENCY_ERROR = "dependency_error"    # 依赖错误（需要解决依赖）
    PERMISSION_ERROR = "permission_error"    # 权限错误（通常不可恢复）
    UNKNOWN_ERROR = "unknown_error"          # 未知错误


@dataclass
class RetryConfig:
    """重试配置"""

    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0  # 秒
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    retry_on_exceptions: List[Type[Exception]] = field(default_factory=list)
    should_retry_callback: Optional[Callable] = None


@dataclass
class ParameterFix:
    """参数修正建议
    
    当错误类型为 PARAMETER_ERROR 时，LLM 分析会生成参数修正建议。
    """

    parameter_name: str  # 需要修正的参数名
    current_value: Any  # 当前参数值
    suggested_value: Any  # 建议的修正值
    fix_reason: str  # 修正原因说明
    confidence: float = 0.0  # 修正建议的置信度 (0.0-1.0)


@dataclass
class ErrorAnalysis:
    """LLM 错误分析结果
    
    包含错误类型识别、可恢复性评估和修正建议。
    """

    error_type: ErrorType  # 错误类型
    is_recoverable: bool  # 是否可恢复
    root_cause: str  # 根本原因分析
    suggested_fixes: List[ParameterFix] = field(default_factory=list)  # 参数修正建议列表
    retry_strategy: Optional[str] = None  # 建议的重试策略: "immediate", "exponential_backoff", "linear_backoff"
    confidence: float = 0.0  # 分析结果的置信度 (0.0-1.0)
    reasoning: str = ""  # LLM 的推理过程说明


@dataclass
class ErrorRecoveryRecord:
    """错误恢复记录
    
    用于记录成功的错误恢复策略到记忆系统，供后续类似错误时参考。
    """

    error_type: str  # 错误类型名称
    error_message: str  # 错误消息
    tool_name: str  # 工具名称
    original_params: Dict[str, Any]  # 原始参数
    fixed_params: Dict[str, Any]  # 修正后的参数
    recovery_successful: bool  # 恢复是否成功
    timestamp: float  # 记录时间戳

    def to_memory_content(self) -> Dict[str, Any]:
        """转换为记忆系统存储格式
        
        Returns:
            Dict[str, Any]: 适合存储到 L2 语义记忆的格式
        """
        return {
            "category": "error_recovery",
            "error_type": self.error_type,
            "error_message": self.error_message,
            "tool_name": self.tool_name,
            "fix_pattern": {
                "original": self.original_params,
                "fixed": self.fixed_params,
            },
            "success": self.recovery_successful,
            "timestamp": self.timestamp,
        }
