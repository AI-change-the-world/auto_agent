"""
LLM 驱动的智能体完整演示

真正由大模型自主规划和执行：
1. 解析 Agent Markdown 定义
2. LLM 自主规划执行步骤
3. 执行工具（带回调）
4. 生成可视化报告

需要配置环境变量：
- DEEPSEEK_API_KEY 或 OPENAI_API_KEY
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from auto_agent import (
    OpenAIClient,
    ToolRegistry,
    BaseTool,
    ToolDefinition,
    ToolParameter,
    func_tool,
    get_global_registry,
)
from auto_agent.core.planner import TaskPlanner
from auto_agent.core.executor import ExecutionEngine
from auto_agent.core.editor.parser import AgentDefinition, AgentMarkdownParser
from auto_agent.models import ExecutionPlan, PlanStep, SubTaskResult
from auto_agent.retry.models import RetryConfig


# ============================================================
# Agent Markdown 定义 (来自 writer_agent_v3.md)
# ============================================================

AGENT_MARKDOWN = """
## 纪委案件办理智能体

你是一个纪委工作人员，主要是侦办相关案件

你需要：

首先根据我给你的内容，判断案件属于哪些类型，比如是公车私用，非法侵占，职务犯罪还是其他。

然后，根据类型，查询相关的指导性案例。

然后，根据类型，查询相关的论文研究，找到一些可能的突破方向。

根据以上内容，写一个办案备忘录。备忘录中只需要针对案件类型，提出具体的需要注意的点，不需要展示典型案例或者相关案件信息

### 目标
- 准确判断案件类型
- 查询相关指导性案例
- 查询相关论文研究
- 生成专业的办案备忘录

