"""
序列化工具
"""

import json
from typing import Any


def to_json(obj: Any) -> str:
    """对象转 JSON 字符串"""
    return json.dumps(obj, ensure_ascii=False, indent=2)


def from_json(json_str: str) -> Any:
    """JSON 字符串转对象"""
    return json.loads(json_str)
