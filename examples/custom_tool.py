"""
自定义工具示例

展示：
1. 使用 @tool 装饰器注册工具
2. 自定义验证函数 (validate_function)
3. 自定义压缩函数 (compress_function)
"""

from auto_agent.models import ValidationMode
from auto_agent.tools import BaseTool, tool

# ==================== 示例1: 基础工具（无验证） ====================


@tool(
    name="calculator",
    description="简单计算器",
    category="math",
    parameters=[
        {
            "name": "expression",
            "type": "string",
            "description": "数学表达式",
            "required": True,
        }
    ],
)
class CalculatorTool(BaseTool):
    """计算器工具"""

    async def execute(self, expression: str) -> dict:
        try:
            result = eval(expression)  # noqa: S307
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ==================== 示例2: 带验证函数的工具 ====================


def validate_search(result, expectations, state, mode: ValidationMode, llm_client, db):
    """
    自定义验证函数

    Args:
        result: 工具执行结果
        expectations: 自然语言期望描述（如 "检索到至少5个文档"）
        state: 当前执行状态
        mode: 验证模式 (NONE/LOOSE/STRICT)
        llm_client: LLM 客户端
        db: 数据库会话

    Returns:
        (passed: bool, reason: str)
    """
    if mode == ValidationMode.NONE:
        return result.get("success", False), "无需校验"

    doc_count = len(result.get("document_ids", []))

    if mode == ValidationMode.STRICT:
        # 严格模式：必须检索到至少5个文档
        if doc_count >= 5:
            return True, f"结果数量达标: {doc_count} 个文档"
        return False, f"结果数量不足: 只有 {doc_count} 个文档，期望至少 5 个"

    else:  # LOOSE
        # 宽松模式：只要执行成功即可
        if result.get("success", False) and doc_count > 0:
            return True, f"执行成功，检索到 {doc_count} 个文档"
        return False, "执行失败或无结果"


def compress_search(result, state):
    """
    自定义压缩函数

    用于在短期记忆中压缩工具执行结果，避免传递大量文本给 LLM

    Args:
        result: 工具执行结果
        state: 当前执行状态

    Returns:
        压缩后的结果，返回 None 表示不压缩（保留完整结果）
    """
    # 只保留文档ID，不保留完整内容
    return {
        "success": result.get("success"),
        "document_ids": result.get("document_ids", [])[:20],  # 最多保留20个ID
        "count": len(result.get("document_ids", [])),
        # 不保留 documents 的完整内容
    }


@tool(
    name="es_fulltext_search",
    description="全文检索工具",
    category="retrieval",
    parameters=[
        {
            "name": "query",
            "type": "string",
            "description": "搜索查询",
            "required": True,
        },
        {"name": "template_id", "type": "integer", "description": "模板ID"},
        {
            "name": "max_results",
            "type": "integer",
            "description": "最大结果数",
            "default": 10,
        },
    ],
    output_schema={
        "document_ids": {"type": "array", "description": "文档ID列表"},
        "documents": {"type": "array", "description": "文档列表"},
        "count": {"type": "integer", "description": "结果数量"},
    },
    validate_function=validate_search,
    compress_function=compress_search,
)
class ESFulltextSearchTool(BaseTool):
    """全文检索工具（示例）"""

    async def execute(
        self, query: str, template_id: int = None, max_results: int = 10
    ) -> dict:
        # 模拟检索结果
        mock_ids = [f"doc_{i}" for i in range(max_results)]
        mock_docs = [
            {
                "id": f"doc_{i}",
                "title": f"文档 {i}",
                "content": f"这是文档 {i} 的内容...",
            }
            for i in range(max_results)
        ]
        return {
            "success": True,
            "document_ids": mock_ids,
            "documents": mock_docs,
            "count": len(mock_ids),
        }


# ==================== 示例3: 生成类工具（不压缩） ====================


def compress_outline(result, state):
    """
    生成类工具的压缩函数

    返回 None 表示不压缩，保留完整结果
    """
    return None  # 大纲内容重要，不压缩


@tool(
    name="generate_outline",
    description="生成文档大纲",
    category="document",
    compress_function=compress_outline,
)
class GenerateOutlineTool(BaseTool):
    """大纲生成工具（示例）"""

    async def execute(self, query: str, template_id: int = None) -> dict:
        return {
            "success": True,
            "outline": {
                "title": "示例大纲",
                "sections": [
                    {"title": "第一章", "subsections": []},
                    {"title": "第二章", "subsections": []},
                ],
            },
        }


# ==================== 使用示例 ====================

if __name__ == "__main__":
    import asyncio

    async def demo():
        # 使用全局注册表
        from auto_agent.tools.registry import get_global_registry

        registry = get_global_registry()

        print("=" * 50)
        print("已注册的工具:")
        print("=" * 50)
        for tool in registry.get_all_tools():
            defn = tool.definition
            has_validate = "✅" if defn.validate_function else "❌"
            has_compress = "✅" if defn.compress_function else "❌"
            print(f"- {defn.name} [{defn.category}]")
            print(f"  验证函数: {has_validate}  压缩函数: {has_compress}")

        print("\n" + "=" * 50)
        print("工具目录（供 LLM 规划使用）:")
        print("=" * 50)
        print(registry.get_tools_catalog())

        print("\n" + "=" * 50)
        print("执行搜索工具:")
        print("=" * 50)
        search_tool = registry.get_tool("es_fulltext_search")
        if search_tool:
            result = await search_tool.execute(query="测试查询", max_results=8)
            print(f"执行结果: {result['success']}, 检索到 {result['count']} 个文档")

            # 测试验证
            from auto_agent.models import ValidationMode

            passed, reason = await search_tool.validate(
                result=result,
                expectations="检索到至少5个文档",
                state={},
                mode=ValidationMode.STRICT,
            )
            print(f"验证结果: {passed}, 原因: {reason}")

            # 测试压缩
            compressed = search_tool.compress_result(result, {})
            print(f"压缩后: {compressed}")

    asyncio.run(demo())
