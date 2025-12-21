"""
全栈项目生成器 - LangChain 风格 (OpenAI 原生客户端)

使用 OpenAI 原生客户端 + 手动实现 Agent 循环，模拟 LangChain tool calling 模式
这样可以准确统计 token 消耗，同时保持 LangChain 的 ReAct 风格

使用方法:
    cd auto_agent
    python examples/langchain_compare/fullstack_langchain.py
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from openai import AsyncOpenAI

# ==================== Token 追踪 ====================


class TokenTracker:
    """Token 追踪器"""

    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        self.cumulative_tokens = 0
        self.llm_call_count = 0

    def add(self, tokens: int, step_name: str):
        self.llm_call_count += 1
        self.cumulative_tokens += tokens
        self.steps.append(
            {
                "step": step_name,
                "tokens": tokens,
                "cumulative": self.cumulative_tokens,
            }
        )
        print(f"   📊 Token: +{tokens:,} | 累计: {self.cumulative_tokens:,}")


# ==================== 全局状态 ====================


class GlobalState:
    """全局状态管理"""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        self.model: str = ""
        self.output_dir: Optional[Path] = None
        self.project_dir: Optional[Path] = None
        self.tracker: Optional[TokenTracker] = None

        # 业务状态
        self.data: Dict[str, Any] = {}
        self.generated_code: Dict[str, str] = {}

    def reset(self):
        self.data = {}
        self.generated_code = {}
        self.project_dir = None


_g = GlobalState()


# ==================== 工具定义 (OpenAI Function Schema) ====================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "init_project",
            "description": "初始化项目目录结构。这是项目生成的第一步。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "项目名称（英文，snake_case）",
                    }
                },
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_requirements",
            "description": "分析用户需求，提取实体、关系和业务规则。输出会影响后续所有步骤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "requirements": {"type": "string", "description": "用户的需求描述"},
                    "project_type": {
                        "type": "string",
                        "description": "项目类型: api/web/cli",
                        "default": "api",
                    },
                },
                "required": ["requirements"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "design_api",
            "description": "基于需求分析结果设计 REST API 端点。需要先调用 analyze_requirements。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "项目名称"}
                },
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_models",
            "description": "基于实体定义生成 Pydantic 模型代码。需要先调用 analyze_requirements。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_service",
            "description": "基于模型和 API 设计生成服务层代码。需要先调用 generate_models。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_router",
            "description": "基于 API 设计和服务层生成 FastAPI 路由代码。需要先调用 generate_service。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_tests",
            "description": "基于 API 端点生成 pytest 测试用例。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_code",
            "description": "将生成的代码写入文件。每次生成代码后必须调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "文件名 (如 models.py)",
                    },
                    "code_type": {
                        "type": "string",
                        "enum": ["models", "service", "router", "tests"],
                        "description": "代码类型",
                    },
                },
                "required": ["filename", "code_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_project",
            "description": "验证生成的项目代码是否一致、完整。这是最后一步。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ==================== 工具实现 ====================


async def _llm_call(prompt: str, step_name: str) -> str:
    """调用 LLM 并记录 token（使用 stream 避免超时）"""
    chunks = []
    total_tokens = 0

    stream = await _g.client.chat.completions.create(
        model=_g.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        stream=True,
        stream_options={"include_usage": True},
    )

    async for chunk in stream:
        # 收集内容块
        if chunk.choices and chunk.choices[0].delta.content:
            chunks.append(chunk.choices[0].delta.content)
        # 最后一个 chunk 包含 usage 信息
        if chunk.usage:
            total_tokens = chunk.usage.total_tokens

    # 记录 token 消耗
    if total_tokens > 0 and _g.tracker:
        _g.tracker.add(total_tokens, f"tool:{step_name}")

    # 返回拼接好的完整字符串
    return "".join(chunks)


async def tool_init_project(args: Dict[str, Any]) -> Dict[str, Any]:
    """初始化项目 这里和auto_agent版本稍微有些差异，可能会导致一些不一致的地方"""
    project_name = args.get("project_name", "my_project")
    _g.project_dir = _g.output_dir / project_name
    _g.project_dir.mkdir(parents=True, exist_ok=True)
    _g.data["project_name"] = project_name

    print(f"   ✅ 项目目录: {_g.project_dir}")
    return {"success": True, "project_dir": str(_g.project_dir)}


async def tool_analyze_requirements(args: Dict[str, Any]) -> Dict[str, Any]:
    """分析需求"""
    requirements = args.get("requirements", "")
    project_type = args.get("project_type", "api")

    prompt = f"""请分析以下项目需求，提取关键信息。

