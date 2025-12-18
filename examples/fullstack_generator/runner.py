"""
全栈项目生成器 - 执行器

封装 AutoAgent 的执行逻辑，提供简洁的接口
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from auto_agent import (
    AutoAgent,
    OpenAIClient,
    ToolRegistry,
    ExecutionPlan,
    PlanStep,
    SubTaskResult,
)

from .tools import (
    AnalyzeRequirementsTool,
    DesignAPITool,
    GenerateModelsTool,
    GenerateServiceTool,
    GenerateRouterTool,
    GenerateTestsTool,
    ValidateProjectTool,
)
from .tools_writer import CodeWriterTool, ProjectInitTool


def get_llm_client() -> Optional[OpenAIClient]:
    """获取 LLM 客户端"""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    return OpenAIClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=120.0,
    )


class FullstackGeneratorRunner:
    """
    全栈项目生成器执行器
    
    封装了工具注册、Agent 创建、执行流程
    """

    def __init__(
        self,
        llm_client: Optional[OpenAIClient] = None,
        output_dir: Optional[Path] = None,
    ):
        self.llm_client = llm_client or get_llm_client()
        self.output_dir = output_dir or Path(__file__).parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 执行结果收集
        self.execution_log: List[Dict[str, Any]] = []
        self.collected_plan: Optional[ExecutionPlan] = None
        self.collected_results: List[SubTaskResult] = []
        self.collected_state: Dict[str, Any] = {}
        self.collected_trace: Optional[Dict[str, Any]] = None
        
        # 生成的代码
        self.generated_code: Dict[str, str] = {}

    def _create_registry(self, project_name: str) -> ToolRegistry:
        """创建工具注册表"""
        registry = ToolRegistry()
        
        # 项目输出目录
        project_dir = str(self.output_dir / project_name)
        
        # 注册所有工具
        registry.register(ProjectInitTool(str(self.output_dir)))
        registry.register(AnalyzeRequirementsTool(self.llm_client))
        registry.register(DesignAPITool(self.llm_client))
        registry.register(GenerateModelsTool(self.llm_client))
        registry.register(GenerateServiceTool(self.llm_client))
        registry.register(GenerateRouterTool(self.llm_client))
        registry.register(GenerateTestsTool(self.llm_client))
        registry.register(ValidateProjectTool(self.llm_client))
        registry.register(CodeWriterTool(project_dir))
        
        return registry

    def _create_agent(self, registry: ToolRegistry) -> AutoAgent:
        """创建 Agent"""
        return AutoAgent(
            llm_client=self.llm_client,
            tool_registry=registry,
            agent_name="Fullstack Project Generator",
            agent_description="一个能够自主规划和生成完整 REST API 项目的智能体",
            agent_goals=[
                "分析用户需求，提取实体和关系",
                "设计符合 RESTful 规范的 API",
                "生成类型安全的 Pydantic 模型",
                "生成服务层和路由层代码",
                "确保各层代码的一致性",
            ],
            agent_constraints=[
                "所有代码必须使用 Python 类型注解",
                "ID 参数必须使用 int 类型",
                "必须使用已定义的模型类名",
                "服务方法必须与 API 端点对应",
            ],
        )

    async def run(
        self,
        requirements: str,
        project_name: str = "my_project",
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """
        运行项目生成
        
        Args:
            requirements: 项目需求描述
            project_name: 项目名称
            verbose: 是否显示详细输出
            
        Returns:
            生成结果，包含代码和执行日志
        """
        if not self.llm_client:
            return {
                "success": False,
                "error": "未配置 LLM 客户端，请设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY",
            }

        # 创建工具和 Agent
        registry = self._create_registry(project_name)
        agent = self._create_agent(registry)

        # 构建查询 - 强调每步生成代码后要写入文件
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

        if verbose:
            print("=" * 70)
            print("🚀 全栈项目生成器")
            print("=" * 70)
            print(f"\n📋 项目名称: {project_name}")
            print(f"📝 需求描述:\n{requirements[:200]}...")
            print("\n" + "=" * 70)

        # 重置收集器
        self.execution_log = []
        self.collected_results = []
        self.generated_code = {}

        execution_success = False

        try:
            async for event in agent.run_stream(
                query=query,
                user_id="developer",
            ):
                event_type = event.get("event")
                data = event.get("data", {})

                if event_type == "planning":
                    if verbose:
                        print(f"\n📝 {data.get('message', '规划中...')}")

                elif event_type == "execution_plan":
                    if verbose:
                        print("\n" + "-" * 50)
                        print("📋 执行计划:")
                        print("-" * 50)
                        for step in data.get("steps", []):
                            print(f"   Step {step['step']}: [{step['name']}] {step['description'][:50]}...")
                        print("-" * 50)

                    # 保存计划
                    self.collected_plan = ExecutionPlan(
                        intent=data.get("description", "项目生成"),
                        subtasks=[
                            PlanStep(
                                id=str(s.get("step", i + 1)),
                                tool=s.get("name"),
                                description=s.get("description", ""),
                                expectations=s.get("expectations"),
                            )
                            for i, s in enumerate(data.get("steps", []))
                        ],
                    )

                elif event_type == "stage_start":
                    if verbose:
                        step = data.get("step", "?")
                        name = data.get("name", "unknown")
                        desc = data.get("description", "")[:60]
                        print(f"\n{'─' * 60}")
                        print(f"▶️  Step {step}: {name}")
                        if desc:
                            print(f"   📝 {desc}...")

                elif event_type == "stage_complete":
                    step = data.get("step", "?")
                    name = data.get("name", "unknown")
                    success = data.get("success", False)
                    result = data.get("result", {}) or {}

                    if verbose:
                        status = "✅ 成功" if success else "❌ 失败"
                        print(f"   {status}")

                        # 显示详细结果
                        if success and isinstance(result, dict):
                            self._print_step_result(name, result)
                        elif not success:
                            error = result.get("error", "未知错误") if isinstance(result, dict) else str(result)
                            print(f"   ❗ 错误: {error}")

                    # 收集生成的代码
                    if success and isinstance(result, dict):
                        if "models_code" in result:
                            self.generated_code["models.py"] = result["models_code"]
                        if "service_code" in result:
                            self.generated_code["service.py"] = result["service_code"]
                        if "router_code" in result:
                            self.generated_code["router.py"] = result["router_code"]
                        if "test_code" in result:
                            self.generated_code["test_api.py"] = result["test_code"]

                    # 收集结果
                    self.collected_results.append(
                        SubTaskResult(
                            step_id=str(step),
                            success=success,
                            output=result,
                            error=result.get("error") if isinstance(result, dict) else None,
                        )
                    )

                elif event_type == "stage_retry":
                    if verbose:
                        print(f"\n   🔄 重试: {data.get('message', '')}")

                elif event_type == "stage_replan":
                    if verbose:
                        print(f"\n⚠️  触发重规划: {data.get('reason', '')}")

                elif event_type == "consistency_violation":
                    if verbose:
                        severity = data.get("severity", "warning")
                        message = data.get("message", "")
                        violations = data.get("violations", [])
                        
                        icon = "🔴" if severity == "critical" else "🟡"
                        print(f"\n{icon} 一致性违规 [{severity}]:")
                        if message:
                            print(f"   📋 {message}")
                        
                        if violations:
                            for v in violations:
                                v_severity = v.get("severity", "warning")
                                v_desc = v.get("description", "未知违规")
                                v_suggestion = v.get("suggestion", "")
                                v_checkpoint = v.get("checkpoint_id", "")
                                
                                print(f"   📍 检查点: {v_checkpoint}")
                                print(f"   📝 问题: {v_desc}")
                                if v_suggestion:
                                    print(f"   💡 建议: {v_suggestion}")
                        else:
                            print(f"   📝 问题: 未知违规")

                elif event_type == "done":
                    execution_success = data.get("success", False)
                    self.collected_trace = data.get("trace")
                    
                    if verbose:
                        print("\n" + "=" * 70)
                        if execution_success:
                            print(f"✅ 项目生成完成!")
                        else:
                            print(f"❌ 项目生成失败: {data.get('message', '')}")
                        print("=" * 70)

                elif event_type == "error":
                    if verbose:
                        print(f"\n❌ 错误: {data.get('message', '')}")

        except Exception as e:
            if verbose:
                print(f"\n❌ 执行异常: {e}")
            return {"success": False, "error": str(e)}

        finally:
            await self.llm_client.close()

        # 保存生成的代码
        if self.generated_code:
            await self._save_generated_code(project_name)

        return {
            "success": execution_success,
            "project_name": project_name,
            "generated_files": list(self.generated_code.keys()),
            "output_dir": str(self.output_dir / project_name),
            "trace": self.collected_trace,
        }

    def _print_step_result(self, tool_name: str, result: Dict[str, Any]) -> None:
        """打印步骤执行结果的详细信息"""
        
        if tool_name == "init_project":
            print(f"   📁 项目目录: {result.get('project_dir', 'N/A')}")
            files = result.get("created_files", [])
            if files:
                print(f"   📄 创建文件: {', '.join(files)}")

        elif tool_name == "analyze_requirements":
            entities = result.get("entities", [])
            relationships = result.get("relationships", [])
            rules = result.get("business_rules", [])
            print(f"   📊 分析结果:")
            print(f"      • 实体: {len(entities)} 个")
            if entities:
                entity_names = [e.get("name", "?") for e in entities[:5]]
                print(f"        {', '.join(entity_names)}")
            print(f"      • 关系: {len(relationships)} 个")
            print(f"      • 业务规则: {len(rules)} 条")

        elif tool_name == "design_api":
            endpoints = result.get("endpoints", [])
            schemas = result.get("schemas", {})
            print(f"   🔗 API 设计:")
            print(f"      • 端点: {len(endpoints)} 个")
            if endpoints:
                for ep in endpoints[:5]:
                    method = ep.get("method", "?")
                    path = ep.get("path", "?")
                    print(f"        {method} {path}")
                if len(endpoints) > 5:
                    print(f"        ... 还有 {len(endpoints) - 5} 个端点")
            print(f"      • Schema: {len(schemas)} 个")

        elif tool_name == "generate_models":
            model_names = result.get("model_names", [])
            line_count = result.get("line_count", 0)
            print(f"   📦 模型代码:")
            print(f"      • 代码行数: {line_count} 行")
            print(f"      • 模型类: {len(model_names)} 个")
            if model_names:
                print(f"        {', '.join(model_names[:8])}")
                if len(model_names) > 8:
                    print(f"        ... 还有 {len(model_names) - 8} 个")

        elif tool_name == "generate_service":
            methods = result.get("service_methods", [])
            line_count = result.get("line_count", 0)
            print(f"   ⚙️  服务代码:")
            print(f"      • 代码行数: {line_count} 行")
            print(f"      • 服务方法: {len(methods)} 个")
            if methods:
                print(f"        {', '.join(methods[:6])}")
                if len(methods) > 6:
                    print(f"        ... 还有 {len(methods) - 6} 个")

        elif tool_name == "generate_router":
            route_count = result.get("route_count", 0)
            line_count = result.get("line_count", 0)
            print(f"   🛣️  路由代码:")
            print(f"      • 代码行数: {line_count} 行")
            print(f"      • 路由数量: {route_count} 个")

        elif tool_name == "generate_tests":
            test_count = result.get("test_count", 0)
            line_count = result.get("line_count", 0)
            print(f"   🧪 测试代码:")
            print(f"      • 代码行数: {line_count} 行")
            print(f"      • 测试用例: {test_count} 个")

        elif tool_name == "write_code":
            filename = result.get("filename", "?")
            line_count = result.get("line_count", 0)
            file_path = result.get("file_path", "")
            print(f"   💾 写入文件:")
            print(f"      • 文件: {filename}")
            print(f"      • 行数: {line_count} 行")
            print(f"      • 路径: {file_path}")

        elif tool_name == "validate_project":
            is_valid = result.get("is_valid", False)
            issues = result.get("issues", [])
            suggestions = result.get("suggestions", [])
            status = "✅ 通过" if is_valid else "⚠️ 有问题"
            print(f"   🔍 验证结果: {status}")
            if issues:
                print(f"      • 问题: {len(issues)} 个")
                for issue in issues[:3]:
                    severity = issue.get("severity", "?")
                    desc = issue.get("description", "?")[:50]
                    print(f"        [{severity}] {desc}...")
            if suggestions:
                print(f"      • 建议: {len(suggestions)} 条")

        else:
            # 通用输出
            for key, value in result.items():
                if key in ("success", "error"):
                    continue
                if isinstance(value, str) and len(value) > 100:
                    print(f"   • {key}: {value[:100]}...")
                elif isinstance(value, list):
                    print(f"   • {key}: {len(value)} 项")
                elif isinstance(value, dict):
                    print(f"   • {key}: {len(value)} 个字段")
                else:
                    print(f"   • {key}: {value}")

    async def _save_generated_code(self, project_name: str) -> None:
        """保存生成的代码到文件"""
        project_dir = self.output_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        for filename, code in self.generated_code.items():
            file_path = project_dir / filename
            file_path.write_text(code, encoding="utf-8")
            print(f"   💾 已保存: {file_path}")

        # 生成 __init__.py
        init_content = f'''"""
{project_name} - 自动生成的 REST API 项目

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

from .models import *
from .service import *
from .router import *
'''
        (project_dir / "__init__.py").write_text(init_content, encoding="utf-8")

        # 生成 README
        readme_content = f"""# {project_name}

自动生成的 REST API 项目。

## 生成时间

{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 文件结构

```
{project_name}/
├── __init__.py
├── models.py      # Pydantic 数据模型
├── service.py     # 服务层
├── router.py      # FastAPI 路由
└── test_api.py    # 测试用例
```

## 使用方法

```python
from fastapi import FastAPI
from {project_name}.router import router

app = FastAPI()
app.include_router(router)
```

## 运行测试

```bash
pytest {project_name}/test_api.py -v
```
"""
        (project_dir / "README.md").write_text(readme_content, encoding="utf-8")
        print(f"   💾 已保存: {project_dir / 'README.md'}")
