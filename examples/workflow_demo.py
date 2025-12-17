"""
完整工作流演示 - 从 Markdown 解析到 Agent 执行到可视化报告

演示流程：
1. 定义 Agent Markdown
2. 解析 Agent 定义
3. 注册工具
4. 执行任务（带回调）
5. 生成 HTML/Markdown 可视化报告
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, List

from auto_agent import BaseTool, ToolRegistry, func_tool
from auto_agent.models import ExecutionPlan, PlanStep, SubTaskResult

# ============================================================
# 1. Agent Markdown 定义
# ============================================================

AGENT_MARKDOWN = """
## API 服务生成智能体

你是一个专业的 API 服务代码生成助手，能够根据用户需求生成完整的 TypeScript 服务代码。

### 目标
- 理解用户的 API 需求
- 分析现有代码结构
- 生成符合规范的 TypeScript 服务代码
- 确保代码质量和一致性

### 约束
- 生成的代码必须符合 TypeScript 规范
- 使用 async/await 处理异步操作
- 遵循 RESTful API 设计原则
- 代码需要有完整的类型定义

### 执行步骤

1. 调用 [analyze_requirement] 工具，分析用户需求，提取关键信息
2. 调用 [analyze_code_structure] 工具，分析现有代码结构和模式
3. 调用 [generate_types] 工具，生成 TypeScript 类型定义
4. 调用 [generate_service] 工具，生成服务代码
5. 调用 [validate_code] 工具，验证生成的代码质量
"""


# ============================================================
# 2. 定义工具
# ============================================================


class StepCallback:
    """步骤回调管理器"""

    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        self.start_time = time.time()

    def on_step_start(self, step_id: str, tool_name: str, description: str):
        """步骤开始回调"""
        print(f"\n🔄 步骤 {step_id} 开始: {tool_name}")
        print(f"   描述: {description}")
        self.steps.append(
            {
                "step_id": step_id,
                "tool_name": tool_name,
                "description": description,
                "status": "running",
                "start_time": time.time(),
                "result": None,
            }
        )

    def on_step_complete(self, step_id: str, result: Dict[str, Any]):
        """步骤完成回调"""
        for step in self.steps:
            if step["step_id"] == step_id:
                step["status"] = "success" if result.get("success") else "failed"
                step["end_time"] = time.time()
                step["duration"] = step["end_time"] - step["start_time"]
                step["result"] = result

                status_icon = "✅" if result.get("success") else "❌"
                print(f"{status_icon} 步骤 {step_id} 完成 ({step['duration']:.2f}s)")
                break

    def on_step_error(self, step_id: str, error: str):
        """步骤错误回调"""
        for step in self.steps:
            if step["step_id"] == step_id:
                step["status"] = "error"
                step["error"] = error
                step["end_time"] = time.time()
                print(f"❌ 步骤 {step_id} 错误: {error}")
                break


# 全局回调实例
callback = StepCallback()


@func_tool(
    name="analyze_requirement",
    description="分析用户需求，提取关键信息",
    category="analysis",
)
async def analyze_requirement(query: str, context: str = "") -> dict:
    """
    分析用户需求

    Args:
        query: 用户的需求描述
        context: 额外上下文信息
    """
    await asyncio.sleep(0.5)  # 模拟处理时间

    # 模拟分析结果
    return {
        "success": True,
        "intent": "generate_api_service",
        "entities": {
            "service_name": "writingTemplateService",
            "resource": "WritingTemplate",
            "operations": ["list", "get", "create", "upload", "delete"],
        },
        "requirements": [
            "TypeScript 类型定义",
            "RESTful API 调用",
            "文件上传支持",
        ],
    }


@func_tool(
    name="analyze_code_structure",
    description="分析现有代码结构和模式",
    category="analysis",
)
async def analyze_code_structure(file_path: str) -> dict:
    """
    分析代码结构

    Args:
        file_path: 要分析的文件路径
    """
    await asyncio.sleep(0.3)

    # 模拟代码分析
    return {
        "success": True,
        "file_type": "typescript",
        "patterns": {
            "import_style": "named_imports",
            "export_style": "object_export",
            "async_style": "async_await",
            "type_style": "interface",
        },
        "dependencies": ["request", "ApiResponse"],
        "structure": {
            "interfaces": ["WritingTemplate", "WritingTemplateCreate"],
            "service_object": "writingTemplateService",
            "methods": 5,
        },
    }


@func_tool(
    name="generate_types",
    description="生成 TypeScript 类型定义",
    category="generation",
)
async def generate_types(
    resource_name: str,
    fields: str = "",
) -> dict:
    """
    生成类型定义

    Args:
        resource_name: 资源名称
        fields: 字段定义（JSON 格式）
    """
    await asyncio.sleep(0.4)

    generated_types = """