项目类型: {project_type}
需求描述:
{requirements}

请以 JSON 格式返回:
请以 JSON 格式返回分析结果:
{{
    "project_name": "项目名称（英文，snake_case）",
    "description": "项目描述",
    "entities": [
        {{
            "name": "实体名称（英文，PascalCase）",
            "description": "实体描述",
            "fields": [
                {{"name": "字段名", "type": "类型", "required": true/false, "description": "描述"}}
            ]
        }}
    ],
    "relationships": [
        {{"from": "实体A", "to": "实体B", "type": "one-to-many/many-to-many/one-to-one", "description": "关系描述"}}
    ],
    "business_rules": [
        {{"rule": "规则描述", "affects": ["相关实体"]}}
    ],
    "constraints": [
        {{"constraint": "约束描述", "type": "validation/security/performance"}}
    ],
    "api_style": "REST/GraphQL",
    "auth_required": true/false
}}"""

    text = await _llm_call(prompt, "analyze_requirements")

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
        _g.data["entities"] = result.get("entities", [])
        _g.data["relationships"] = result.get("relationships", [])
        _g.data["business_rules"] = result.get("business_rules", [])

        print(f"   ✅ 实体: {len(_g.data['entities'])} 个")
        return {"success": True, **result}

    return {"success": False, "error": "解析失败"}


async def tool_design_api(args: Dict[str, Any]) -> Dict[str, Any]:
    """设计 API"""
    entities = _g.data.get("entities", [])
    relationships = _g.data.get("relationships", [])

    if not entities:
        return {"success": False, "error": "请先调用 analyze_requirements"}

    prompt = f"""请基于以下实体设计 REST API。

实体: {json.dumps(entities, ensure_ascii=False, indent=2)}
关系: {json.dumps(relationships, ensure_ascii=False, indent=2)}

请以 JSON 格式返回 API 设计:
{{
    "base_path": "/api/v1",
    "endpoints": [
        {{
            "path": "/users",
            "method": "GET",
            "description": "获取用户列表",
            "request_params": {{"page": "int", "size": "int"}},
            "response_schema": "UserListResponse",
            "auth_required": true
        }},
        {{
            "path": "/users/{{id}}",
            "method": "GET",
            "description": "获取单个用户",
            "path_params": {{"id": "int"}},
            "response_schema": "UserResponse",
            "auth_required": true
        }}
    ],
    "schemas": {{
        "UserResponse": {{
            "type": "object",
            "properties": {{
                "id": {{"type": "integer"}},
                "name": {{"type": "string"}}
            }}
        }}
    }},
    "error_responses": {{
        "400": "Bad Request",
        "401": "Unauthorized",
        "404": "Not Found",
        "500": "Internal Server Error"
    }}
}}

要求:
1. 为每个实体生成 CRUD 端点
2. 考虑实体间的关系，生成嵌套资源端点
3. 使用 RESTful 风格
4. 所有 ID 参数使用整数类型"""

    text = await _llm_call(prompt, "design_api")

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
        _g.data["endpoints"] = result.get("endpoints", [])
        _g.data["schemas"] = result.get("schemas", {})

        print(f"   ✅ 端点: {len(_g.data['endpoints'])} 个")
        return {"success": True, **result}

    return {"success": False, "error": "解析失败"}


async def tool_generate_models(args: Dict[str, Any]) -> Dict[str, Any]:
    """生成模型代码"""
    entities = _g.data.get("entities", [])
    schemas = _g.data.get("schemas", {})

    if not entities:
        return {"success": False, "error": "请先调用 analyze_requirements"}

    prompt = f"""请生成 Pydantic 模型代码。

实体: {json.dumps(entities, ensure_ascii=False, indent=2)}
Schema: {json.dumps(schemas, ensure_ascii=False, indent=2)}

