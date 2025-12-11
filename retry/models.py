"""
重试配置模型
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional, Type


class RetryStrategy(str, Enum):
    """重试策略"""

    IMMEDIATE = "immediate"  # 立即重试
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 指数退避
    LINEAR_BACKOFF = "linear_backoff"  # 线性退避


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
