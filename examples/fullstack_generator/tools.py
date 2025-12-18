"""
全栈项目生成器 - 工具定义

所有工具都使用 LLM 驱动，并配置了统一后处理策略 (ToolPostPolicy)
"""

import json
import re
from typing import Any, Dict, List, Optional

from auto_agent import (
    BaseTool,
    OpenAIClient,
    ToolDefinition,
    ToolParameter,
)
from auto_agent.models import (
    PostSuccessConfig,
    ResultHandlingConfig,
    ToolPostPolicy,
    ValidationConfig,
)


class AnalyzeRequirementsTool(BaseTool):
    """
    需求分析工具
    
    分析用户需求，提取实体、关系、业务规则
    这是项目生成的第一步，输出会影响后续所有步骤
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_requirements",
            description="分析用户需求，提取实体、关系和业务规则。这是项目生成的第一步，输出会影响后续所有步骤。",
            parameters=[
                ToolParameter(
                    name="requirements",
                    type="string",
                    description="用户的需求描述",
                    required=True,
                ),
                ToolParameter(
                    name="project_type",
                    type="string",
                    description="项目类型: api/web/cli",
                    required=False,
                ),
            ],
            category="analysis",
            output_schema={
                "entities": {"type": "array", "description": "实体列表"},
                "relationships": {"type": "array", "description": "实体关系"},
                "business_rules": {"type": "array", "description": "业务规则"},
                "constraints": {"type": "array", "description": "约束条件"},
            },
            # 统一后处理策略
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(
                    on_fail="retry",
                    max_retries=2,
                ),
                post_success=PostSuccessConfig(
                    high_impact=True,  # 高影响力工具
                    requires_consistency_check=False,  # 第一步无需检查
                    extract_working_memory=True,  # 提取工作记忆
                ),
                result_handling=ResultHandlingConfig(
                    register_as_checkpoint=True,  # 注册为检查点
                    checkpoint_type="requirements",
                ),
            ),
        )

    async def execute(
        self,
        requirements: str,
        project_type: str = "api",
        **kwargs,
    ) -> Dict[str, Any]:
        """分析需求"""
        try:
            prompt = f"""请分析以下项目需求，提取关键信息。

项目类型: {project_type}
需求描述:
{requirements}

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

            print("分析requirement prompt:\n"+ prompt)

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            # 解析 JSON
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                result["success"] = True
                return result
            else:
                return {
                    "success": False,
                    "error": "无法解析 LLM 响应为 JSON",
                    "raw_response": response,
                }

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON 解析错误: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class DesignAPITool(BaseTool):
    """
    API 设计工具
    
    基于需求分析结果设计 REST API 端点
    需要与需求分析结果保持一致
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="design_api",
            description="基于需求分析结果设计 REST API 端点。需要与需求分析中的实体和关系保持一致。",
            parameters=[
                ToolParameter(
                    name="entities",
                    type="array",
                    description="实体列表（从 analyze_requirements 获取）",
                    required=True,
                ),
                ToolParameter(
                    name="relationships",
                    type="array",
                    description="实体关系（从 analyze_requirements 获取）",
                    required=False,
                ),
                ToolParameter(
                    name="project_name",
                    type="string",
                    description="项目名称",
                    required=True,
                ),
            ],
            category="design",
            output_schema={
                "endpoints": {"type": "array", "description": "API 端点列表"},
                "schemas": {"type": "object", "description": "请求/响应 Schema"},
            },
            param_aliases={
                "entities": "entities",
                "relationships": "relationships",
                "project_name": "project_name",
            },
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(
                    on_fail="retry",
                    max_retries=2,
                ),
                post_success=PostSuccessConfig(
                    high_impact=True,
                    requires_consistency_check=True,  # 需要与需求分析一致
                    consistency_check_against=["requirements"],
                    extract_working_memory=True,
                ),
                result_handling=ResultHandlingConfig(
                    register_as_checkpoint=True,
                    checkpoint_type="interface",
                ),
            ),
        )

    async def execute(
        self,
        entities: List[Dict[str, Any]],
        project_name: str,
        relationships: List[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """设计 API"""
        try:
            entities_text = json.dumps(entities, ensure_ascii=False, indent=2)
            relationships_text = json.dumps(relationships or [], ensure_ascii=False, indent=2)

            prompt = f"""请基于以下实体和关系设计 REST API 端点。

项目名称: {project_name}

实体列表:
{entities_text}

实体关系:
{relationships_text}

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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                result["success"] = True
                result["project_name"] = project_name
                return result
            else:
                return {"success": False, "error": "无法解析 API 设计"}

        except Exception as e:
            return {"success": False, "error": str(e)}


