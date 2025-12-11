"""
重试控制器
"""

import asyncio
from typing import Any, Callable, Dict, Optional

from auto_agent.llm.client import LLMClient
from auto_agent.retry.models import RetryConfig, RetryStrategy
from auto_agent.retry.strategies import (
    exponential_backoff_delay,
    immediate_delay,
    linear_backoff_delay,
)


class RetryController:
    """
    重试控制器

    支持多种重试策略和智能错误分析
    """

    def __init__(
        self, config: RetryConfig, llm_client: Optional[LLMClient] = None
    ):
        self.config = config
        self.llm_client = llm_client

    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs,
    ) -> Any:
        """
        带重试的执行

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果

        Raises:
            最后一次失败的异常
        """
        last_exception = None

        for attempt in range(self.config.max_retries + 1):
            try:
                # 执行函数
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return result

            except Exception as e:
                last_exception = e

                # 判断是否应该重试
                if not await self.should_retry(e, attempt, {}):
                    raise

                # 如果是最后一次尝试，直接抛出异常
                if attempt >= self.config.max_retries:
                    raise

                # 计算延迟时间
                delay = self.get_delay(attempt)
                await asyncio.sleep(delay)

        # 理论上不应该到达这里
        if last_exception:
            raise last_exception

    async def should_retry(
        self,
        exception: Exception,
        attempt: int,
        context: Dict[str, Any],
    ) -> bool:
        """
        判断是否应该重试

        Args:
            exception: 异常对象
            attempt: 当前尝试次数
            context: 上下文信息

        Returns:
            是否应该重试
        """
        # 检查是否达到最大重试次数
        if attempt >= self.config.max_retries:
            return False

        # 检查异常类型
        if self.config.retry_on_exceptions:
            if not any(
                isinstance(exception, exc_type)
                for exc_type in self.config.retry_on_exceptions
            ):
                return False

        # 如果有自定义回调，使用回调判断
        if self.config.should_retry_callback:
            return self.config.should_retry_callback(exception, attempt, context)

        # 默认重试
        return True

    async def analyze_error(
        self,
        exception: Exception,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        使用 LLM 分析错误（占位实现）

        Args:
            exception: 异常对象
            context: 上下文信息

        Returns:
            分析结果
        """
        # TODO: 使用 LLM 分析错误
        return {
            "is_recoverable": True,
            "root_cause": str(exception),
            "should_retry": True,
            "suggested_changes": {},
            "reasoning": "默认分析",
        }

    def get_delay(self, attempt: int) -> float:
        """
        计算延迟时间

        Args:
            attempt: 当前尝试次数

        Returns:
            延迟时间（秒）
        """
        if self.config.strategy == RetryStrategy.IMMEDIATE:
            return immediate_delay()
        elif self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            return exponential_backoff_delay(
                attempt,
                self.config.base_delay,
                self.config.backoff_factor,
                self.config.max_delay,
            )
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            return linear_backoff_delay(
                attempt, self.config.base_delay, self.config.max_delay
            )
        else:
            return self.config.base_delay