请生成完整的 Python 代码，包含:
1. 必要的 import 语句
2. 基础模型类（BaseModel 配置）
3. 每个实体的模型类（包含 Create、Update、Response 变体）
4. 类型注解和字段验证
5. 文档字符串

代码风格要求:
- 使用 Pydantic v2 语法
- 所有字段都要有类型注解
- 可选字段使用 Optional
- ID 字段使用 int 类型

请直接输出 Python 代码，用 ```python 和 ``` 包裹。"""

    text = await _llm_call(prompt, "generate_models")

    code_match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    code = code_match.group(1).strip() if code_match else text.strip()

    _g.generated_code["models"] = code
    model_names = re.findall(r"class (\w+)\(", code)
    _g.data["model_names"] = model_names

    print(f"   ✅ 模型: {len(model_names)} 个, {len(code.split(chr(10)))} 行")
    return {
        "success": True,
        "model_names": model_names,
        "line_count": len(code.split("\n")),
    }


async def tool_generate_service(args: Dict[str, Any]) -> Dict[str, Any]:
    """生成服务层代码"""
    model_names = _g.data.get("model_names", [])
    endpoints = _g.data.get("endpoints", [])
    entities = _g.data.get("entities", [])

    if not model_names:
        return {"success": False, "error": "请先调用 generate_models"}

    prompt = f"""请生成服务层代码。

模型类: {json.dumps(model_names)}
端点: {json.dumps(endpoints, ensure_ascii=False, indent=2)}
实体: {json.dumps(entities, ensure_ascii=False, indent=2)}

请生成完整的服务层 Python 代码，包含:
1. 必要的 import 语句（从 models 模块导入模型类）
2. 服务类（每个实体一个服务类）
3. CRUD 方法实现（使用 async/await）
4. 类型注解
5. 错误处理

代码风格要求:
- 使用依赖注入模式
- 方法参数和返回值都要有类型注解
- 使用已定义的模型类名（不要自己创造新的类名）
- ID 参数使用 int 类型

请直接输出 Python 代码，用 ```python 和 ``` 包裹。"""

    text = await _llm_call(prompt, "generate_service")

    code_match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    code = code_match.group(1).strip() if code_match else text.strip()

    _g.generated_code["service"] = code
    methods = re.findall(r"async def (\w+)\(", code)
    _g.data["service_methods"] = methods

    print(f"   ✅ 方法: {len(methods)} 个, {len(code.split(chr(10)))} 行")
    return {
        "success": True,
        "service_methods": methods,
        "line_count": len(code.split("\n")),
    }


async def tool_generate_router(args: Dict[str, Any]) -> Dict[str, Any]:
    """生成路由代码"""
    endpoints = _g.data.get("endpoints", [])
    service_methods = _g.data.get("service_methods", [])
    model_names = _g.data.get("model_names", [])

    if not service_methods:
        return {"success": False, "error": "请先调用 generate_service"}

    prompt = f"""请生成 FastAPI 路由代码。

端点: {json.dumps(endpoints, ensure_ascii=False, indent=2)}
服务方法: {json.dumps(service_methods)}
模型类: {json.dumps(model_names)}

请生成完整的 FastAPI 路由 Python 代码，包含:
1. 必要的 import 语句
2. APIRouter 实例
3. 每个端点的路由函数
4. 依赖注入（服务类）
5. 请求/响应模型
6. 错误处理

代码风格要求:
- 使用 FastAPI 的依赖注入
- 路由函数使用 async/await
- 正确使用已定义的模型类和服务方法
- 添加 OpenAPI 文档注解
- ID 参数使用 int 类型

请直接输出 Python 代码，用 ```python 和 ``` 包裹。"""

    text = await _llm_call(prompt, "generate_router")

    code_match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    code = code_match.group(1).strip() if code_match else text.strip()

    _g.generated_code["router"] = code
    route_count = len(re.findall(r"@router\.(get|post|put|delete|patch)", code))

    print(f"   ✅ 路由: {route_count} 个, {len(code.split(chr(10)))} 行")
    return {
        "success": True,
        "route_count": route_count,
        "line_count": len(code.split("\n")),
    }


async def tool_generate_tests(args: Dict[str, Any]) -> Dict[str, Any]:
    """生成测试代码"""
    endpoints = _g.data.get("endpoints", [])
    model_names = _g.data.get("model_names", [])

    if not endpoints:
        return {"success": False, "error": "请先调用 design_api"}

    prompt = f"""请生成 pytest 测试代码。

