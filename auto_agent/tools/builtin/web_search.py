"""
网页搜索工具（示例）
"""

from auto_agent.models import (
    ResultHandlingConfig,
    ToolPostPolicy,
    ValidationConfig,
)
from auto_agent.tools.base import BaseTool
from auto_agent.tools.models import ToolDefinition, ToolParameter
from auto_agent.tools.registry import tool


@tool(
    name="web_search",
    description="网页搜索",
    category="retrieval",
    post_policy=ToolPostPolicy(
        validation=ValidationConfig(
            on_fail="retry",
            max_retries=3,
        ),
        result_handling=ResultHandlingConfig(
            cache_policy="session",
            cache_ttl=1800,  # 30 分钟缓存
        ),
    ),
)
class WebSearchTool(BaseTool):
    """网页搜索工具（占位实现）"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description="搜索网页内容",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="搜索查询",
                    required=True,
                ),
                ToolParameter(
                    name="max_results",
                    type="number",
                    description="最大结果数",
                    required=False,
                    default=5,
                ),
            ],
            returns={"type": "array", "description": "搜索结果列表"},
            category="retrieval",
        )

    async def execute(self, query: str, max_results: int = 5) -> dict:
        """执行搜索（占位）"""
        # TODO: 实际实现搜索
        return {
            "success": True,
            "results": [
                {"title": f"结果 {i}", "url": f"http://example.com/{i}"}
                for i in range(max_results)
            ],
        }
