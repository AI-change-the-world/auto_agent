"""
纪委案件办理智能体演示

基于 writer_agent_v3.md 构建智能体：
1. 解析 Agent Markdown 定义
2. 注册对应工具
3. 执行任务（带回调）
4. 生成可视化报告
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from auto_agent import (
    AgentMarkdownParser,
    BaseTool,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    func_tool,
    get_global_registry,
)
from auto_agent.models import ExecutionPlan, PlanStep, SubTaskResult


# ============================================================
# Agent Markdown 定义 (来自 writer_agent_v3.md)
# ============================================================

AGENT_MARKDOWN = """
## 纪委案件办理智能体

你是一个纪委工作人员，主要是侦办相关案件

### 目标
- 准确判断案件类型
- 查询相关指导性案例
- 查询相关论文研究
- 生成专业的办案备忘录

### 约束
- 备忘录只针对案件类型提出注意点
- 不展示典型案例或相关案件信息
- 保持专业性和保密性

### 执行步骤

1. 调用 [classify_case] 工具，根据案件内容判断类型（公车私用、非法侵占、职务犯罪等）
2. 调用 [search_guidance_cases] 工具，根据案件类型查询相关指导性案例
3. 调用 [search_research_papers] 工具，查询相关论文研究，找到突破方向
4. 调用 [generate_memo] 工具，根据以上内容生成办案备忘录
"""


# ============================================================
# 步骤回调管理器
# ============================================================

@dataclass
class StepRecord:
    """步骤记录"""
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
    """执行回调管理器"""
    
    def __init__(self):
        self.steps: List[StepRecord] = []
        self.start_time = time.time()
    
    def on_step_start(self, step_id: str, tool_name: str, description: str):
        """步骤开始"""
        print(f"\n{'─'*50}")
        print(f"🔄 步骤 {step_id}: {tool_name}")
        print(f"   📝 {description}")
        print(f"{'─'*50}")
        
        self.steps.append(StepRecord(
            step_id=step_id,
            tool_name=tool_name,
            description=description,
            status="running",
            start_time=time.time(),
        ))
    
    def on_step_complete(self, step_id: str, result: Dict[str, Any]):
        """步骤完成"""
        for step in self.steps:
            if step.step_id == step_id:
                step.status = "success" if result.get("success") else "failed"
                step.end_time = time.time()
                step.duration = step.end_time - step.start_time
                step.result = result
                
                icon = "✅" if result.get("success") else "❌"
                print(f"{icon} 完成 ({step.duration:.2f}s)")
                
                # 显示关键结果
                self._print_result_summary(result)
                break
    
    def on_step_error(self, step_id: str, error: str):
        """步骤错误"""
        for step in self.steps:
            if step.step_id == step_id:
                step.status = "error"
                step.error = error
                step.end_time = time.time()
                print(f"❌ 错误: {error}")
                break
    
    def _print_result_summary(self, result: Dict[str, Any]):
        """打印结果摘要"""
        if "case_types" in result:
            print(f"   📋 案件类型: {', '.join(result['case_types'])}")
        if "cases_count" in result:
            print(f"   📚 找到 {result['cases_count']} 个指导性案例")
        if "papers_count" in result:
            print(f"   📄 找到 {result['papers_count']} 篇相关论文")
        if "memo_title" in result:
            print(f"   📝 备忘录: {result['memo_title']}")


# 全局回调实例
callback = ExecutionCallback()


# ============================================================
# 定义工具
# ============================================================

@func_tool(
    name="classify_case",
    description="根据案件内容判断案件类型（公车私用、非法侵占、职务犯罪等）",
    category="analysis",
)
async def classify_case(case_content: str) -> dict:
    """
    分析案件内容，判断案件类型
    
    Args:
        case_content: 案件描述内容
    """
    await asyncio.sleep(0.8)  # 模拟分析时间
    
    # 模拟案件分类逻辑
    case_types = []
    keywords_map = {
        "公车私用": ["公车", "私用", "车辆", "出行"],
        "非法侵占": ["侵占", "挪用", "私吞", "占有"],
        "职务犯罪": ["受贿", "贪污", "滥用职权", "玩忽职守"],
        "违规收受礼品": ["礼品", "礼金", "红包", "宴请"],
        "违反中央八项规定": ["公款吃喝", "超标准", "违规"],
    }
    
    content_lower = case_content.lower()
    for case_type, keywords in keywords_map.items():
        if any(kw in content_lower for kw in keywords):
            case_types.append(case_type)
    
    if not case_types:
        case_types = ["其他违纪违法行为"]
    
    return {
        "success": True,
        "case_types": case_types,
        "primary_type": case_types[0],
        "confidence": 0.85,
        "analysis": {
            "risk_level": "中等" if len(case_types) == 1 else "较高",
            "complexity": "复杂" if len(case_types) > 1 else "一般",
        },
    }


@func_tool(
    name="search_guidance_cases",
    description="根据案件类型查询相关指导性案例",
    category="retrieval",
)
async def search_guidance_cases(case_type: str, limit: int = 5) -> dict:
    """
    查询指导性案例
    
    Args:
        case_type: 案件类型
        limit: 返回数量限制
    """
    await asyncio.sleep(0.6)
    
    # 模拟指导性案例数据
    guidance_cases = {
        "公车私用": [
            {"id": "GC2023001", "title": "某局长公车私用案", "key_points": ["认定标准", "处分依据"]},
            {"id": "GC2023002", "title": "某处长节假日公车私用案", "key_points": ["时间认定", "责任划分"]},
        ],
        "非法侵占": [
            {"id": "GC2022015", "title": "某科长侵占公款案", "key_points": ["金额认定", "追缴程序"]},
            {"id": "GC2022018", "title": "某主任挪用资金案", "key_points": ["挪用与侵占区分", "量刑标准"]},
        ],
        "职务犯罪": [
            {"id": "GC2023010", "title": "某副局长受贿案", "key_points": ["受贿认定", "证据收集"]},
            {"id": "GC2023012", "title": "某处长滥用职权案", "key_points": ["职权范围", "损失认定"]},
        ],
    }
    
    cases = guidance_cases.get(case_type, [
        {"id": "GC2023099", "title": "一般违纪案例", "key_points": ["程序规范", "处分标准"]}
    ])
    
    return {
        "success": True,
        "case_type": case_type,
        "cases": cases[:limit],
        "cases_count": len(cases[:limit]),
        "key_insights": [
            f"针对{case_type}案件，需重点关注证据链完整性",
            "注意区分主观故意与客观过失",
            "严格按照程序规范办理",
        ],
    }


@func_tool(
    name="search_research_papers",
    description="查询相关论文研究，找到可能的突破方向",
    category="retrieval",
)
async def search_research_papers(case_type: str, keywords: str = "") -> dict:
    """
    查询相关论文研究
    
    Args:
        case_type: 案件类型
        keywords: 额外关键词
    """
    await asyncio.sleep(0.5)
    
    # 模拟论文数据
    papers = {
        "公车私用": [
            {
                "title": "公车私用行为的认定与处理研究",
                "author": "张某某",
                "year": 2023,
                "insights": ["GPS轨迹作为证据的效力", "私用时间的界定标准"],
            },
            {
                "title": "新形势下公车管理制度完善研究",
                "author": "李某某",
                "year": 2022,
                "insights": ["制度漏洞分析", "预防机制建设"],
            },
        ],
        "职务犯罪": [
            {
                "title": "职务犯罪证据收集与固定研究",
                "author": "王某某",
                "year": 2023,
                "insights": ["电子证据采集", "言词证据固定"],
            },
            {
                "title": "监察体制改革背景下职务犯罪侦查研究",
                "author": "赵某某",
                "year": 2022,
                "insights": ["留置措施适用", "与司法衔接"],
            },
        ],
    }
    
    paper_list = papers.get(case_type, [
        {
            "title": "纪检监察工作规范化研究",
            "author": "陈某某",
            "year": 2023,
            "insights": ["程序规范", "证据标准"],
        }
    ])
    
    # 提取突破方向
    breakthrough_directions = []
    for paper in paper_list:
        breakthrough_directions.extend(paper.get("insights", []))
    
    return {
        "success": True,
        "case_type": case_type,
        "papers": paper_list,
        "papers_count": len(paper_list),
        "breakthrough_directions": list(set(breakthrough_directions)),
    }


@func_tool(
    name="generate_memo",
    description="根据分析结果生成办案备忘录",
    category="generation",
)
async def generate_memo(
    case_types: str,
    key_insights: str,
    breakthrough_directions: str,
) -> dict:
    """
    生成办案备忘录
    
    Args:
        case_types: 案件类型（JSON 格式）
        key_insights: 关键洞察（JSON 格式）
        breakthrough_directions: 突破方向（JSON 格式）
    """
    await asyncio.sleep(0.7)
    
    # 解析输入
    try:
        types = json.loads(case_types) if isinstance(case_types, str) else case_types
    except:
        types = [case_types]
    
    try:
        insights = json.loads(key_insights) if isinstance(key_insights, str) else key_insights
    except:
        insights = [key_insights]
    
    try:
        directions = json.loads(breakthrough_directions) if isinstance(breakthrough_directions, str) else breakthrough_directions
    except:
        directions = [breakthrough_directions]
    
    # 生成备忘录
    primary_type = types[0] if types else "未分类案件"
    
    memo_content = f"""# 办案备忘录

