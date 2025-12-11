"""
计算器工具（示例）
"""

from auto_agent.tools.base import BaseTool
from auto_agent.tools.models import ToolDefinition, ToolParameter
from auto_agent.tools.registry import tool


@tool(name="calculator", description="简单计算器", category="math")
class CalculatorTool(BaseTool):
    """计算器工具"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calculator",
            description="执行简单的数学表达式计算",
            parameters=[
                ToolParameter(
                    name="expression",
                    type="string",
                    description="数学表达式，如 '2 + 3 * 4'",
                    required=True,
                )
            ],
            returns={"type": "number", "description": "计算结果"},
            category="math",
            examples=[
                {"input": {"expression": "2 + 2"}, "output": {"result": 4}},
                {"input": {"expression": "10 * 5"}, "output": {"result": 50}},
            ],
        )

    async def execute(self, expression: str) -> dict:
        """执行计算"""
        try:
            result = eval(expression)  # noqa: S307 - 示例代码
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