export interface WritingTemplate {
    id: number;
    title: string;
    theme: string;
    content: string;
    description?: string;
    tags: string[];
    template_id: number;
    word_count?: number;
    created_at: string;
}

export interface WritingTemplateCreate {
    title: string;
    theme: string;
    content: string;
    template_id: number;
    description?: string;
    tags?: string[];
}
"""

    return {
        "success": True,
        "types": generated_types.strip(),
        "type_count": 2,
        "interfaces": ["WritingTemplate", "WritingTemplateCreate"],
    }


@func_tool(
    name="generate_service",
    description="生成服务代码",
    category="generation",
)
async def generate_service(
    service_name: str,
    operations: str = "",
    base_path: str = "",
) -> dict:
    """
    生成服务代码

    Args:
        service_name: 服务名称
        operations: 操作列表（JSON 格式）
        base_path: API 基础路径
    """
    await asyncio.sleep(0.6)

    generated_code = """
export const writingTemplateService = {
    // 获取写作样例列表
    getTemplates: (templateId: number) =>
        request.get<ApiResponse<WritingTemplate[]>>(
            `/writing-templates/?template_id=${templateId}`
        ),

    // 获取样例详情
    getTemplate: (id: number) =>
        request.get<ApiResponse<WritingTemplate>>(`/writing-templates/${id}`),

    // 创建写作样例
    createTemplate: (data: WritingTemplateCreate) =>
        request.post<ApiResponse<WritingTemplate>>("/writing-templates/", data),

    // 上传文件创建样例
    uploadFile: (formData: FormData) =>
        request.post<ApiResponse<WritingTemplate>>(
            "/writing-templates/upload",
            formData,
            { headers: { "Content-Type": "multipart/form-data" } }
        ),

    // 删除样例
    deleteTemplate: (id: number) =>
        request.delete<ApiResponse<void>>(`/writing-templates/${id}`),
};
"""

    return {
        "success": True,
        "code": generated_code.strip(),
        "method_count": 5,
        "methods": [
            "getTemplates",
            "getTemplate",
            "createTemplate",
            "uploadFile",
            "deleteTemplate",
        ],
    }


@func_tool(
    name="validate_code",
    description="验证生成的代码质量",
    category="validation",
)
async def validate_code(code: str, language: str = "typescript") -> dict:
    """
    验证代码质量

    Args:
        code: 要验证的代码
        language: 编程语言
    """
    await asyncio.sleep(0.3)

    return {
        "success": True,
        "valid": True,
        "checks": {
            "syntax": "pass",
            "types": "pass",
            "style": "pass",
            "best_practices": "pass",
        },
        "warnings": [],
        "suggestions": [
            "考虑添加错误处理",
            "可以添加请求重试逻辑",
        ],
    }


# ============================================================
# 3. 执行引擎（带回调）
# ============================================================


class WorkflowExecutor:
    """工作流执行器"""

    def __init__(self, registry: ToolRegistry, callback: StepCallback):
        self.registry = registry
        self.callback = callback
        self.state: Dict[str, Any] = {}
        self.results: List[SubTaskResult] = []

    async def execute_plan(self, plan: ExecutionPlan, query: str) -> Dict[str, Any]:
        """执行计划"""
        print(f"\n{'=' * 60}")
        print(f"🚀 开始执行计划: {query}")
        print(f"{'=' * 60}")
        print(f"总步骤数: {len(plan.subtasks)}")

        self.state["query"] = query
        start_time = time.time()

        for step in plan.subtasks:
            step_id = f"step_{step.id}"

            # 回调：步骤开始
            self.callback.on_step_start(step_id, step.tool, step.description)

            try:
                # 获取工具
                tool = self.registry.get_tool(step.tool)
                if not tool:
                    raise ValueError(f"工具未找到: {step.tool}")

                # 构建参数
                args = self._build_arguments(step, tool)

                # 执行工具
                result = await tool.execute(**args)

                # 保存结果
                self.state[step.tool] = result
                self.results.append(
                    SubTaskResult(
                        step_id=str(step.id),
                        success=result.get("success", False),
                        output=result,
                        error=None,
                        metadata={"tool": step.tool},
                    )
                )

                # 回调：步骤完成
                self.callback.on_step_complete(step_id, result)

            except Exception as e:
                error_msg = str(e)
                self.results.append(
                    SubTaskResult(
                        step_id=str(step.id),
                        success=False,
                        output={},
                        error=error_msg,
                        metadata={"tool": step.tool},
                    )
                )
                self.callback.on_step_error(step_id, error_msg)

        total_time = time.time() - start_time

        print(f"\n{'=' * 60}")
        print(f"✅ 执行完成! 总耗时: {total_time:.2f}s")
        print(f"{'=' * 60}")

        return {
            "success": all(r.success for r in self.results),
            "total_time": total_time,
            "steps": len(self.results),
            "results": self.results,
            "state": self.state,
        }

    def _build_arguments(self, step: PlanStep, tool: BaseTool) -> Dict[str, Any]:
        """构建工具参数"""
        args = {}
        definition = tool.definition

        for param in definition.parameters:
            # 从 step.parameters 获取
            if step.parameters and param.name in step.parameters:
                args[param.name] = step.parameters[param.name]
            # 从 state 获取
            elif param.name == "query":
                args["query"] = self.state.get("query", "")
            elif param.name == "code":
                # 从之前的生成结果获取
                if "generate_service" in self.state:
                    args["code"] = self.state["generate_service"].get("code", "")
            elif param.name == "file_path":
                args["file_path"] = "frontend/src/services/writingTemplate.ts"
            elif param.name == "resource_name":
                if "analyze_requirement" in self.state:
                    args["resource_name"] = self.state["analyze_requirement"][
                        "entities"
                    ]["resource"]
            elif param.name == "service_name":
                if "analyze_requirement" in self.state:
                    args["service_name"] = self.state["analyze_requirement"][
                        "entities"
                    ]["service_name"]
            elif param.default is not None:
                args[param.name] = param.default

        return args


# ============================================================
# 4. 报告生成器
# ============================================================


class WorkflowReportGenerator:
    """工作流报告生成器"""

    @staticmethod
    def generate_html_report(
        agent_name: str,
        query: str,
        plan: ExecutionPlan,
        results: List[SubTaskResult],
        callback: StepCallback,
        state: Dict[str, Any],
    ) -> str:
        """生成 HTML 报告"""

        # 计算统计
        total_steps = len(results)
        success_steps = sum(1 for r in results if r.success)
        total_time = sum(s.get("duration", 0) for s in callback.steps)

        # 生成 Mermaid 流程图
        mermaid = WorkflowReportGenerator._generate_mermaid(plan, results)

        # 生成步骤详情
        steps_html = WorkflowReportGenerator._generate_steps_html(callback.steps)

        # 生成结果详情
        results_html = WorkflowReportGenerator._generate_results_html(results, state)

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent 执行报告 - {agent_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .card {{
            background: white;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        h1 {{ color: #1a1a2e; margin-bottom: 8px; }}
        h2 {{ color: #16213e; margin-bottom: 16px; border-bottom: 2px solid #667eea; padding-bottom: 8px; }}
        .header {{ text-align: center; color: white; margin-bottom: 30px; }}
        .header h1 {{ color: white; font-size: 2.5em; }}
        .header p {{ opacity: 0.9; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }}
        .stat {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }}
        .stat-value {{ font-size: 2em; font-weight: bold; }}
        .stat-label {{ opacity: 0.9; font-size: 0.9em; }}
        .mermaid {{ background: #f8f9fa; padding: 20px; border-radius: 8px; }}
        .step {{
            border-left: 4px solid #667eea;
            padding: 16px;
            margin-bottom: 16px;
            background: #f8f9fa;
            border-radius: 0 8px 8px 0;
        }}
        .step.success {{ border-left-color: #10b981; }}
        .step.failed {{ border-left-color: #ef4444; }}
        .step-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .step-title {{ font-weight: 600; color: #1a1a2e; }}
        .step-time {{ color: #6b7280; font-size: 0.9em; }}
        .step-desc {{ color: #4b5563; margin-bottom: 8px; }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 500;
        }}
        .badge-success {{ background: #d1fae5; color: #065f46; }}
        .badge-failed {{ background: #fee2e2; color: #991b1b; }}
        pre {{
            background: #1a1a2e;
            color: #e2e8f0;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 0.9em;
        }}
        .result-section {{ margin-top: 16px; }}
        .result-title {{ font-weight: 600; color: #374151; margin-bottom: 8px; }}
        .query-box {{
            background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .query-label {{ font-weight: 600; color: #92400e; }}
        .query-text {{ color: #78350f; margin-top: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 {agent_name}</h1>
            <p>执行报告 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
        
        <div class="card">
            <h2>📊 执行概览</h2>
            <div class="query-box">
                <div class="query-label">用户查询</div>
                <div class="query-text">{query}</div>
            </div>
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{total_steps}</div>
                    <div class="stat-label">总步骤</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{success_steps}</div>
                    <div class="stat-label">成功</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{total_steps - success_steps}</div>
                    <div class="stat-label">失败</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{total_time:.2f}s</div>
                    <div class="stat-label">总耗时</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>🔄 执行流程</h2>
            <div class="mermaid">
{mermaid}
            </div>
        </div>
        
        <div class="card">
            <h2>📝 步骤详情</h2>
            {steps_html}
        </div>
        
        <div class="card">
            <h2>📦 执行结果</h2>
            {results_html}
        </div>
    </div>
    
    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
</body>
</html>"""

        return html

    @staticmethod
    def _generate_mermaid(plan: ExecutionPlan, results: List[SubTaskResult]) -> str:
        """生成 Mermaid 流程图"""
        lines = ["graph TD"]
        lines.append("    Start([🚀 开始]) --> Step1")

        result_map = {r.step_id: r for r in results}

        for i, step in enumerate(plan.subtasks):
            step_num = i + 1
            next_num = step_num + 1
            result = result_map.get(str(step.id))

            status = "✅" if result and result.success else "❌"
            lines.append(f"    Step{step_num}[{status} {step.tool}]")

            if step_num < len(plan.subtasks):
                lines.append(f"    Step{step_num} --> Step{next_num}")
            else:
                lines.append(f"    Step{step_num} --> End([🏁 完成])")

        return "\n".join(lines)

    @staticmethod
    def _generate_steps_html(steps: List[Dict[str, Any]]) -> str:
        """生成步骤 HTML"""
        html_parts = []

        for step in steps:
            status_class = "success" if step["status"] == "success" else "failed"
            badge_class = (
                "badge-success" if step["status"] == "success" else "badge-failed"
            )
            badge_text = "成功" if step["status"] == "success" else "失败"
            duration = step.get("duration", 0)

            html_parts.append(f"""
            <div class="step {status_class}">
                <div class="step-header">
                    <span class="step-title">{step["step_id"]}: {step["tool_name"]}</span>
                    <span class="badge {badge_class}">{badge_text}</span>
                </div>
                <div class="step-desc">{step["description"]}</div>
                <div class="step-time">⏱️ 耗时: {duration:.3f}s</div>
            </div>
            """)

        return "\n".join(html_parts)

    @staticmethod
    def _generate_results_html(
        results: List[SubTaskResult], state: Dict[str, Any]
    ) -> str:
        """生成结果 HTML"""
        html_parts = []

        for result in results:
            if result.success and result.output:
                result_json = json.dumps(result.output, ensure_ascii=False, indent=2)
                tool_name = result.metadata.get("tool", result.step_id)
                html_parts.append(f"""
                <div class="result-section">
                    <div class="result-title">📌 {tool_name}</div>
                    <pre>{result_json}</pre>
                </div>
                """)

        return "\n".join(html_parts)

    @staticmethod
    def generate_markdown_report(
        agent_name: str,
        query: str,
        plan: ExecutionPlan,
        results: List[SubTaskResult],
        callback: StepCallback,
        state: Dict[str, Any],
    ) -> str:
        """生成 Markdown 报告"""

        total_steps = len(results)
        success_steps = sum(1 for r in results if r.success)
        total_time = sum(s.get("duration", 0) for s in callback.steps)

        md = f"""# 🤖 {agent_name} - 执行报告

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 📋 执行概览

| 指标 | 值 |
|------|-----|
| 用户查询 | {query} |
| 总步骤 | {total_steps} |
| 成功步骤 | {success_steps} |
| 失败步骤 | {total_steps - success_steps} |
| 总耗时 | {total_time:.2f}s |

## 🔄 执行流程

```mermaid
{WorkflowReportGenerator._generate_mermaid(plan, results)}
```

## 📝 步骤详情

"""

        for step in callback.steps:
            status = "✅" if step["status"] == "success" else "❌"
            duration = step.get("duration", 0)
            md += f"""### {status} {step["step_id"]}: {step["tool_name"]}

- **描述**: {step["description"]}
- **状态**: {step["status"]}
- **耗时**: {duration:.3f}s

"""

        md += "## 📦 执行结果\n\n"

        for result in results:
            if result.success and result.output:
                result_json = json.dumps(result.output, ensure_ascii=False, indent=2)
                tool_name = result.metadata.get("tool", result.step_id)
                md += f"""### {tool_name}

```json
{result_json}
```

"""

        return md


