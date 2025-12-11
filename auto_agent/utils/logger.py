"""
日志工具
"""

import logging
import sys


def setup_logger(name: str = "auto_agent", level: int = logging.INFO):
    """
    设置日志

    Args:
        name: 日志名称
        level: 日志级别

    Returns:
        Logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 控制台处理器
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # 格式化
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger
