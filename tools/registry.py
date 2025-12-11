"""
工具注册表 + 装饰器注册

支持：
- @tool 装饰器自动注册
- validate_function 和 compress_function
- 工具目录生成（供 LLM 规划使用）
"""

import inspect
from typing import Any, Callable, Dict, List, Optional, Type

from auto_agent.models import ToolDefinition, ToolParameter, ValidationMode
from auto_agent.tools.base import BaseTool


class ToolRegistry:
    """
    工具注册表

    功能：
    - 注册/注销工具
    - 按类别获取工具
    - 生成工具描述（供 LLM 使用）
    - 生成工具目录和状态键目录
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[str, List[str]] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        name = tool.definition.name
        self._tools[name] = tool

        # 按类别分组
        category = tool.definition.category
        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)

    def unregister(self, tool_name: str) -> None:
        """注销工具"""
        if tool_name in self._tools:
            tool = self._tools.pop(tool_name)
            category = tool.definition.category
            if category in self._categories:
                self._categories[category] = [
                    n for n in self._categories[category] if n != tool_name
                ]

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(tool_name)

    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """按类别获取工具"""
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]

    def get_all_tools(self) -> List[BaseTool]:
        """获取所有工具"""
        return list(self._tools.values())

    def get_tool_descriptions(self) -> str:
        """获取所有工具的描述（用于提示词）"""
        descriptions = []
        for tool in self._tools.values():
            defn = tool.definition
            desc = f"- **{defn.name}** [{defn.category}]: {defn.description}"
            if defn.parameters:
                params = ", ".join(f"{p.name}({p.type})" for p in defn.parameters)
                desc += f"\n  参数: {params}"
            descriptions.append(desc)
        return "\n".join(descriptions)

    def get_tools_schema_list(self) -> List[Dict[str, Any]]:
        """获取所有工具的 Schema 列表（供 LLM 使用）"""
        return [tool.get_openai_schema() for tool in self._tools.values()]

    def get_tools_catalog(self) -> str:
        """
        生成工具能力目录（供 LLM 规划阶段使用）

        包含每个工具的:
        - name / description / capabilities(category+tags)
        - input_schema (参数摘要)
        - output_schema (输出字段)
        """
        catalog_lines = []

        for i, tool in enumerate(self._tools.values()):
            defn = tool.definition
            desc = defn.description.strip()
            category = defn.category
            tags = defn.tags

            # 构建能力描述
            capabilities = f"[{category}]"
            if tags:
                capabilities += f" {', '.join(tags)}"

            # 简化参数列表
            param_list = []
            for p in defn.parameters:
                pdesc = p.description[:50] if p.description else ""
                req_mark = "*" if p.required else ""
                param_list.append(f"{p.name}{req_mark}: {p.type} - {pdesc}")

            params_text = "\n     - ".join(param_list) if param_list else "无参数"

            # 获取输出 schema
            if defn.output_schema:
                output_keys = list(defn.output_schema.keys())
                output_text = ", ".join(output_keys)
            else:
                output_text = "success(boolean), error?(string)"

            catalog_lines.append(
                f"{i+1}. **{defn.name}** {capabilities}\n"
                f"   描述: {desc[:200]}\n"
                f"   输入参数:\n     - {params_text}\n"
                f"   输出字段: {output_text}"
            )

        return "\n\n".join(catalog_lines)

    def get_state_keys_catalog(self) -> str:
        """
        生成状态键目录（汇总所有工具可能写入的状态键）
        """
        state_keys: Dict[str, Dict[str, Any]] = {}

        for tool_name, tool in self._tools.items():
            output_schema = tool.definition.output_schema
            if not output_schema:
                continue

            for key, schema in output_schema.items():
                if key not in state_keys:
                    state_keys[key] = {
                        "type": schema.get("type", "any"),
                        "description": schema.get("description", ""),
                        "sources": [],
                    }
                if tool_name not in state_keys[key]["sources"]:
                    state_keys[key]["sources"].append(tool_name)

        catalog_lines = []
        for i, (key, details) in enumerate(sorted(state_keys.items())):
            ktype = details["type"]
            kdesc = details["description"][:80]
            ksources = ", ".join(details["sources"])

            catalog_lines.append(
                f"{i+1}. **{key}** ({ktype})\n"
                f"   说明: {kdesc}\n"
                f"   来源工具: {ksources}"
            )

        return "\n\n".join(catalog_lines)

    def get_compress_function(self, tool_name: str) -> Optional[Callable]:
        """获取工具的压缩函数"""
        tool = self._tools.get(tool_name)
        if tool:
            return tool.definition.compress_function
        return None

    def get_validate_function(self, tool_name: str) -> Optional[Callable]:
        """获取工具的验证函数"""
        tool = self._tools.get(tool_name)
        if tool:
            return tool.definition.validate_function
        return None


# ==================== 全局注册表 ====================

_GLOBAL_REGISTRY: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    """获取全局注册表"""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = ToolRegistry()
    return _GLOBAL_REGISTRY


# ==================== 装饰器 ====================


def tool(
    name: str,
    description: str,
    category: str = "general",
    tags: Optional[List[str]] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    validate_function: Optional[Callable] = None,
    compress_function: Optional[Callable] = None,
    auto_register: bool = True,
):
    """
    工具装饰器

    使用示例：
    ```python
    # 方式1: 不校验（默认）
    @tool(name="calculator", description="计算器", category="math")
    class CalculatorTool(BaseTool):
        ...

    # 方式2: 使用自定义验证函数
    def validate_search(result, expectations, state, mode: ValidationMode, llm_client, db):
        if mode == ValidationMode.NONE:
            return result.get("success", False), "无需校验"
        if mode == ValidationMode.STRICT:
            if result.get("count", 0) >= 5:
                return True, "结果数量达标"
            return False, "结果数量不足"
        return result.get("success", False), "宽松校验通过"

    # 方式3: 使用自定义压缩函数
    def compress_search(result, state):
        # 只保留文档ID，不保留完整内容
        return {
            "success": result.get("success"),
            "document_ids": result.get("document_ids", [])[:20],
            "count": len(result.get("document_ids", [])),
        }

    @tool(
        name="es_fulltext_search",
        description="全文检索",
        validate_function=validate_search,
        compress_function=compress_search,
    )
    class ESFulltextSearchTool(BaseTool):
        ...
    ```

    Args:
        name: 工具名称
        description: 工具描述
        category: 工具类别
        tags: 标签列表
        parameters: 参数定义列表
        output_schema: 输出结构定义
        validate_function: 自定义验证函数
        compress_function: 自定义结果压缩函数
        auto_register: 是否自动注册到全局注册表
    """

    def decorator(cls: Type[BaseTool]):
        # 解析参数定义
        param_list = []
        if parameters:
            for p in parameters:
                param_list.append(
                    ToolParameter(
                        name=p.get("name", ""),
                        type=p.get("type", "string"),
                        description=p.get("description", ""),
                        required=p.get("required", False),
                        default=p.get("default"),
                        enum=p.get("enum"),
                    )
                )

        # 保存元信息到类
        cls._tool_name = name
        cls._tool_description = description
        cls._tool_category = category
        cls._tool_tags = tags or []
        cls._tool_parameters = param_list
        cls._tool_output_schema = output_schema
        cls._tool_validate_function = validate_function
        cls._tool_compress_function = compress_function

        # 重写 definition 属性
        original_definition = getattr(cls, "definition", None)

        @property
        def enhanced_definition(self) -> ToolDefinition:
            # 如果子类实现了 definition，合并信息
            if original_definition and callable(original_definition.fget):
                base_def = original_definition.fget(self)
                return ToolDefinition(
                    name=name,
                    description=description,
                    parameters=param_list or base_def.parameters,
                    returns=base_def.returns,
                    category=category,
                    tags=tags or base_def.tags,
                    examples=base_def.examples,
                    output_schema=output_schema or base_def.output_schema,
                    validate_function=validate_function,
                    compress_function=compress_function,
                )
            return ToolDefinition(
                name=name,
                description=description,
                parameters=param_list,
                category=category,
                tags=tags or [],
                output_schema=output_schema,
                validate_function=validate_function,
                compress_function=compress_function,
            )

        cls.definition = enhanced_definition

        # 如果开启自动注册，实例化并注册
        if auto_register:
            instance = cls()
            registry = get_global_registry()
            registry.register(instance)

        return cls

    return decorator