## 一、案件类型判定

本案经初步分析，主要涉及以下违纪违法类型：
"""
    
    for i, t in enumerate(types, 1):
        memo_content += f"\n{i}. **{t}**"
    
    memo_content += f"""

## 二、办案注意事项

### （一）证据收集要点
"""
    
    evidence_points = {
        "公车私用": [
            "调取车辆GPS行驶轨迹记录",
            "核实用车审批手续",
            "询问相关知情人员",
            "调取加油卡使用记录",
        ],
        "非法侵占": [
            "固定财务凭证和账目",
            "追溯资金流向",
            "核实资产权属",
            "收集书证物证",
        ],
        "职务犯罪": [
            "及时固定电子数据",
            "规范留置措施使用",
            "做好言词证据固定",
            "注意证据链完整性",
        ],
    }
    
    points = evidence_points.get(primary_type, ["按规范程序收集证据"])
    for point in points:
        memo_content += f"\n- {point}"
    
    memo_content += """

### （二）程序规范要求

- 严格执行审批程序
- 保障当事人合法权益
- 做好全程留痕记录
- 注意保密工作要求

### （三）可能的突破方向
"""
    
    for direction in directions[:5]:
        memo_content += f"\n- {direction}"
    
    memo_content += """

### （四）风险防控提示

