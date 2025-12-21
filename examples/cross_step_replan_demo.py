"""
跨步骤智能规划 Demo - 测试 Replan 优化功能

演示新实现的功能：
1. 任务复杂度分级 (TaskComplexity)
2. 执行策略选择 (ExecutionStrategy)
3. 跨步骤工作记忆 (CrossStepWorkingMemory)
4. 全局一致性检查 (GlobalConsistencyChecker)
5. 增量式重规划 (_incremental_replan)

场景：模拟一个"API 服务项目生成"任务
- 设计 API 接口 → 生成数据模型 → 实现业务逻辑 → 生成测试代码
- 每个步骤都会产生约束，后续步骤必须遵守
- 故意在某些步骤引入不一致，测试一致性检查

使用方法:
    export OPENAI_API_KEY=your-key  # 或 DEEPSEEK_API_KEY
    python examples/cross_step_replan_demo.py
"""

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path，确保使用本地版本
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_agent import (
    AutoAgent,
    BaseTool,
    OpenAIClient,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
)
from auto_agent.models import ToolReplanPolicy

# ==================== LLM 客户端配置 ====================


def get_llm_client() -> Optional[OpenAIClient]:
    """获取 LLM 客户端"""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    return OpenAIClient(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
        model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
        timeout=120.0,
    )


# ==================== 工具定义（带 replan_policy）====================


class DesignAPITool(BaseTool):
    """
    API 接口设计工具

    这是一个高影响力工具，会产生后续步骤必须遵守的接口约束
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="design_api",
            description="设计 API 接口，定义端点、请求/响应格式。这是项目的第一步，会产生后续必须遵守的接口约束。",
            parameters=[
                ToolParameter(
                    name="project_name",
                    type="string",
                    description="项目名称",
                    required=True,
                ),
                ToolParameter(
                    name="requirements",
                    type="string",
                    description="功能需求描述",
                    required=True,
                ),
            ],
            category="design",
            output_schema={
                "api_design": {"type": "object", "description": "API 设计结果"},
                "endpoints": {"type": "array", "description": "端点列表"},
                "constraints": {"type": "array", "description": "接口约束"},
            },
            # 高影响力工具，需要一致性检查
            replan_policy=ToolReplanPolicy(
                high_impact=True,
                requires_consistency_check=True,
                force_replan_check=False,
            ),
        )

    async def execute(
        self,
        project_name: str,
        requirements: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """使用 LLM 设计 API 接口"""
        prompt = f"""请为以下项目设计 RESTful API 接口。

项目名称: {project_name}
功能需求: {requirements}

请返回 JSON 格式的设计结果：
```json
{{
    "project_name": "{project_name}",
    "endpoints": [
        {{
            "method": "GET/POST/PUT/DELETE",
            "path": "/api/xxx",
            "description": "接口描述",
            "request_params": {{"param_name": "type"}},
            "response_schema": {{"field": "type"}}
        }}
    ],
    "data_models": [
        {{
            "name": "ModelName",
            "fields": {{"field_name": "type"}}
        }}
    ],
    "constraints": [
        "所有 ID 字段必须使用整数类型",
        "时间字段使用 ISO 8601 格式"
    ]
}}
```"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2000,
            )

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"success": False, "error": "无法解析 API 设计结果"}

            result["success"] = True
            result["api_design"] = {
                "endpoints": result.get("endpoints", []),
                "data_models": result.get("data_models", []),
            }
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}


class GenerateModelTool(BaseTool):
    """
    数据模型生成工具

    必须基于 API 设计中定义的数据模型，保持一致性
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_model",
            description="根据 API 设计生成数据模型代码。必须与 API 设计中的数据模型定义保持一致。",
            parameters=[
                ToolParameter(
                    name="api_design",
                    type="object",
                    description="API 设计结果（从 design_api 获取）",
                    required=True,
                ),
                ToolParameter(
                    name="language",
                    type="string",
                    description="编程语言: python/typescript/java",
                    required=False,
                ),
            ],
            category="code_generation",
            output_schema={
                "model_code": {"type": "string", "description": "生成的模型代码"},
                "model_definitions": {"type": "object", "description": "模型定义"},
            },
            param_aliases={
                "api_design": "api_design",
            },
            replan_policy=ToolReplanPolicy(
                high_impact=True,
                requires_consistency_check=True,
                consistency_check_against=["interface"],
            ),
        )

    async def execute(
        self,
        api_design: Dict[str, Any],
        language: str = "python",
        **kwargs,
    ) -> Dict[str, Any]:
        """生成数据模型代码"""
        data_models = api_design.get("data_models", [])

        prompt = f"""请根据以下数据模型定义生成 {language} 代码。