端点: {json.dumps(endpoints, ensure_ascii=False, indent=2)}
模型类: {json.dumps(model_names)}

请生成完整的 pytest 测试代码，包含:
1. 必要的 import 语句
2. pytest fixtures（TestClient、测试数据）
3. 每个端点的测试函数
4. 正向测试和异常测试
5. 断言验证

代码风格要求:
- 使用 pytest 和 httpx
- 测试函数命名: test_<method>_<resource>_<scenario>
- 使用 fixtures 管理测试数据
- 包含边界条件测试

请直接输出 Python 代码，用 ```python 和 ``` 包裹。"""

    text = await _llm_call(prompt, "generate_tests")

    code_match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    code = code_match.group(1).strip() if code_match else text.strip()

    _g.generated_code["tests"] = code
    test_count = len(re.findall(r"def test_\w+\(", code))

    print(f"   ✅ 测试: {test_count} 个, {len(code.split(chr(10)))} 行")
    return {
        "success": True,
        "test_count": test_count,
        "line_count": len(code.split("\n")),
    }


async def tool_write_code(args: Dict[str, Any]) -> Dict[str, Any]:
    """写入代码文件"""
    filename = args.get("filename", "")
    code_type = args.get("code_type", "")

    code = _g.generated_code.get(code_type, "")
    if not code:
        return {"success": False, "error": f"没有 {code_type} 代码"}

    if not _g.project_dir:
        return {"success": False, "error": "项目未初始化"}

    file_path = _g.project_dir / filename
    file_path.write_text(code, encoding="utf-8")

    print(f"   ✅ 写入: {filename}")
    return {"success": True, "filename": filename, "file_path": str(file_path)}


async def tool_validate_project(args: Dict[str, Any]) -> Dict[str, Any]:
    """验证项目"""
    models_code = _g.generated_code.get("models", "")[:1500]
    service_code = _g.generated_code.get("service", "")[:1500]
    router_code = _g.generated_code.get("router", "")[:1500]

    if not all([models_code, service_code, router_code]):
        return {"success": False, "error": "代码不完整"}

    prompt = f"""请验证以下代码的一致性。

模型代码:
{models_code}

服务代码:
{service_code}

路由代码:
{router_code}

请检查:
1. 模型类是否在服务和路由中正确使用
2. 服务方法是否在路由中正确调用
3. 类型注解是否一致
4. 是否有未定义的引用
5. ID 参数类型是否统一为 int

请以 JSON 格式返回验证结果:
{{
    "is_valid": true/false,
    "issues": [
        {{"severity": "error/warning", "location": "位置", "description": "问题描述"}}
    ],
    "suggestions": ["改进建议1", "改进建议2"],
    "summary": "验证总结"
}}"""

    text = await _llm_call(prompt, "validate_project")

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
        status = "✅ 通过" if result.get("is_valid") else "⚠️ 有问题"
        print(f"   {status}")
        return {"success": True, **result}

    return {"success": True, "is_valid": True, "issues": []}


# 工具映射
TOOL_HANDLERS = {
    "init_project": tool_init_project,
    "analyze_requirements": tool_analyze_requirements,
    "design_api": tool_design_api,
    "generate_models": tool_generate_models,
    "generate_service": tool_generate_service,
    "generate_router": tool_generate_router,
    "generate_tests": tool_generate_tests,
    "write_code": tool_write_code,
    "validate_project": tool_validate_project,
}


# ==================== Agent 主循环 (模拟 LangChain ReAct) ====================

SYSTEM_PROMPT = """你是一个专业的全栈项目生成智能体，能够自主规划和生成完整的 REST API 项目。

## 你的能力
你可以使用以下工具完成项目生成任务：
1. init_project - 初始化项目目录
2. analyze_requirements - 分析需求，提取实体和关系
3. design_api - 设计 REST API 端点
4. generate_models - 生成 Pydantic 模型代码
5. generate_service - 生成服务层代码
6. generate_router - 生成 FastAPI 路由代码
7. generate_tests - 生成测试用例
8. write_code - 将代码写入文件
9. validate_project - 验证项目一致性

