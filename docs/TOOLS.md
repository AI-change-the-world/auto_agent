# Auto-Agent 工具定义完整指南

本文档详细介绍 Auto-Agent 框架中工具的定义方式、错误恢复策略配置和参数验证器使用。

## 目录

- [工具定义方式](#工具定义方式)
- [错误恢复策略配置](#错误恢复策略配置)
- [参数验证器](#参数验证器)
- [替代工具配置](#替代工具配置)
- [完整示例](#完整示例)

---

## 工具定义方式

Auto-Agent 提供三种工具定义方式，从简单到复杂：

### 方式 1: 函数装饰器（最简洁）

```python
from auto_agent import func_tool

@func_tool(name="calculator", description="简单计算器", category="math")
async def calculator(expression: str, precision: int = 2) -> dict:
    """
    计算数学表达式
    
    Args:
        expression: 数学表达式，如 "1 + 2 * 3"
        precision: 小数精度
    """
    result = eval(expression)
    return {"success": True, "result": round(result, precision)}
```

### 方式 2: 类装饰器（带验证/压缩）

```python
from auto_agent import tool, BaseTool

@tool(
    name="es_search",
    description="全文检索",
    category="retrieval",
)
class ESSearchTool(BaseTool):
    async def execute(self, query: str, size: int = 10, **kwargs) -> dict:
        # 检索逻辑...
        return {"success": True, "documents": [...]}
```

### 方式 3: 继承 BaseTool（完全控制）

```python
from auto_agent import BaseTool, ToolDefinition, ToolParameter
from auto_agent.models import ErrorRecoveryStrategy, ParameterValidator

class SearchTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_documents",
            description="搜索文档",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="搜索查询",
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    type="number",
                    description="返回数量限制",
                    required=False,
                    default=10,
                ),
            ],
            # 错误恢复策略
            error_recovery_strategies=[
                ErrorRecoveryStrategy(
                    error_pattern=r".*empty.*query.*",
                    recovery_action="retry_with_fix",
                    fix_suggestion="从 state['inputs']['query'] 获取查询值",
                    max_attempts=3,
                ),
            ],
            # 参数验证器
            parameter_validators=[
                ParameterValidator(
                    parameter_name="query",
                    validation_type="regex",
                    validation_rule=r".+",
                    error_message="查询不能为空",
                ),
            ],
            # 替代工具
            alternative_tools=["fallback_search"],
        )

    async def execute(self, query: str, limit: int = 10, **kwargs) -> dict:
        # 搜索逻辑...
        return {"success": True, "documents": [...]}
```

---

## 错误恢复策略配置

### ErrorRecoveryStrategy 数据类

```python
@dataclass
class ErrorRecoveryStrategy:
    error_pattern: str      # 错误匹配模式（正则表达式）
    recovery_action: str    # 恢复动作
    fix_suggestion: str     # 修正建议（供 LLM 参考）
    max_attempts: int       # 最大尝试次数
```

### 恢复动作类型

| 动作 | 说明 |
|------|------|
| `retry_with_fix` | 修正参数后重试 |
| `use_alternative` | 使用替代工具 |
| `skip` | 跳过当前步骤 |
| `abort` | 中止执行 |

### 配置示例

```python
from auto_agent.models import ErrorRecoveryStrategy

# 参数错误恢复策略
param_error_strategy = ErrorRecoveryStrategy(
    error_pattern=r".*参数.*不能为空.*",
    recovery_action="retry_with_fix",
    fix_suggestion="从执行状态中查找对应的参数值",
    max_attempts=3,
)

# 网络错误恢复策略
network_error_strategy = ErrorRecoveryStrategy(
    error_pattern=r".*(timeout|connection|network).*",
    recovery_action="retry_with_fix",
    fix_suggestion="使用指数退避重试",
    max_attempts=5,
)

# 权限错误策略
permission_error_strategy = ErrorRecoveryStrategy(
    error_pattern=r".*(permission|unauthorized|forbidden).*",
    recovery_action="abort",
    fix_suggestion="检查 API 密钥或权限配置",
    max_attempts=1,
)

# 资源不可用策略
resource_error_strategy = ErrorRecoveryStrategy(
    error_pattern=r".*(rate limit|quota|resource).*",
    recovery_action="use_alternative",
    fix_suggestion="切换到备用服务或等待配额恢复",
    max_attempts=2,
)
```

### 在工具定义中使用

```python
tool_definition = ToolDefinition(
    name="api_call",
    description="调用外部 API",
    parameters=[...],
    error_recovery_strategies=[
        param_error_strategy,
        network_error_strategy,
        permission_error_strategy,
    ],
)
```

---

## 参数验证器

### ParameterValidator 数据类

```python
@dataclass
class ParameterValidator:
    parameter_name: str     # 要验证的参数名称
    validation_type: str    # 验证类型
    validation_rule: str    # 验证规则
    error_message: str      # 验证失败时的错误消息
```

### 验证类型

| 类型 | 说明 | 规则格式 |
|------|------|----------|
| `regex` | 正则表达式匹配 | 正则表达式字符串 |
| `range` | 数值范围检查 | `"min,max"` 格式 |
| `enum` | 枚举值检查 | 逗号分隔的有效值列表 |
| `custom` | 自定义验证 | 自定义验证函数名 |

### 配置示例

```python
from auto_agent.models import ParameterValidator

# 正则表达式验证：非空字符串
query_validator = ParameterValidator(
    parameter_name="query",
    validation_type="regex",
    validation_rule=r".+",
    error_message="查询参数不能为空",
)

# 正则表达式验证：邮箱格式
email_validator = ParameterValidator(
    parameter_name="email",
    validation_type="regex",
    validation_rule=r"^[\w\.-]+@[\w\.-]+\.\w+$",
    error_message="邮箱格式不正确",
)

# 数值范围验证
limit_validator = ParameterValidator(
    parameter_name="limit",
    validation_type="range",
    validation_rule="1,100",
    error_message="limit 必须在 1-100 之间",
)

# 枚举值验证
format_validator = ParameterValidator(
    parameter_name="format",
    validation_type="enum",
    validation_rule="json,xml,csv",
    error_message="format 必须是 json、xml 或 csv",
)

# 自定义验证
custom_validator = ParameterValidator(
    parameter_name="data",
    validation_type="custom",
    validation_rule="validate_data_structure",
    error_message="数据结构不符合要求",
)
```

### 在工具定义中使用

```python
tool_definition = ToolDefinition(
    name="export_data",
    description="导出数据",
    parameters=[
        ToolParameter(name="query", type="string", required=True),
        ToolParameter(name="limit", type="number", default=10),
        ToolParameter(name="format", type="string", default="json"),
    ],
    parameter_validators=[
        query_validator,
        limit_validator,
        format_validator,
    ],
)
```

---

## 替代工具配置

当工具执行失败且重试无效时，可以自动切换到替代工具。

### 配置方式

```python
tool_definition = ToolDefinition(
    name="primary_search",
    description="主搜索引擎",
    parameters=[...],
    # 定义替代工具列表（按优先级排序）
    alternative_tools=["backup_search", "fallback_search"],
)
```

### 替代工具切换流程

```
primary_search 执行失败
        │
        ▼
    重试策略执行
        │
        ▼
    仍然失败？
        │
   ┌────┴────┐
  否        是
   │         │
   ▼         ▼
 返回结果  检查 alternative_tools
              │
              ▼
         有替代工具？
              │
         ┌────┴────┐
        否        是
         │         │
         ▼         ▼
       报错     尝试 backup_search
                   │
                   ▼
              成功？
                   │
              ┌────┴────┐
             是        否
              │         │
              ▼         ▼
           返回结果  尝试 fallback_search
```

---

## 完整示例

### 带完整错误恢复配置的工具

```python
from auto_agent import BaseTool, ToolDefinition, ToolParameter
from auto_agent.models import ErrorRecoveryStrategy, ParameterValidator

class DocumentSearchTool(BaseTool):
    """文档搜索工具，带完整的错误恢复配置"""
    
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="document_search",
            description="搜索文档库中的相关文档",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="搜索查询关键词",
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    type="number",
                    description="返回结果数量限制",
                    required=False,
                    default=10,
                ),
                ToolParameter(
                    name="category",
                    type="string",
                    description="文档分类过滤",
                    required=False,
                    enum=["tech", "business", "general"],
                ),
            ],
            category="retrieval",
            tags=["search", "documents"],
            
            # 参数验证器
            parameter_validators=[
                ParameterValidator(
                    parameter_name="query",
                    validation_type="regex",
                    validation_rule=r"\S+",
                    error_message="搜索查询不能为空或纯空白",
                ),
                ParameterValidator(
                    parameter_name="limit",
                    validation_type="range",
                    validation_rule="1,100",
                    error_message="limit 必须在 1-100 之间",
                ),
            ],
            
            # 错误恢复策略
            error_recovery_strategies=[
                # 空查询错误
                ErrorRecoveryStrategy(
                    error_pattern=r".*query.*empty.*",
                    recovery_action="retry_with_fix",
                    fix_suggestion="从 state['inputs']['query'] 或 state['search_query'] 获取查询值",
                    max_attempts=2,
                ),
                # 连接超时
                ErrorRecoveryStrategy(
                    error_pattern=r".*(timeout|connection).*",
                    recovery_action="retry_with_fix",
                    fix_suggestion="使用指数退避重试，增加超时时间",
                    max_attempts=3,
                ),
                # 服务不可用
                ErrorRecoveryStrategy(
                    error_pattern=r".*(unavailable|503).*",
                    recovery_action="use_alternative",
                    fix_suggestion="切换到备用搜索服务",
                    max_attempts=1,
                ),
            ],
            
            # 替代工具
            alternative_tools=["simple_search", "keyword_match"],
            
            # 参数别名（从状态中自动映射）
            param_aliases={
                "query": "search_query",
            },
            
            # 状态写入映射
            state_mapping={
                "documents": "search_results",
                "total_count": "result_count",
            },
        )

    async def execute(
        self,
        query: str,
        limit: int = 10,
        category: str = None,
        **kwargs,
    ) -> dict:
        """执行文档搜索"""
        # 搜索逻辑实现...
        documents = await self._search(query, limit, category)
        
        return {
            "success": True,
            "documents": documents,
            "total_count": len(documents),
            "query": query,
        }
    
    async def _search(self, query, limit, category):
        # 实际搜索实现
        pass
```

### 工具注册和使用

```python
from auto_agent import ToolRegistry, AutoAgent

# 创建工具注册表
registry = ToolRegistry()

# 注册工具
registry.register(DocumentSearchTool())

# 创建 Agent
agent = AutoAgent(
    llm_client=llm_client,
    tool_registry=registry,
)

# 执行任务（自动使用错误恢复策略）
response = await agent.run("搜索关于 Python 的技术文档")
```

---

## 最佳实践

### 1. 错误恢复策略设计

- 为常见错误类型配置专门的恢复策略
- 参数错误优先使用 `retry_with_fix`
- 网络错误使用指数退避重试
- 权限错误通常应该 `abort`

### 2. 参数验证器使用

- 对必需参数添加非空验证
- 对数值参数添加范围验证
- 对枚举参数使用 `enum` 验证
- 验证失败消息要清晰明确

### 3. 替代工具配置

- 按优先级排序替代工具
- 替代工具应该有相似的功能
- 替代工具的参数应该兼容

### 4. 与记忆系统集成

- 成功的错误恢复会自动记录到 L2 记忆
- 下次遇到类似错误时会优先使用历史策略
- 定期清理低效的恢复策略记忆
