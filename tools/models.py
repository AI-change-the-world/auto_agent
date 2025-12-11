"""
工具数据模型
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
    """工具定义"""

    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    returns: Dict[str, Any] = field(default_factory=dict)
    category: str = "general"
    examples: List[Dict[str, Any]] = field(default_factory=list)

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
            "examples": self.examples,
        }