### 约束
- 备忘录只针对案件类型提出注意点
- 不展示典型案例或相关案件信息
- 保持专业性和保密性
"""


# ============================================================
# 执行回调
# ============================================================

@dataclass
class StepRecord:
    step_id: str
    tool_name: str
    description: str
    status: str = "pending"
    start_time: float = 0
    end_time: float = 0
    duration: float = 0
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ExecutionCallback:
    """执行回调"""
    
    def __init__(self):
        self.steps: List[StepRecord] = []
        self.plan_json: Optional[Dict] = None
    
    def on_plan_generated(self, plan: ExecutionPlan):
        """规划完成回调"""
        print(f"\n{'='*60}")
        print("📋 LLM 生成的执行计划")
        print(f"{'='*60}")
        print(f"意图: {plan.intent}")
        print(f"步骤数: {len(plan.subtasks)}")
        for step in plan.subtasks:
            print(f"  {step.id}. [{step.tool}] {step.description}")
        if plan.expected_outcome:
            print(f"预期结果: {plan.expected_outcome}")
    
    async def on_step_complete(self, step: PlanStep, result: SubTaskResult):
        """步骤完成回调"""
        record = StepRecord(
            step_id=str(step.id),
            tool_name=step.tool or "unknown",
            description=step.description,
            status="success" if result.success else "failed",
            end_time=time.time(),
            result=result.output or {},
            error=result.error,
        )
        
        # 计算耗时
        if self.steps:
            record.start_time = self.steps[-1].end_time
        else:
            record.start_time = record.end_time - 0.5
        record.duration = record.end_time - record.start_time
        
        self.steps.append(record)
        
        icon = "✅" if result.success else "❌"
        print(f"\n{icon} 步骤 {step.id} 完成: {step.tool}")
        print(f"   描述: {step.description}")
        print(f"   耗时: {record.duration:.2f}s")
        
        if result.error:
            print(f"   错误: {result.error}")
        elif result.output:
            self._print_result_summary(result.output)
    
    def _print_result_summary(self, result: Dict[str, Any]):
        """打印结果摘要"""
        if "case_types" in result:
            print(f"   📋 案件类型: {result['case_types']}")
        if "cases" in result:
            print(f"   📚 指导性案例: {len(result['cases'])} 个")
        if "papers" in result:
            print(f"   📄 相关论文: {len(result['papers'])} 篇")
        if "memo_title" in result:
            print(f"   📝 备忘录: {result['memo_title']}")


callback = ExecutionCallback()


# ============================================================
# 定义工具（模拟实现）
# ============================================================

@func_tool(
    name="classify_case",
    description="根据案件内容判断案件类型，如公车私用、非法侵占、职务犯罪、违规收受礼品等",
    category="analysis",
)
async def classify_case(case_content: str) -> dict:
    """
    分析案件内容，判断案件类型
    
    Args:
        case_content: 案件描述内容
    """
    await asyncio.sleep(0.5)
    
    case_types = []
    keywords_map = {
        "公车私用": ["公车", "私用", "车辆", "出行", "接送"],
        "非法侵占": ["侵占", "挪用", "私吞", "占有"],
        "职务犯罪": ["受贿", "贪污", "滥用职权", "玩忽职守", "好处费"],
        "违规收受礼品": ["礼品", "礼金", "红包", "宴请"],
    }
    
    for case_type, keywords in keywords_map.items():
        if any(kw in case_content for kw in keywords):
            case_types.append(case_type)
    
    if not case_types:
        case_types = ["其他违纪违法行为"]
    
    return {
        "success": True,
        "case_types": case_types,
        "primary_type": case_types[0],
        "analysis": {
            "risk_level": "较高" if len(case_types) > 1 else "中等",
            "complexity": "复杂" if len(case_types) > 1 else "一般",
        },
    }


@func_tool(
    name="search_guidance_cases",
    description="根据案件类型查询相关的指导性案例，获取办案参考",
    category="retrieval",
)
async def search_guidance_cases(case_type: str, limit: int = 5) -> dict:
    """
    查询指导性案例
    
    Args:
        case_type: 案件类型
        limit: 返回数量
    """
    await asyncio.sleep(0.4)
    
    cases_db = {
        "公车私用": [
            {"id": "GC2023001", "title": "某局长公车私用案", "key_points": ["GPS轨迹认定", "处分依据"]},
            {"id": "GC2023002", "title": "某处长节假日公车私用案", "key_points": ["时间认定", "责任划分"]},
        ],
        "职务犯罪": [
            {"id": "GC2023010", "title": "某副局长受贿案", "key_points": ["受贿认定", "证据收集"]},
            {"id": "GC2023012", "title": "某处长滥用职权案", "key_points": ["职权范围", "损失认定"]},
        ],
        "违规收受礼品": [
            {"id": "GC2022020", "title": "某科长收受礼金案", "key_points": ["金额认定", "退还情节"]},
        ],
    }
    
    cases = cases_db.get(case_type, [{"id": "GC0000", "title": "通用案例", "key_points": ["程序规范"]}])
    
    return {
        "success": True,
        "case_type": case_type,
        "cases": cases[:limit],
        "key_insights": [
            f"针对{case_type}案件，需重点关注证据链完整性",
            "注意区分主观故意与客观过失",
        ],
    }


@func_tool(
    name="search_research_papers",
    description="查询相关的论文研究，找到可能的突破方向和办案思路",
    category="retrieval",
)
async def search_research_papers(case_type: str) -> dict:
    """
    查询相关论文
    
    Args:
        case_type: 案件类型
    """
    await asyncio.sleep(0.3)
    
    papers_db = {
        "公车私用": [
            {"title": "公车私用行为认定研究", "insights": ["GPS轨迹证据效力", "私用时间界定"]},
            {"title": "公车管理制度完善研究", "insights": ["制度漏洞分析", "预防机制"]},
        ],
        "职务犯罪": [
            {"title": "职务犯罪证据收集研究", "insights": ["电子证据采集", "言词证据固定"]},
        ],
    }
    
    papers = papers_db.get(case_type, [{"title": "纪检监察规范化研究", "insights": ["程序规范"]}])
    
    directions = []
    for p in papers:
        directions.extend(p.get("insights", []))
    
    return {
        "success": True,
        "case_type": case_type,
        "papers": papers,
        "breakthrough_directions": list(set(directions)),
    }


@func_tool(
    name="generate_memo",
    description="根据案件分析结果生成办案备忘录，包含注意事项和建议",
    category="generation",
)
async def generate_memo(
    case_types: str,
    key_insights: str = "",
    breakthrough_directions: str = "",
) -> dict:
    """
    生成办案备忘录
    
    Args:
        case_types: 案件类型列表
        key_insights: 关键洞察
        breakthrough_directions: 突破方向
    """
    await asyncio.sleep(0.5)
    
    try:
        types = json.loads(case_types) if isinstance(case_types, str) else [case_types]
    except:
        types = [str(case_types)]
    
    primary_type = types[0] if types else "未分类"
    
    evidence_points = {
        "公车私用": ["调取GPS轨迹", "核实审批手续", "询问知情人", "调取加油记录"],
        "职务犯罪": ["固定电子数据", "规范留置措施", "做好言词证据", "注意证据链"],
        "违规收受礼品": ["核实礼品来源", "确认金额价值", "调查利益关联", "查明退还情况"],
    }
    
    points = evidence_points.get(primary_type, ["按规范程序收集证据"])
    
    memo = f"""# 办案备忘录