数据模型定义:
{json.dumps(data_models, ensure_ascii=False, indent=2)}

要求:
1. 使用 dataclass（Python）或 interface（TypeScript）
2. 添加类型注解
3. 添加文档注释
4. 字段类型必须与定义完全一致

请返回 JSON 格式：
```json
{{
    "language": "{language}",
    "model_code": "完整的模型代码",
    "model_definitions": {{
        "ModelName": {{
            "fields": {{"field": "type"}},
            "methods": []
        }}
    }}
}}
```"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"success": False, "error": "无法解析模型代码"}

            result["success"] = True
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}


class ImplementServiceTool(BaseTool):
    """
    业务逻辑实现工具

    必须使用之前定义的数据模型和 API 接口
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="implement_service",
            description="实现业务逻辑代码。必须使用之前定义的数据模型，实现 API 设计中的端点。",
            parameters=[
                ToolParameter(
                    name="api_design",
                    type="object",
                    description="API 设计结果",
                    required=True,
                ),
                ToolParameter(
                    name="model_definitions",
                    type="object",
                    description="模型定义（从 generate_model 获取）",
                    required=True,
                ),
            ],
            category="code_generation",
            output_schema={
                "service_code": {"type": "string", "description": "服务代码"},
                "implemented_endpoints": {
                    "type": "array",
                    "description": "已实现的端点",
                },
            },
            param_aliases={
                "api_design": "api_design",
                "model_definitions": "model_definitions",
            },
            replan_policy=ToolReplanPolicy(
                high_impact=True,
                requires_consistency_check=True,
                replan_condition="如果实现的接口与设计不一致",
            ),
        )

    async def execute(
        self,
        api_design: Dict[str, Any],
        model_definitions: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """实现业务逻辑"""
        endpoints = api_design.get("endpoints", [])

        prompt = f"""请根据以下 API 设计和数据模型实现业务逻辑代码。

API 端点:
{json.dumps(endpoints, ensure_ascii=False, indent=2)}

数据模型:
{json.dumps(model_definitions, ensure_ascii=False, indent=2)}

要求:
1. 为每个端点实现对应的处理函数
2. 使用定义的数据模型
3. 添加基本的错误处理
4. 函数签名必须与 API 设计一致

请返回 JSON 格式：
```json
{{
    "service_code": "完整的服务代码",
    "implemented_endpoints": [
        {{
            "path": "/api/xxx",
            "method": "GET",
            "function_name": "get_xxx"
        }}
    ]
}}
```"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=3000,
            )

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"success": False, "error": "无法解析服务代码"}

            result["success"] = True
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}


class GenerateTestTool(BaseTool):
    """
    测试代码生成工具

    必须覆盖所有已实现的端点
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_tests",
            description="生成测试代码，覆盖所有已实现的 API 端点。",
            parameters=[
                ToolParameter(
                    name="implemented_endpoints",
                    type="array",
                    description="已实现的端点列表",
                    required=True,
                ),
                ToolParameter(
                    name="model_definitions",
                    type="object",
                    description="模型定义",
                    required=True,
                ),
            ],
            category="testing",
            output_schema={
                "test_code": {"type": "string", "description": "测试代码"},
                "test_coverage": {"type": "object", "description": "测试覆盖情况"},
            },
            param_aliases={
                "implemented_endpoints": "implemented_endpoints",
                "model_definitions": "model_definitions",
            },
        )

    async def execute(
        self,
        implemented_endpoints: List[Dict[str, Any]],
        model_definitions: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """生成测试代码"""
        prompt = f"""请为以下 API 端点生成测试代码。

已实现的端点:
{json.dumps(implemented_endpoints, ensure_ascii=False, indent=2)}