- 注意办案安全
- 防止串供毁证
- 做好舆情应对准备
- 严格遵守办案纪律

## 三、下一步工作建议

1. 制定详细的调查方案
2. 明确分工和时间节点
3. 做好证据收集和固定
4. 及时请示汇报重大事项

---
*本备忘录仅供内部参考，请注意保密*
"""
    
    return {
        "success": True,
        "memo_title": f"{primary_type}案件办案备忘录",
        "memo_content": memo_content,
        "word_count": len(memo_content),
        "sections": ["案件类型判定", "办案注意事项", "下一步工作建议"],
    }



# ============================================================
# 执行器
# ============================================================

class CaseAgentExecutor:
    """案件智能体执行器"""
    
    def __init__(self, registry: ToolRegistry, callback: ExecutionCallback):
        self.registry = registry
        self.callback = callback
        self.state: Dict[str, Any] = {}
        self.results: List[SubTaskResult] = []
    
    async def execute(self, plan: ExecutionPlan, case_content: str) -> Dict[str, Any]:
        """执行计划"""
        print(f"\n{'='*60}")
        print(f"🚀 开始执行案件分析")
        print(f"{'='*60}")
        print(f"📋 案件内容: {case_content[:100]}...")
        print(f"📊 总步骤数: {len(plan.subtasks)}")
        
        self.state["case_content"] = case_content
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
                args = self._build_arguments(step)
                
                # 执行工具
                result = await tool.execute(**args)
                
                # 保存结果到状态
                self.state[step.tool] = result
                
                # 记录结果
                self.results.append(SubTaskResult(
                    step_id=str(step.id),
                    success=result.get("success", False),
                    output=result,
                    metadata={"tool": step.tool},
                ))
                
                # 回调：步骤完成
                self.callback.on_step_complete(step_id, result)
                
            except Exception as e:
                error_msg = str(e)
                self.results.append(SubTaskResult(
                    step_id=str(step.id),
                    success=False,
                    output={},
                    error=error_msg,
                    metadata={"tool": step.tool},
                ))
                self.callback.on_step_error(step_id, error_msg)
        
        total_time = time.time() - start_time
        
        print(f"\n{'='*60}")
        print(f"✅ 执行完成! 总耗时: {total_time:.2f}s")
        print(f"{'='*60}")
        
        return {
            "success": all(r.success for r in self.results),
            "total_time": total_time,
            "results": self.results,
            "state": self.state,
        }
    
    def _build_arguments(self, step: PlanStep) -> Dict[str, Any]:
        """构建工具参数"""
        args = {}
        
        if step.tool == "classify_case":
            args["case_content"] = self.state.get("case_content", "")
            
        elif step.tool == "search_guidance_cases":
            classify_result = self.state.get("classify_case", {})
            args["case_type"] = classify_result.get("primary_type", "其他")
            args["limit"] = 5
            
        elif step.tool == "search_research_papers":
            classify_result = self.state.get("classify_case", {})
            args["case_type"] = classify_result.get("primary_type", "其他")
            
        elif step.tool == "generate_memo":
            classify_result = self.state.get("classify_case", {})
            guidance_result = self.state.get("search_guidance_cases", {})
            papers_result = self.state.get("search_research_papers", {})
            
            args["case_types"] = json.dumps(classify_result.get("case_types", []))
            args["key_insights"] = json.dumps(guidance_result.get("key_insights", []))
            args["breakthrough_directions"] = json.dumps(papers_result.get("breakthrough_directions", []))
        
        return args


# ============================================================
# 报告生成器
# ============================================================

class CaseReportGenerator:
    """案件报告生成器"""
    
    @staticmethod
    def generate_html(
        agent_name: str,
        case_content: str,
        callback: ExecutionCallback,
        results: List[SubTaskResult],
        state: Dict[str, Any],
    ) -> str:
        """生成 HTML 报告"""
        
        total_steps = len(results)
        success_steps = sum(1 for r in results if r.success)
        total_time = sum(s.duration for s in callback.steps)
        
        # 获取备忘录内容
        memo_result = state.get("generate_memo", {})
        memo_content = memo_result.get("memo_content", "").replace("\n", "<br>")
        
        # 生成步骤 HTML
        steps_html = ""
        for step in callback.steps:
            status_class = "success" if step.status == "success" else "failed"
            icon = "✅" if step.status == "success" else "❌"
            steps_html += f'''
            <div class="step {status_class}">
                <div class="step-header">
                    <span class="step-icon">{icon}</span>
                    <span class="step-title">{step.step_id}: {step.tool_name}</span>
                    <span class="step-time">{step.duration:.2f}s</span>
                </div>
                <div class="step-desc">{step.description}</div>
            </div>
            '''
        
        # 生成 Mermaid 流程图
        mermaid = "graph TD\n    Start([🚀 开始]) --> S1\n"
        for i, step in enumerate(callback.steps):
            icon = "✅" if step.status == "success" else "❌"
            mermaid += f"    S{i+1}[{icon} {step.tool_name}]\n"
            if i < len(callback.steps) - 1:
                mermaid += f"    S{i+1} --> S{i+2}\n"
            else:
                mermaid += f"    S{i+1} --> End([🏁 完成])\n"
        
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{agent_name} - 执行报告</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            padding: 20px;
            color: #e2e8f0;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ text-align: center; padding: 40px 0; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .header p {{ opacity: 0.8; }}
        .card {{
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        h2 {{ color: #60a5fa; margin-bottom: 16px; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
        }}
        .stat {{
            background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }}
        .stat-value {{ font-size: 2em; font-weight: bold; }}
        .stat-label {{ opacity: 0.9; font-size: 0.9em; }}
        .step {{
            background: rgba(255,255,255,0.05);
            border-left: 4px solid #3b82f6;
            padding: 16px;
            margin-bottom: 12px;
            border-radius: 0 8px 8px 0;
        }}
        .step.success {{ border-left-color: #10b981; }}
        .step.failed {{ border-left-color: #ef4444; }}
        .step-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
        .step-icon {{ font-size: 1.2em; }}
        .step-title {{ font-weight: 600; flex: 1; }}
        .step-time {{ color: #94a3b8; }}
        .step-desc {{ color: #94a3b8; font-size: 0.9em; }}
        .mermaid {{ background: rgba(255,255,255,0.95); padding: 20px; border-radius: 8px; }}
        .memo {{
            background: #fff;
            color: #1a1a2e;
            padding: 30px;
            border-radius: 8px;
            line-height: 1.8;
        }}
        .memo h1 {{ color: #1a1a2e; font-size: 1.5em; margin-bottom: 20px; }}
        .memo h2 {{ color: #3b82f6; font-size: 1.2em; margin: 20px 0 10px; }}
        .memo h3 {{ color: #1a1a2e; font-size: 1em; margin: 15px 0 8px; }}
        .case-box {{
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.3);
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .case-label {{ color: #60a5fa; font-weight: 600; margin-bottom: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 {agent_name}</h1>
            <p>执行报告 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </div>
        
        <div class="card">
            <h2>📋 案件信息</h2>
            <div class="case-box">
                <div class="case-label">案件内容</div>
                <div>{case_content}</div>
            </div>
        </div>
        
        <div class="card">
            <h2>📊 执行概览</h2>
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
                    <div class="stat-value">{total_time:.1f}s</div>
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
            <h2>📄 生成的办案备忘录</h2>
            <div class="memo">
                {memo_content}
            </div>
        </div>
    </div>
    <script>mermaid.initialize({{startOnLoad: true, theme: 'default'}});</script>
</body>
</html>'''
        
        return html
    
    @staticmethod
    def generate_markdown(
        agent_name: str,
        case_content: str,
        callback: ExecutionCallback,
        results: List[SubTaskResult],
        state: Dict[str, Any],
    ) -> str:
        """生成 Markdown 报告"""
        
        total_steps = len(results)
        success_steps = sum(1 for r in results if r.success)
        total_time = sum(s.duration for s in callback.steps)
        
        memo_result = state.get("generate_memo", {})
        memo_content = memo_result.get("memo_content", "")
        
        # Mermaid 流程图
        mermaid = "graph TD\n    Start([🚀 开始]) --> S1\n"
        for i, step in enumerate(callback.steps):
            icon = "✅" if step.status == "success" else "❌"
            mermaid += f"    S{i+1}[{icon} {step.tool_name}]\n"
            if i < len(callback.steps) - 1:
                mermaid += f"    S{i+1} --> S{i+2}\n"
            else:
                mermaid += f"    S{i+1} --> End([🏁 完成])\n"
        
        md = f'''# 🔍 {agent_name} - 执行报告

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 📋 案件信息

{case_content}

## 📊 执行概览

| 指标 | 值 |
|------|-----|
| 总步骤 | {total_steps} |
| 成功 | {success_steps} |
| 失败 | {total_steps - success_steps} |
| 总耗时 | {total_time:.2f}s |

## 🔄 执行流程

```mermaid
{mermaid}
```

## 📝 步骤详情

'''
        
        for step in callback.steps:
            icon = "✅" if step.status == "success" else "❌"
            md += f'''### {icon} {step.step_id}: {step.tool_name}

- **描述**: {step.description}
- **状态**: {step.status}
- **耗时**: {step.duration:.3f}s

'''
        
        md += f'''## 📄 生成的办案备忘录

{memo_content}
'''
        
        return md



# ============================================================
# 主函数
# ============================================================

async def main():
    """主函数"""
    
    print("=" * 60)
    print("🔍 纪委案件办理智能体演示")
    print("=" * 60)
    
    # 1. 读取 Agent Markdown（这里直接使用内置定义）
    print("\n📄 步骤 1: 解析 Agent Markdown")
    print("-" * 40)
    
    from auto_agent.core.editor.parser import AgentDefinition
    
    agent_def = AgentDefinition(
        name="纪委案件办理智能体",
        description="侦办纪委相关案件的智能助手",
        goals=[
            "准确判断案件类型",
            "查询相关指导性案例",
            "查询相关论文研究",
            "生成专业的办案备忘录",
        ],
        constraints=[
            "备忘录只针对案件类型提出注意点",
            "不展示典型案例或相关案件信息",
            "保持专业性和保密性",
        ],
        initial_plan=[
            PlanStep(id=1, tool="classify_case", description="根据案件内容判断类型"),
            PlanStep(id=2, tool="search_guidance_cases", description="查询相关指导性案例"),
            PlanStep(id=3, tool="search_research_papers", description="查询相关论文研究"),
            PlanStep(id=4, tool="generate_memo", description="生成办案备忘录"),
        ],
    )
    
    print(f"✅ Agent: {agent_def.name}")
    print(f"✅ 目标: {len(agent_def.goals)} 个")
    print(f"✅ 步骤: {len(agent_def.initial_plan)} 个")
    
    # 2. 注册工具
    print("\n🔧 步骤 2: 注册工具")
    print("-" * 40)
    
    registry = get_global_registry()
    tools = registry.get_all_tools()
    
    # 过滤出本演示的工具
    demo_tools = ["classify_case", "search_guidance_cases", "search_research_papers", "generate_memo"]
    available = [t.definition.name for t in tools if t.definition.name in demo_tools]
    print(f"✅ 已注册工具: {available}")
    
    # 3. 创建执行计划
    print("\n📋 步骤 3: 创建执行计划")
    print("-" * 40)
    
    plan = ExecutionPlan(
        intent="case_analysis",
        subtasks=agent_def.initial_plan,
        state_schema={},
    )
    
    for step in plan.subtasks:
        print(f"   {step.id}. {step.tool}: {step.description}")
    
    # 4. 模拟案件内容
    case_content = """
    某市交通局副局长张某，在2022年至2023年期间，多次使用公务车辆接送子女上下学，
    并在节假日期间驾驶公车外出旅游。经初步调查，张某还涉嫌收受下属单位负责人礼品礼金，
    金额约5万元。此外，张某在工程招标过程中，涉嫌为特定企业提供便利，收受好处费。
    """
    
    # 5. 执行
    print("\n⚡ 步骤 4: 执行案件分析")
    print("-" * 40)
    
    executor = CaseAgentExecutor(registry, callback)
    result = await executor.execute(plan, case_content.strip())
    
    # 6. 生成报告
    print("\n📊 步骤 5: 生成可视化报告")
    print("-" * 40)
    
    # HTML 报告
    html_report = CaseReportGenerator.generate_html(
        agent_name=agent_def.name,
        case_content=case_content.strip(),
        callback=callback,
        results=executor.results,
        state=executor.state,
    )
    
    html_path = "case_report.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_report)
    print(f"✅ HTML 报告: {html_path}")
    
    # Markdown 报告
    md_report = CaseReportGenerator.generate_markdown(
        agent_name=agent_def.name,
        case_content=case_content.strip(),
        callback=callback,
        results=executor.results,
        state=executor.state,
    )
    
    md_path = "case_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"✅ Markdown 报告: {md_path}")
    
    # 7. 显示生成的备忘录
    print("\n" + "=" * 60)
    print("📄 生成的办案备忘录")
    print("=" * 60)
    
    memo_result = executor.state.get("generate_memo", {})
    if memo_result.get("memo_content"):
        print(memo_result["memo_content"])
    
    print("\n" + "=" * 60)
    print("✅ 演示完成!")
    print(f"📄 HTML 报告: {html_path}")
    print(f"📄 Markdown 报告: {md_path}")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