# ============================================================
# 5. 主函数
# ============================================================


async def main():
    """主函数 - 完整工作流演示"""

    print("=" * 60)
    print("🚀 完整工作流演示")
    print("=" * 60)

    # 1. 解析 Agent Markdown
    print("\n📄 步骤 1: 解析 Agent Markdown 定义")
    print("-" * 40)

    # 由于没有真实 LLM，我们手动构建 AgentDefinition
    from auto_agent.core.editor.parser import AgentDefinition

    agent_def = AgentDefinition(
        name="API 服务生成智能体",
        description="专业的 API 服务代码生成助手",
        goals=[
            "理解用户的 API 需求",
            "分析现有代码结构",
            "生成符合规范的 TypeScript 服务代码",
            "确保代码质量和一致性",
        ],
        constraints=[
            "生成的代码必须符合 TypeScript 规范",
            "使用 async/await 处理异步操作",
            "遵循 RESTful API 设计原则",
        ],
        initial_plan=[
            PlanStep(
                id=1,
                tool="analyze_requirement",
                description="分析用户需求，提取关键信息",
            ),
            PlanStep(
                id=2,
                tool="analyze_code_structure",
                description="分析现有代码结构和模式",
            ),
            PlanStep(
                id=3, tool="generate_types", description="生成 TypeScript 类型定义"
            ),
            PlanStep(id=4, tool="generate_service", description="生成服务代码"),
            PlanStep(id=5, tool="validate_code", description="验证生成的代码质量"),
        ],
    )

    print(f"✅ Agent 名称: {agent_def.name}")
    print(f"✅ 目标数量: {len(agent_def.goals)}")
    print(f"✅ 步骤数量: {len(agent_def.initial_plan)}")

    # 2. 注册工具
    print("\n🔧 步骤 2: 注册工具")
    print("-" * 40)

    from auto_agent import get_global_registry

    registry = get_global_registry()

    # 工具已通过 @func_tool 装饰器自动注册
    tools = registry.get_all_tools()
    print(f"✅ 已注册工具: {[t.definition.name for t in tools]}")

    # 3. 创建执行计划
    print("\n📋 步骤 3: 创建执行计划")
    print("-" * 40)

    plan = ExecutionPlan(
        intent="generate_api_service",
        subtasks=agent_def.initial_plan,
        state_schema={
            "query": "string",
            "analyze_requirement": "object",
            "analyze_code_structure": "object",
            "generate_types": "object",
            "generate_service": "object",
            "validate_code": "object",
        },
    )

    print(f"✅ 计划步骤: {len(plan.subtasks)}")
    for step in plan.subtasks:
        print(f"   {step.id}. {step.tool}: {step.description}")

    # 4. 执行工作流
    print("\n⚡ 步骤 4: 执行工作流")
    print("-" * 40)

    query = "根据 writingTemplate.ts 的代码结构，生成一个类似的 API 服务"

    executor = WorkflowExecutor(registry, callback)
    execution_result = await executor.execute_plan(plan, query)

    # 5. 生成报告
    print("\n📊 步骤 5: 生成可视化报告")
    print("-" * 40)

    # 生成 HTML 报告
    html_report = WorkflowReportGenerator.generate_html_report(
        agent_name=agent_def.name,
        query=query,
        plan=plan,
        results=executor.results,
        callback=callback,
        state=executor.state,
    )

    html_path = "workflow_report.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)
    print(f"✅ HTML 报告已生成: {html_path}")

    # 生成 Markdown 报告
    md_report = WorkflowReportGenerator.generate_markdown_report(
        agent_name=agent_def.name,
        query=query,
        plan=plan,
        results=executor.results,
        callback=callback,
        state=executor.state,
    )

    md_path = "workflow_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"✅ Markdown 报告已生成: {md_path}")

    # 6. 显示摘要
    print("\n" + "=" * 60)
    print("📈 执行摘要")
    print("=" * 60)
    print(f"总步骤: {len(executor.results)}")
    print(f"成功: {sum(1 for r in executor.results if r.success)}")
    print(f"失败: {sum(1 for r in executor.results if not r.success)}")
    print(f"总耗时: {execution_result['total_time']:.2f}s")

    # 显示生成的代码
    if "generate_service" in executor.state:
        print("\n📝 生成的服务代码:")
        print("-" * 40)
        print(executor.state["generate_service"].get("code", ""))

    print("\n" + "=" * 60)
    print("✅ 演示完成!")
    print(f"📄 查看 HTML 报告: {html_path}")
    print(f"📄 查看 Markdown 报告: {md_path}")
    print("=" * 60)

    return execution_result


if __name__ == "__main__":
    asyncio.run(main())