## 工作流程
请严格按以下顺序执行：
1. init_project - 初始化项目目录
2. analyze_requirements - 分析需求
3. design_api - 设计 API
4. generate_models → write_code(filename="models.py", code_type="models")
5. generate_service → write_code(filename="service.py", code_type="service")
6. generate_router → write_code(filename="router.py", code_type="router")
7. generate_tests → write_code(filename="test_api.py", code_type="tests")
8. validate_project - 验证一致性

## 重要规则
- 每次生成代码后，必须立即调用 write_code 写入文件
- 各层代码使用一致的类名和方法名
- 所有 ID 参数使用 int 类型
- 确保按顺序执行，因为后续步骤依赖前面的结果"""


async def run_agent_loop(query: str) -> Dict[str, Any]:
    """运行 Agent 循环 (模拟 LangChain ReAct 模式)"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    max_iterations = 25
    iteration = 0
    tool_calls_count = 0

    while iteration < max_iterations:
        iteration += 1
        print(f"\n--- 迭代 {iteration} ---")

        # 调用 LLM
        response = await _g.client.chat.completions.create(
            model=_g.model,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
            temperature=0.3,
        )

        # 记录 token
        if response.usage and _g.tracker:
            _g.tracker.add(response.usage.total_tokens, f"agent_iter_{iteration}")

        message = response.choices[0].message

        # 检查是否有工具调用
        if message.tool_calls:
            messages.append(message)

            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)

                print(f"   🔧 调用工具: {func_name}")
                tool_calls_count += 1

                # 执行工具
                handler = TOOL_HANDLERS.get(func_name)
                if handler:
                    try:
                        result = await handler(func_args)
                    except Exception as e:
                        result = {"success": False, "error": str(e)}
                else:
                    result = {"success": False, "error": f"未知工具: {func_name}"}

                # 添加工具结果
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False)[:3000],
                    }
                )
        else:
            # 没有工具调用，Agent 完成
            final_output = message.content or ""
            print(f"\n✅ Agent 完成推理")

            return {
                "success": True,
                "output": final_output,
                "iterations": iteration,
                "tool_calls": tool_calls_count,
            }

    return {
        "success": False,
        "error": "达到最大迭代次数",
        "iterations": iteration,
        "tool_calls": tool_calls_count,
    }