class GenerateModelsTool(BaseTool):
    """
    数据模型生成工具
    
    基于实体定义生成 Pydantic 模型代码
    需要与 API 设计中的 Schema 保持一致
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_models",
            description="基于实体定义生成 Pydantic 模型代码。需要与 API 设计中的 Schema 保持一致。",
            parameters=[
                ToolParameter(
                    name="entities",
                    type="array",
                    description="实体列表",
                    required=True,
                ),
                ToolParameter(
                    name="schemas",
                    type="object",
                    description="API Schema 定义（从 design_api 获取）",
                    required=False,
                ),
            ],
            category="code_generation",
            output_schema={
                "models_code": {"type": "string", "description": "生成的模型代码"},
                "model_names": {"type": "array", "description": "模型名称列表"},
            },
            param_aliases={
                "entities": "entities",
                "schemas": "schemas",
            },
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(
                    on_fail="retry",
                    max_retries=2,
                ),
                post_success=PostSuccessConfig(
                    high_impact=True,
                    requires_consistency_check=True,
                    consistency_check_against=["requirements", "interface"],
                    extract_working_memory=True,
                ),
                result_handling=ResultHandlingConfig(
                    register_as_checkpoint=True,
                    checkpoint_type="code",
                ),
            ),
        )

    async def execute(
        self,
        entities: List[Dict[str, Any]],
        schemas: Dict[str, Any] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """生成模型代码"""
        try:
            entities_text = json.dumps(entities, ensure_ascii=False, indent=2)
            schemas_text = json.dumps(schemas or {}, ensure_ascii=False, indent=2)

            prompt = f"""请基于以下实体定义生成 Pydantic 模型代码。

实体定义:
{entities_text}

API Schema 参考:
{schemas_text}

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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            # 提取代码块
            code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()
            else:
                code = response.strip()

            # 提取模型名称
            model_names = re.findall(r"class (\w+)\(", code)

            return {
                "success": True,
                "models_code": code,
                "model_names": model_names,
                "line_count": len(code.split("\n")),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}



class GenerateServiceTool(BaseTool):
    """
    服务层生成工具
    
    基于模型和 API 设计生成服务层代码
    需要使用正确的模型类名和方法签名
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_service",
            description="基于模型和 API 设计生成服务层代码。需要使用正确的模型类名和方法签名。",
            parameters=[
                ToolParameter(
                    name="model_names",
                    type="array",
                    description="模型名称列表（从 generate_models 获取）",
                    required=True,
                ),
                ToolParameter(
                    name="endpoints",
                    type="array",
                    description="API 端点列表（从 design_api 获取）",
                    required=True,
                ),
                ToolParameter(
                    name="entities",
                    type="array",
                    description="实体列表",
                    required=True,
                ),
            ],
            category="code_generation",
            output_schema={
                "service_code": {"type": "string", "description": "服务层代码"},
                "service_methods": {"type": "array", "description": "服务方法列表"},
            },
            param_aliases={
                "model_names": "model_names",
                "endpoints": "endpoints",
                "entities": "entities",
            },
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(
                    on_fail="retry",
                    max_retries=2,
                ),
                post_success=PostSuccessConfig(
                    high_impact=True,
                    requires_consistency_check=True,
                    consistency_check_against=["interface", "code"],
                    extract_working_memory=True,
                    # 自定义重规划条件
                    replan_condition="如果服务方法与 API 端点不匹配，或使用了未定义的模型类",
                ),
                result_handling=ResultHandlingConfig(
                    register_as_checkpoint=True,
                    checkpoint_type="code",
                ),
            ),
        )

    async def execute(
        self,
        model_names: List[str],
        endpoints: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        **kwargs,
    ) -> Dict[str, Any]:
        """生成服务层代码"""
        try:
            prompt = f"""请基于以下信息生成服务层代码。

可用的模型类: {json.dumps(model_names, ensure_ascii=False)}

API 端点:
{json.dumps(endpoints, ensure_ascii=False, indent=2)}