## 一、案件类型判定

本案涉及以下违纪违法类型：
"""
    for t in types:
        memo += f"\n- **{t}**"
    
    memo += f"""

## 二、办案注意事项

### （一）证据收集要点
"""
    for p in points:
        memo += f"\n- {p}"
    
    memo += """

### （二）程序规范要求

- 严格执行审批程序
- 保障当事人合法权益
- 做好全程留痕记录

### （三）风险防控

- 注意办案安全
- 防止串供毁证
- 严格遵守办案纪律

## 三、下一步建议

1. 制定详细调查方案
2. 明确分工和时间节点
3. 及时请示汇报重大事项

---
*本备忘录仅供内部参考*
"""
    
    return {
        "success": True,
        "memo_title": f"{primary_type}案件办案备忘录",
        "memo_content": memo,
        "word_count": len(memo),
    }



# ============================================================
# 报告生成器
# ============================================================

class ReportGenerator:
    """报告生成器"""
    
    @staticmethod
    def generate_html(
        agent_name: str,
        query: str,
        plan: ExecutionPlan,
        callback: ExecutionCallback,
        state: Dict[str, Any],
    ) -> str:
        """生成 HTML 报告"""
        
        total = len(callback.steps)
        success = sum(1 for s in callback.steps if s.status == "success")
        total_time = sum(s.duration for s in callback.steps)
        
        memo = state.get("generate_memo", {}).get("memo_content", "").replace("\n", "<br>")
        
        # 步骤 HTML
        steps_html = ""
        for s in callback.steps:
            icon = "✅" if s.status == "success" else "❌"
            steps_html += f'''
            <div class="step {'success' if s.status == 'success' else 'failed'}">
                <div class="step-header">
                    <span>{icon} {s.step_id}: {s.tool_name}</span>
                    <span class="time">{s.duration:.2f}s</span>
                </div>
                <div class="desc">{s.description}</div>
            </div>'''
        
        # Mermaid
        mermaid = "graph TD\n    Start([开始]) --> S1\n"
        for i, s in enumerate(callback.steps):
            icon = "✅" if s.status == "success" else "❌"
            mermaid += f"    S{i+1}[{icon} {s.tool_name}]\n"
            if i < len(callback.steps) - 1:
                mermaid += f"    S{i+1} --> S{i+2}\n"
            else:
                mermaid += f"    S{i+1} --> End([完成])\n"
        
        # 计划详情
        plan_html = "<ul>"
        for step in plan.subtasks:
            plan_html += f"<li><b>{step.id}. {step.tool}</b>: {step.description}</li>"
        plan_html += "</ul>"
        
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{agent_name} - 执行报告</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        h1 {{ text-align: center; margin: 30px 0; font-size: 2em; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 20px; margin: 20px 0; }}
        h2 {{ color: #60a5fa; margin-bottom: 15px; font-size: 1.2em; }}
        .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }}
        .stat {{ background: linear-gradient(135deg, #3b82f6, #8b5cf6); padding: 15px; border-radius: 8px; text-align: center; }}
        .stat-val {{ font-size: 1.8em; font-weight: bold; }}
        .stat-label {{ opacity: 0.9; font-size: 0.9em; }}
        .step {{ background: #334155; padding: 12px; margin: 8px 0; border-radius: 6px; border-left: 3px solid #3b82f6; }}
        .step.success {{ border-left-color: #10b981; }}
        .step.failed {{ border-left-color: #ef4444; }}
        .step-header {{ display: flex; justify-content: space-between; font-weight: 600; }}
        .time {{ color: #94a3b8; }}
        .desc {{ color: #94a3b8; font-size: 0.9em; margin-top: 5px; }}
        .mermaid {{ background: #fff; padding: 20px; border-radius: 8px; }}
        .memo {{ background: #fff; color: #1e293b; padding: 25px; border-radius: 8px; line-height: 1.8; }}
        .query {{ background: #334155; padding: 15px; border-radius: 8px; margin-bottom: 15px; }}
        .query-label {{ color: #60a5fa; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 {agent_name}</h1>
        <p style="text-align:center;opacity:0.7;">执行报告 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <div class="card">
            <h2>📋 任务信息</h2>
            <div class="query">
                <div class="query-label">用户查询</div>
                <div style="margin-top:8px;">{query[:500]}...</div>
            </div>
        </div>
        
        <div class="card">
            <h2>📊 执行概览</h2>
            <div class="stats">
                <div class="stat"><div class="stat-val">{total}</div><div class="stat-label">总步骤</div></div>
                <div class="stat"><div class="stat-val">{success}</div><div class="stat-label">成功</div></div>
                <div class="stat"><div class="stat-val">{total-success}</div><div class="stat-label">失败</div></div>
                <div class="stat"><div class="stat-val">{total_time:.1f}s</div><div class="stat-label">总耗时</div></div>
            </div>
        </div>
        
        <div class="card">
            <h2>🤖 LLM 生成的执行计划</h2>
            <p style="margin-bottom:10px;color:#94a3b8;">意图: {plan.intent}</p>
            {plan_html}
        </div>
        
        <div class="card">
            <h2>🔄 执行流程</h2>
            <div class="mermaid">{mermaid}</div>
        </div>
        
        <div class="card">
            <h2>📝 步骤详情</h2>
            {steps_html}
        </div>
        
        <div class="card">
            <h2>📄 生成的办案备忘录</h2>
            <div class="memo">{memo}</div>
        </div>
    </div>
    <script>mermaid.initialize({{startOnLoad:true}});</script>
</body>
</html>'''
    
    @staticmethod
    def generate_markdown(
        agent_name: str,
        query: str,
        plan: ExecutionPlan,
        callback: ExecutionCallback,
        state: Dict[str, Any],
    ) -> str:
        """生成 Markdown 报告"""
        
        total = len(callback.steps)
        success = sum(1 for s in callback.steps if s.status == "success")
        total_time = sum(s.duration for s in callback.steps)
        
        memo = state.get("generate_memo", {}).get("memo_content", "")
        
        md = f'''# 🔍 {agent_name} - 执行报告

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 📋 任务信息

**用户查询:**
{query}

## 📊 执行概览

| 指标 | 值 |
|------|-----|
| 总步骤 | {total} |
| 成功 | {success} |
| 失败 | {total-success} |
| 总耗时 | {total_time:.2f}s |

## 🤖 LLM 生成的执行计划

**意图:** {plan.intent}

'''
        for step in plan.subtasks:
            md += f"- **{step.id}. {step.tool}**: {step.description}\n"
        
        md += "\n## 📝 步骤详情\n\n"
        for s in callback.steps:
            icon = "✅" if s.status == "success" else "❌"
            md += f"### {icon} {s.step_id}: {s.tool_name}\n\n"
            md += f"- 描述: {s.description}\n"
            md += f"- 耗时: {s.duration:.2f}s\n\n"
        
        md += f"## 📄 生成的办案备忘录\n\n{memo}\n"
        
        return md


# ============================================================
# 主函数
# ============================================================

async def main():
    """主函数 - LLM 驱动的智能体演示"""
    
    print("=" * 60)
    print("🤖 LLM 驱动的智能体完整演示")
    print("=" * 60)
    
    # 1. 检查 API Key
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.environ.get("OPENAI_MODEL", "deepseek-chat")
    
    if not api_key:
        print("\n❌ 错误: 请设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量")
        print("\n示例:")
        print("  set DEEPSEEK_API_KEY=your-api-key")
        print("  python examples/llm_agent_demo.py")
        return
    
    print(f"\n✅ API 配置:")
    print(f"   Base URL: {base_url}")
    print(f"   Model: {model}")
    
    # 2. 初始化 LLM 客户端
    print("\n📡 初始化 LLM 客户端...")
    llm = OpenAIClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    
    # 3. 获取工具注册表
    registry = get_global_registry()
    tools = registry.get_all_tools()
    demo_tools = ["classify_case", "search_guidance_cases", "search_research_papers", "generate_memo"]
    available = [t.definition.name for t in tools if t.definition.name in demo_tools]
    print(f"✅ 已注册工具: {available}")
    
    # 4. 创建 TaskPlanner（LLM 驱动的规划器）
    print("\n🧠 创建 LLM 规划器...")
    planner = TaskPlanner(
        llm_client=llm,
        tool_registry=registry,
        agent_goals=[
            "准确判断案件类型",
            "查询相关指导性案例",
            "查询相关论文研究",
            "生成专业的办案备忘录",
        ],
        agent_constraints=[
            "备忘录只针对案件类型提出注意点",
            "不展示典型案例或相关案件信息",
            "保持专业性和保密性",
        ],
    )
    
    # 5. 案件内容
    case_content = """
    某市交通局副局长张某，在2022年至2023年期间，多次使用公务车辆接送子女上下学，
    并在节假日期间驾驶公车外出旅游。经初步调查，张某还涉嫌收受下属单位负责人礼品礼金，
    金额约5万元。此外，张某在工程招标过程中，涉嫌为特定企业提供便利，收受好处费。
    """
    
    query = f"请分析以下案件并生成办案备忘录：\n{case_content.strip()}"
    
    # 6. LLM 自主规划
    print("\n" + "=" * 60)
    print("🧠 LLM 自主规划中...")
    print("=" * 60)
    
    try:
        plan = await planner.plan(
            query=query,
            user_context="",
            conversation_context="",
        )
        
        callback.on_plan_generated(plan)
        
    except Exception as e:
        print(f"\n❌ 规划失败: {e}")
        print("使用默认计划...")
        plan = ExecutionPlan(
            intent="case_analysis",
            subtasks=[
                PlanStep(id="1", tool="classify_case", description="判断案件类型"),
                PlanStep(id="2", tool="search_guidance_cases", description="查询指导性案例"),
                PlanStep(id="3", tool="search_research_papers", description="查询论文研究"),
                PlanStep(id="4", tool="generate_memo", description="生成办案备忘录"),
            ],
        )
    
    # 7. 执行计划
    print("\n" + "=" * 60)
    print("⚡ 执行计划中...")
    print("=" * 60)
    
    retry_config = RetryConfig(max_retries=2, base_delay=1.0)
    executor = ExecutionEngine(
        tool_registry=registry,
        retry_config=retry_config,
        llm_client=llm,
    )
    
    state = {
        "inputs": {"query": query, "case_content": case_content.strip()},
        "control": {"max_iterations": 10},
    }
    
    results, final_state = await executor.execute_plan(
        plan=plan,
        state=state,
        conversation_id="demo_001",
        on_step_complete=callback.on_step_complete,
    )
    
    # 8. 生成报告
    print("\n" + "=" * 60)
    print("📊 生成可视化报告...")
    print("=" * 60)
    
    html = ReportGenerator.generate_html(
        agent_name="纪委案件办理智能体",
        query=query,
        plan=plan,
        callback=callback,
        state=final_state,
    )
    
    with open("llm_agent_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ HTML 报告: llm_agent_report.html")
    
    md = ReportGenerator.generate_markdown(
        agent_name="纪委案件办理智能体",
        query=query,
        plan=plan,
        callback=callback,
        state=final_state,
    )
    
    with open("llm_agent_report.md", "w", encoding="utf-8") as f:
        f.write(md)
    print("✅ Markdown 报告: llm_agent_report.md")
    
    # 9. 显示备忘录
    print("\n" + "=" * 60)
    print("📄 生成的办案备忘录")
    print("=" * 60)
    
    memo = final_state.get("generate_memo", {}).get("memo_content", "")
    if memo:
        print(memo)
    else:
        print("未生成备忘录")
    
    # 10. 总结
    print("\n" + "=" * 60)
    print("✅ 演示完成!")
    print("=" * 60)
    success_count = sum(1 for r in results if r.success)
    print(f"总步骤: {len(results)}, 成功: {success_count}, 失败: {len(results) - success_count}")
    print(f"📄 HTML 报告: llm_agent_report.html")
    print(f"📄 Markdown 报告: llm_agent_report.md")


if __name__ == "__main__":
    asyncio.run(main())
