"""
验证工具
"""

from typing import Any, Dict


def validate_parameters(parameters: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """
    验证参数是否符合 schema

    Args:
        parameters: 参数字典
        schema: Schema 定义

    Returns:
        是否验证通过
    """
    # 简化实现：检查必需参数
    required = schema.get("required", [])
    for key in required:
        if key not in parameters:
            return False
    return True