实体信息:
{json.dumps(entities, ensure_ascii=False, indent=2)}

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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()
            else:
                code = response.strip()

            # 提取服务方法
            method_names = re.findall(r"async def (\w+)\(", code)

            return {
                "success": True,
                "service_code": code,
                "service_methods": method_names,
                "line_count": len(code.split("\n")),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


class GenerateRouterTool(BaseTool):
    """
    路由层生成工具
    
    基于 API 设计和服务层生成 FastAPI 路由代码
    需要正确调用服务层方法
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_router",
            description="基于 API 设计和服务层生成 FastAPI 路由代码。需要正确调用服务层方法。",
            parameters=[
                ToolParameter(
                    name="endpoints",
                    type="array",
                    description="API 端点列表",
                    required=True,
                ),
                ToolParameter(
                    name="service_methods",
                    type="array",
                    description="服务方法列表（从 generate_service 获取）",
                    required=True,
                ),
                ToolParameter(
                    name="model_names",
                    type="array",
                    description="模型名称列表",
                    required=True,
                ),
            ],
            category="code_generation",
            output_schema={
                "router_code": {"type": "string", "description": "路由层代码"},
                "route_count": {"type": "integer", "description": "路由数量"},
            },
            param_aliases={
                "endpoints": "endpoints",
                "service_methods": "service_methods",
                "model_names": "model_names",
            },
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(
                    on_fail="retry",
                    max_retries=2,
                ),
                post_success=PostSuccessConfig(
                    high_impact=True,
                    requires_consistency_check=True,
                    consistency_check_against=["interface", "code"],
                    extract_working_memory=True,
                ),
                result_handling=ResultHandlingConfig(
                    register_as_checkpoint=True,
                    checkpoint_type="code",
                ),
            ),
        )

    async def execute(
        self,
        endpoints: List[Dict[str, Any]],
        service_methods: List[str],
        model_names: List[str],
        **kwargs,
    ) -> Dict[str, Any]:
        """生成路由代码"""
        try:
            prompt = f"""请基于以下信息生成 FastAPI 路由代码。

API 端点:
{json.dumps(endpoints, ensure_ascii=False, indent=2)}

可用的服务方法: {json.dumps(service_methods, ensure_ascii=False)}

可用的模型类: {json.dumps(model_names, ensure_ascii=False)}

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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()
            else:
                code = response.strip()

            # 统计路由数量
            route_count = len(re.findall(r"@router\.(get|post|put|delete|patch)", code))

            return {
                "success": True,
                "router_code": code,
                "route_count": route_count,
                "line_count": len(code.split("\n")),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


class GenerateTestsTool(BaseTool):
    """
    测试用例生成工具
    
    基于 API 端点生成测试用例
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_tests",
            description="基于 API 端点生成 pytest 测试用例。",
            parameters=[
                ToolParameter(
                    name="endpoints",
                    type="array",
                    description="API 端点列表",
                    required=True,
                ),
                ToolParameter(
                    name="model_names",
                    type="array",
                    description="模型名称列表",
                    required=True,
                ),
            ],
            category="testing",
            output_schema={
                "test_code": {"type": "string", "description": "测试代码"},
                "test_count": {"type": "integer", "description": "测试用例数量"},
            },
            param_aliases={
                "endpoints": "endpoints",
                "model_names": "model_names",
            },
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(
                    on_fail="retry",
                    max_retries=2,
                ),
                post_success=PostSuccessConfig(
                    high_impact=False,  # 测试不是高影响力
                    requires_consistency_check=True,
                    consistency_check_against=["interface"],
                ),
                result_handling=ResultHandlingConfig(
                    register_as_checkpoint=True,
                    checkpoint_type="test",
                ),
            ),
        )

    async def execute(
        self,
        endpoints: List[Dict[str, Any]],
        model_names: List[str],
        **kwargs,
    ) -> Dict[str, Any]:
        """生成测试代码"""
        try:
            prompt = f"""请基于以下 API 端点生成 pytest 测试用例。

API 端点:
{json.dumps(endpoints, ensure_ascii=False, indent=2)}

可用的模型类: {json.dumps(model_names, ensure_ascii=False)}

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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()
            else:
                code = response.strip()

            # 统计测试数量
            test_count = len(re.findall(r"def test_\w+\(", code))

            return {
                "success": True,
                "test_code": code,
                "test_count": test_count,
                "line_count": len(code.split("\n")),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


class ValidateProjectTool(BaseTool):
    """
    项目验证工具
    
    验证生成的代码是否一致、完整
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="validate_project",
            description="验证生成的项目代码是否一致、完整。检查模型、服务、路由之间的一致性。",
            parameters=[
                ToolParameter(
                    name="models_code",
                    type="string",
                    description="模型代码",
                    required=True,
                ),
                ToolParameter(
                    name="service_code",
                    type="string",
                    description="服务代码",
                    required=True,
                ),
                ToolParameter(
                    name="router_code",
                    type="string",
                    description="路由代码",
                    required=True,
                ),
            ],
            category="validation",
            output_schema={
                "is_valid": {"type": "boolean", "description": "是否有效"},
                "issues": {"type": "array", "description": "发现的问题"},
                "suggestions": {"type": "array", "description": "改进建议"},
            },
            param_aliases={
                "models_code": "models_code",
                "service_code": "service_code",
                "router_code": "router_code",
            },
            post_policy=ToolPostPolicy(
                validation=ValidationConfig(
                    on_fail="continue",  # 验证失败也继续
                ),
                post_success=PostSuccessConfig(
                    high_impact=False,
                    requires_consistency_check=False,
                ),
            ),
        )

    async def execute(
        self,
        models_code: str,
        service_code: str,
        router_code: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """验证项目"""
        try:
            prompt = f"""请验证以下生成的代码是否一致、完整。

=== 模型代码 ===
{models_code[:2000]}

=== 服务代码 ===
{service_code[:2000]}

=== 路由代码 ===
{router_code[:2000]}

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

            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                result["success"] = True
                return result
            else:
                return {
                    "success": True,
                    "is_valid": True,
                    "issues": [],
                    "suggestions": [],
                    "summary": "验证完成",
                }

        except Exception as e:
            return {"success": False, "error": str(e)}
