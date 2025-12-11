"""
重试策略实现
"""


def immediate_delay() -> float:
    """立即重试（无延迟）"""
    return 0.0


def exponential_backoff_delay(
    attempt: int,
    base_delay: float,
    backoff_factor: float,
    max_delay: float,
) -> float:
    """
    指数退避延迟

    Args:
        attempt: 尝试次数
        base_delay: 基础延迟
        backoff_factor: 退避因子
        max_delay: 最大延迟

    Returns:
        延迟时间（秒）
    """
    delay = base_delay * (backoff_factor**attempt)
    return min(delay, max_delay)


def linear_backoff_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
) -> float:
    """
    线性退避延迟

    Args:
        attempt: 尝试次数
        base_delay: 基础延迟
        max_delay: 最大延迟

    Returns:
        延迟时间（秒）
    """
    delay = base_delay * (attempt + 1)
    return min(delay, max_delay)