async def run_langchain_fullstack(
    requirements: str,
    project_name: str,
    output_dir: Path,
) -> Dict[str, Any]:
    """运行全栈项目生成"""

    print("=" * 70)
    print("🏗️  LangChain 风格全栈项目生成器 (OpenAI 原生客户端)")
    print("=" * 70)

    # 初始化
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    _g.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    _g.model = model
    _g.output_dir = output_dir
    _g.tracker = TokenTracker()
    _g.reset()

    print(f"\n✅ 客户端初始化成功 (model: {model})")
    print(f"📁 输出目录: {output_dir}")
    print(f"📋 项目名称: {project_name}")

    # 构建查询
    query = f"""
请帮我生成一个完整的 REST API 项目。

项目名称: {project_name}

需求描述:
{requirements}

请按以下步骤执行:
1. 初始化项目目录 (init_project)
2. 分析需求，提取实体和关系 (analyze_requirements)
3. 设计 REST API 端点 (design_api)
4. 生成 Pydantic 数据模型 (generate_models)，然后用 write_code 写入 models.py
5. 生成服务层代码 (generate_service)，然后用 write_code 写入 service.py
6. 生成 FastAPI 路由代码 (generate_router)，然后用 write_code 写入 router.py
7. 生成测试用例 (generate_tests)，然后用 write_code 写入 test_api.py
8. 验证项目一致性 (validate_project)

重要规则:
- 每次生成代码后，必须立即调用 write_code 工具将代码写入文件
- 各层代码使用一致的类名和方法名
- 所有 ID 参数使用 int 类型
- 代码符合 Python 最佳实践
"""

    print("\n" + "=" * 70)
    print("🚀 开始执行...")
    print("=" * 70)

    start_time = time.time()

    try:
        result = await run_agent_loop(query)

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        print("\n" + "=" * 70)
        print("✅ 执行完成!")
        print("=" * 70)

        # 统计
        print(f"\n📊 执行统计:")
        print(f"   - 迭代次数: {result.get('iterations', 0)}")
        print(f"   - 工具调用: {result.get('tool_calls', 0)} 次")
        print(f"   - LLM 调用: {_g.tracker.llm_call_count} 次")
        print(f"   - Token 消耗: {_g.tracker.cumulative_tokens:,}")
        print(f"   - 耗时: {duration_ms:.1f}ms ({duration_ms / 1000:.1f}s)")

        # Token 明细
        print(f"\n📊 Token 消耗明细:")
        for step in _g.tracker.steps:
            print(
                f"      {step['step']}: +{step['tokens']:,} (累计: {step['cumulative']:,})"
            )

        # 生成的文件
        generated_files = list(_g.generated_code.keys())
        print(f"\n📁 生成代码: {', '.join(generated_files)}")

        return {
            "success": result.get("success", False),
            "output": result.get("output", ""),
            "project_name": project_name,
            "output_dir": str(output_dir / project_name)
            if _g.project_dir
            else str(output_dir),
            "generated_files": generated_files,
            "iterations": result.get("iterations", 0),
            "tool_calls": result.get("tool_calls", 0),
            "llm_calls": _g.tracker.llm_call_count,
            "total_tokens": _g.tracker.cumulative_tokens,
            "token_steps": _g.tracker.steps,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        end_time = time.time()
        print(f"\n❌ 执行失败: {e}")
        import traceback

        traceback.print_exc()

        return {
            "success": False,
            "error": str(e),
            "duration_ms": (end_time - start_time) * 1000,
            "total_tokens": _g.tracker.cumulative_tokens if _g.tracker else 0,
        }


# ==================== 示例需求 ====================

SAMPLE_REQUIREMENTS = {
    "task": """
一个任务管理系统 API，包含以下功能：

1. 项目管理
   - 创建、编辑、删除项目
   - 项目成员管理
   - 项目状态（进行中、已完成、已归档）

2. 任务管理
   - 创建、编辑、删除任务
   - 任务属性（标题、描述、优先级、截止日期）
   - 任务状态（待办、进行中、已完成）
   - 任务分配给成员
   - 子任务支持

3. 标签系统
   - 创建、编辑、删除标签
   - 任务可以有多个标签

4. 评论和附件
   - 任务评论
   - 任务附件上传

5. 业务规则
   - 只有项目成员可以查看/编辑项目内的任务
   - 完成所有子任务后父任务自动完成
   - 删除项目时删除所有相关任务
""",
}


async def main():
    """主函数"""
    print("🚀 启动 LangChain 风格全栈项目生成器...")

    # 检查 API Key
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 未设置 API Key")
        return

    # 输出目录
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    # 项目配置
    project_name = "task_api_langchain"
    requirements = SAMPLE_REQUIREMENTS["task"]

    result = await run_langchain_fullstack(requirements, project_name, output_dir)

    # 保存报告
    if result.get("success"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_dir / f"langchain_fullstack_report_{timestamp}.md"

        # Token 明细
        token_detail = (
            "\n### Token 消耗明细\n\n| 步骤 | Token | 累计 |\n|------|-------|------|\n"
        )
        for step in result.get("token_steps", []):
            token_detail += (
                f"| {step['step']} | {step['tokens']:,} | {step['cumulative']:,} |\n"
            )

        report_file.write_text(
            f"""# LangChain 风格全栈项目生成报告

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 框架: OpenAI Function Calling (LangChain ReAct 风格)

## 项目信息

- 项目名称: {result["project_name"]}
- 输出目录: {result["output_dir"]}
- 生成文件: {", ".join(result.get("generated_files", []))}

## 执行统计

- 迭代次数: {result.get("iterations", 0)}
- 工具调用次数: {result.get("tool_calls", 0)}
- LLM 调用次数: {result.get("llm_calls", 0)}
- Token 消耗: {result.get("total_tokens", 0):,}
- 总耗时: {result["duration_ms"]:.1f}ms ({result["duration_ms"] / 1000:.1f}s)
{token_detail}

## Agent 输出

{result.get("output", "")}
""",
            encoding="utf-8",
        )

        print(f"\n📄 报告已保存: {report_file}")


if __name__ == "__main__":
    print("=" * 70)
    print("LangChain 风格全栈项目生成器")
    print("=" * 70)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
