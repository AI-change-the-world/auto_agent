"""
工具注册表 + 装饰器注册

支持：
- @tool 装饰器自动注册
- validate_function 和 compress_function
- 工具目录生成（供 LLM 规划使用）
"""

import inspect
from typing import Any, Callable, Dict, List, Optional, Type

from auto_agent.models import ToolDefinition, ToolParameter
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
                f"{i + 1}. **{defn.name}** {capabilities}\n"
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
                f"{i + 1}. **{key}** ({ktype})\n"
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


def func_tool(
    name: str,
    description: str,
    category: str = "general",
    tags: Optional[List[str]] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    compress_function: Optional[Callable] = None,
    validate_function: Optional[Callable] = None,
    context_param: Optional[str] = None,
    param_aliases: Optional[Dict[str, str]] = None,
    state_mapping: Optional[Dict[str, str]] = None,
    auto_register: bool = True,
):
    """
    函数工具装饰器 - 最简洁的工具定义方式

    直接装饰一个 async 函数，自动从函数签名推断参数。
    也可以手动指定 parameters 覆盖自动推断。

    使用示例：
    ```python
    # 方式1: 自动推断参数（从函数签名 + docstring）
    @func_tool(name="calculator", description="简单计算器", category="math")
    async def calculator(expression: str, precision: int = 2) -> dict:
        '''
        计算数学表达式

        Args:
            expression: 数学表达式，如 "1 + 2 * 3"
            precision: 小数精度
        '''
        result = eval(expression)
        return {"success": True, "result": round(result, precision)}

    # 方式2: 手动指定参数（更精确的描述）
    @func_tool(
        name="search",
        description="搜索文档",
        parameters=[
            {"name": "query", "type": "string", "description": "搜索关键词", "required": True},
            {"name": "limit", "type": "integer", "description": "返回数量", "required": False, "default": 10},
        ],
    )
    async def search_docs(query: str, limit: int = 10) -> dict:
        return {"success": True, "documents": [...]}

    # 方式3: 带上下文参数（如数据库连接）
    @func_tool(
        name="db_query",
        description="数据库查询",
        context_param="ctx",  # 指定上下文参数名
    )
    async def db_query(ctx, query: str) -> dict:
        # ctx 会在 execute 时通过 kwargs 传入
        return {"success": True}

    # 方式4: 参数别名和状态映射
    @func_tool(
        name="analyze_input",
        description="分析输入",
        param_aliases={"input_text": "query"},  # 从 state["query"] 读取值赋给 input_text
        state_mapping={"search_query": "search_queries"},  # 将 result["search_query"] 写入 state["search_queries"]
    )
    async def analyze_input(ctx, input_text: str) -> dict:
        return {"success": True}
    ```

    Args:
        name: 工具名称
        description: 工具描述
        category: 工具类别
        tags: 标签列表
        parameters: 参数定义列表（可选，不提供则自动推断）
        output_schema: 输出结构定义
        compress_function: 自定义结果压缩函数
        validate_function: 自定义验证函数
        context_param: 上下文参数名（如 "ctx"），该参数不会被推断为工具参数
        param_aliases: 参数别名映射 {param_name: state_field_name}
        state_mapping: 状态写入映射 {result_field: state_field}
        auto_register: 是否自动注册到全局注册表
    """

    def decorator(func: Callable):
        param_list = []

        # 需要跳过的参数名
        skip_params = {"self", "cls", "kwargs"}
        if context_param:
            skip_params.add(context_param)

        # 如果手动指定了 parameters，使用手动指定的
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
        else:
            # 从函数签名推断参数
            sig = inspect.signature(func)

            # 类型映射
            type_map = {
                str: "string",
                int: "integer",
                float: "number",
                bool: "boolean",
                list: "array",
                dict: "object",
            }

            for param_name, param in sig.parameters.items():
                if param_name in skip_params:
                    continue

                # 推断类型
                param_type = "string"
                if param.annotation != inspect.Parameter.empty:
                    param_type = type_map.get(param.annotation, "string")

                # 判断是否必需
                required = param.default == inspect.Parameter.empty

                # 获取默认值
                default = None if required else param.default

                param_list.append(
                    ToolParameter(
                        name=param_name,
                        type=param_type,
                        description="",  # 可以从 docstring 解析
                        required=required,
                        default=default,
                    )
                )

            # 尝试从 docstring 解析参数描述
            if func.__doc__:
                import re

                doc = func.__doc__
                for p in param_list:
                    # 匹配 "param_name: description"
                    pattern = rf"{p.name}[^:]*:\s*(.+?)(?:\n|$)"
                    match = re.search(pattern, doc)
                    if match:
                        p.description = match.group(1).strip()

        # 保存函数引用（避免闭包问题）
        _captured_func = func
        _captured_params = param_list
        _context_param = context_param

        # 保存别名和映射
        _param_aliases = param_aliases or {}
        _state_mapping = state_mapping or {}

        # 创建动态工具类
        class FuncTool(BaseTool):
            @property
            def definition(self) -> ToolDefinition:
                return ToolDefinition(
                    name=name,
                    description=description,
                    parameters=_captured_params,
                    category=category,
                    tags=tags or [],
                    output_schema=output_schema,
                    compress_function=compress_function,
                    validate_function=validate_function,
                    param_aliases=_param_aliases,
                    state_mapping=_state_mapping,
                )

            async def execute(self, **kwargs) -> Any:
                import asyncio

                if asyncio.iscoroutinefunction(_captured_func):
                    return await _captured_func(**kwargs)
                else:
                    return _captured_func(**kwargs)

        # 设置类名
        FuncTool.__name__ = f"{name.title().replace('_', '')}Tool"
        FuncTool.__qualname__ = FuncTool.__name__

        # 自动注册
        if auto_register:
            instance = FuncTool()
            registry = get_global_registry()
            registry.register(instance)

        # 保存工具实例到函数属性，方便访问
        func._tool_instance = (
            FuncTool() if not auto_register else registry.get_tool(name)
        )
        func._tool_class = FuncTool

        return func

    return decorator