数据模型:
{json.dumps(model_definitions, ensure_ascii=False, indent=2)}

要求:
1. 使用 pytest 框架
2. 为每个端点至少生成 2 个测试用例（正常和异常）
3. 使用 mock 数据

请返回 JSON 格式：
```json
{{
    "test_code": "完整的测试代码",
    "test_coverage": {{
        "total_endpoints": 0,
        "covered_endpoints": 0,
        "test_cases": []
    }}
}}
```"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=8192,
            )

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"success": False, "error": "无法解析测试代码"}

            result["success"] = True
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}


class ReviewCodeTool(BaseTool):
    """
    代码审查工具

    检查代码一致性和质量
    """

    def __init__(self, llm_client: OpenAIClient):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="review_code",
            description="审查生成的代码，检查一致性、质量和潜在问题。",
            parameters=[
                ToolParameter(
                    name="api_design",
                    type="object",
                    description="API 设计",
                    required=True,
                ),
                ToolParameter(
                    name="model_code",
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
            ],
            category="review",
            output_schema={
                "review_result": {"type": "object", "description": "审查结果"},
                "issues": {"type": "array", "description": "发现的问题"},
                "suggestions": {"type": "array", "description": "改进建议"},
            },
            param_aliases={
                "api_design": "api_design",
                "model_code": "model_code",
                "service_code": "service_code",
            },
        )

    async def execute(
        self,
        api_design: Dict[str, Any],
        model_code: str,
        service_code: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """审查代码"""
        prompt = f"""请审查以下代码，检查一致性和质量。

API 设计:
{json.dumps(api_design, ensure_ascii=False, indent=2)[:1500]}

模型代码:
{model_code[:2000]}

服务代码:
{service_code[:2000]}

请检查:
1. 模型是否与 API 设计一致
2. 服务是否正确使用了模型
3. 接口实现是否完整
4. 代码质量问题

请返回 JSON 格式：
```json
{{
    "consistency_score": 0.0-1.0,
    "quality_score": 0.0-1.0,
    "issues": [
        {{"type": "consistency/quality/security", "description": "问题描述", "severity": "high/medium/low"}}
    ],
    "suggestions": ["改进建议1", "改进建议2"],
    "summary": "审查总结"
}}
```"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=2000,
            )

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    return {"success": False, "error": "无法解析审查结果"}

            result["success"] = True
            result["review_result"] = {
                "consistency_score": result.get("consistency_score", 0),
                "quality_score": result.get("quality_score", 0),
                "summary": result.get("summary", ""),
            }
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}


# ==================== 主程序 ====================


async def main():
    """主函数 - 测试跨步骤智能规划功能"""
    print("=" * 70)
    print("🔧 跨步骤智能规划 Demo - 测试 Replan 优化功能")
    print("=" * 70)

    # 1. 获取 LLM 客户端
    llm_client = get_llm_client()
    if not llm_client:
        print("\n❌ 未设置 API Key，请设置环境变量:")
        print("   export OPENAI_API_KEY=your-api-key")
        return

    print("\n✅ LLM 客户端初始化成功")

    # 2. 注册工具
    print("\n🔧 注册工具...")
    registry = ToolRegistry()

    registry.register(DesignAPITool(llm_client))
    registry.register(GenerateModelTool(llm_client))
    registry.register(ImplementServiceTool(llm_client))
    registry.register(GenerateTestTool(llm_client))
    registry.register(ReviewCodeTool(llm_client))

    print(f"   已注册 {len(registry.get_all_tools())} 个工具:")
    for tool in registry.get_all_tools():
        policy = tool.definition.replan_policy
        policy_info = ""
        if policy:
            if policy.high_impact:
                policy_info = " [高影响力]"
            if policy.requires_consistency_check:
                policy_info += " [需一致性检查]"
        print(f"   - {tool.definition.name}{policy_info}")

    # 3. 创建智能体
    print("\n🤖 创建智能体...")
    agent = AutoAgent(
        llm_client=llm_client,
        tool_registry=registry,
        agent_name="API Project Generator",
        agent_description="一个能够自主规划和生成 API 项目代码的智能体",
        agent_goals=[
            "设计清晰的 API 接口",
            "生成一致的数据模型",
            "实现完整的业务逻辑",
            "生成测试代码",
            "确保代码质量",
        ],
        agent_constraints=[
            "后续步骤必须与 API 设计保持一致",
            "数据模型字段类型必须严格遵守",
            "所有端点都必须有对应实现",
        ],
    )

    # 4. 用户需求
    user_query = """
    请帮我创建一个简单的"用户管理 API"项目。

    功能需求：
    1. 用户注册（POST /api/users）
    2. 用户登录（POST /api/auth/login）
    3. 获取用户信息（GET /api/users/{id}）
    4. 更新用户信息（PUT /api/users/{id}）

    请按以下步骤执行：
    1. 首先设计 API 接口
    2. 根据设计生成数据模型
    3. 实现业务逻辑
    4. 生成测试代码
    5. 最后审查代码质量

    注意：每个步骤都要与前面的设计保持一致！
    """

    print("\n" + "=" * 70)
    print("📋 用户需求:")
    print("=" * 70)
    print(user_query.strip())
    print("\n" + "=" * 70)
    print("🚀 智能体开始执行...")
    print("=" * 70)

    # 5. 执行并观察
    execution_log = []
    final_results = {}

    try:
        async for event in agent.run_stream(
            query=user_query,
            user_id="developer",
        ):
            event_type = event.get("event")
            data = event.get("data", {})

            if event_type == "planning":
                print(f"\n📝 {data.get('message', '规划中...')}")

            elif event_type == "execution_plan":
                print("\n" + "-" * 50)
                print("📋 执行计划:")
                print("-" * 50)
                for step in data.get("steps", []):
                    pinned = "📌" if step.get("is_pinned") else "  "
                    print(
                        f"   {pinned} Step {step['step']}: [{step['name']}] {step['description'][:50]}..."
                    )
                print("-" * 50)

            elif event_type == "stage_start":
                step = data.get("step", "?")
                name = data.get("name", "unknown")
                desc = data.get("description", "")
                print(f"\n▶️  Step {step}: {name}")
                print(f"   📝 {desc[:60]}...")

            elif event_type == "stage_complete":
                step = data.get("step", "?")
                name = data.get("name", "unknown")
                success = data.get("success", False)
                result = data.get("result", {}) or {}
                status = "✅" if success else "❌"

                print(f"   {status} 完成")

                if not success:
                    error = result.get("error", "未知错误")
                    print(f"   ❗ 错误: {error}")
                    continue

                # 显示关键输出
                if isinstance(result, dict):
                    if "endpoints" in result:
                        endpoints = result.get("endpoints", [])
                        print(f"   📤 设计了 {len(endpoints)} 个端点")
                        for ep in endpoints[:3]:
                            print(
                                f"      - {ep.get('method', '?')} {ep.get('path', '?')}"
                            )

                    if "model_code" in result:
                        code = result.get("model_code", "")
                        print(f"   📤 生成模型代码 ({len(code)} 字符)")

                    if "service_code" in result:
                        code = result.get("service_code", "")
                        endpoints = result.get("implemented_endpoints", [])
                        print(
                            f"   📤 实现了 {len(endpoints)} 个端点 ({len(code)} 字符)"
                        )

                    if "test_code" in result:
                        code = result.get("test_code", "")
                        coverage = result.get("test_coverage", {})
                        print(f"   📤 生成测试代码 ({len(code)} 字符)")
                        print(
                            f"      覆盖端点: {coverage.get('covered_endpoints', 0)}/{coverage.get('total_endpoints', 0)}"
                        )

                    if "review_result" in result:
                        review = result.get("review_result", {})
                        print(f"   📤 审查结果:")
                        print(f"      一致性: {review.get('consistency_score', 0):.0%}")
                        print(f"      质量: {review.get('quality_score', 0):.0%}")
                        issues = result.get("issues", [])
                        if issues:
                            print(f"      发现 {len(issues)} 个问题")

                # 保存结果
                final_results[name] = result
                execution_log.append(
                    {
                        "step": step,
                        "name": name,
                        "success": success,
                    }
                )

            elif event_type == "consistency_violation":
                violations = data.get("violations", [])
                print(f"\n   ⚠️  一致性违规检测:")
                for v in violations:
                    print(
                        f"      - [{v.get('severity', '?')}] {v.get('description', '')[:60]}..."
                    )

            elif event_type == "stage_replan":
                reason = data.get("reason", "")
                print(f"\n   🔄 触发重规划: {reason[:60]}...")

            elif event_type == "stage_retry":
                print(f"\n   🔄 重试: {data.get('message', '')}")

            elif event_type == "done":
                print("\n" + "=" * 70)
                success = data.get("success", False)
                iterations = data.get("iterations", 0)

                if success:
                    print(f"✅ 执行完成! (共 {iterations} 步)")
                else:
                    print(f"❌ 执行失败: {data.get('message', '')}")

                # 显示追踪统计
                trace = data.get("trace")
                if trace:
                    summary = trace.get("summary", {})
                    llm_calls = summary.get("llm_calls", {})
                    print(f"\n📊 执行统计:")
                    print(f"   - 追踪ID: {trace.get('trace_id', 'N/A')}")
                    print(f"   - LLM调用: {llm_calls.get('count', 0)} 次")
                    print(f"   - Token消耗: {llm_calls.get('total_tokens', 0):,}")

                print("=" * 70)

            elif event_type == "error":
                print(f"\n❌ 错误: {data.get('message', '')}")

        # 6. 显示工作记忆和一致性检查结果
        print("\n" + "=" * 70)
        print("📋 跨步骤智能规划功能验证")
        print("=" * 70)

        # 获取执行上下文（如果可用）
        if hasattr(agent, "_last_context") and agent._last_context:
            ctx = agent._last_context

            # 工作记忆
            wm = ctx.working_memory
            print(f"\n🧠 工作记忆:")
            print(f"   - 设计决策: {len(wm.design_decisions)} 条")
            print(f"   - 约束条件: {len(wm.constraints)} 条")
            print(f"   - 待办事项: {len(wm.todos)} 条")
            print(f"   - 接口定义: {len(wm.interfaces)} 个")

            if wm.design_decisions:
                print("\n   最近的设计决策:")
                for d in wm.design_decisions[-3:]:
                    print(f"      - {d.decision[:50]}...")

            if wm.constraints:
                print("\n   约束条件:")
                for c in wm.constraints[-3:]:
                    print(f"      - [{c.priority}] {c.constraint[:50]}...")

            # 一致性检查器
            checker = ctx.consistency_checker
            print(f"\n🔍 一致性检查:")
            print(f"   - 检查点: {len(checker.checkpoints)} 个")
            print(f"   - 违规记录: {len(checker.violations)} 条")

            if checker.checkpoints:
                print("\n   注册的检查点:")
                for step_id, cp in list(checker.checkpoints.items())[:3]:
                    print(f"      - [{cp.artifact_type}] {cp.description[:40]}...")

            if checker.violations:
                print("\n   违规记录:")
                for v in checker.violations[-3:]:
                    print(f"      - [{v.severity}] {v.description[:50]}...")

        # 7. 显示最终结果摘要
        print("\n" + "=" * 70)
        print("📊 执行结果摘要")
        print("=" * 70)

        success_count = sum(1 for log in execution_log if log.get("success"))
        total_count = len(execution_log)
        print(f"\n   步骤完成: {success_count}/{total_count}")

        if "design_api" in final_results:
            endpoints = final_results["design_api"].get("endpoints", [])
            print(f"   API 端点: {len(endpoints)} 个")

        if "generate_model" in final_results:
            models = final_results["generate_model"].get("model_definitions", {})
            print(f"   数据模型: {len(models)} 个")

        if "implement_service" in final_results:
            impl = final_results["implement_service"].get("implemented_endpoints", [])
            print(f"   实现端点: {len(impl)} 个")

        if "review_code" in final_results:
            review = final_results["review_code"].get("review_result", {})
            print(f"   代码一致性: {review.get('consistency_score', 0):.0%}")
            print(f"   代码质量: {review.get('quality_score', 0):.0%}")

        print("\n" + "=" * 70)

    except Exception as e:
        print(f"\n❌ 执行异常: {e}")
        import traceback

        traceback.print_exc()

    finally:
        await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
