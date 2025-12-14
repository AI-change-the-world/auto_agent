"""
智能体执行报告生成器

用于生成可视化的执行过程报告，支持 Markdown 和结构化数据导出
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from auto_agent.models import ExecutionPlan, PlanStep, SubTaskResult


class ExecutionReportGenerator:
    """智能体执行报告生成器"""

    @staticmethod
    def generate_report_data(
        agent_name: str,
        query: str,
        plan: ExecutionPlan,
        results: List[SubTaskResult],
        state: Dict[str, Any],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        生成结构化的执行报告数据

        Args:
            agent_name: 智能体名称
            query: 用户查询
            plan: 执行计划
            results: 执行结果列表
            state: 最终状态
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            结构化的报告数据
        """
        result_map = {r.step_id: r for r in results}

        steps_detail = []
        for step in plan.subtasks:
            result = result_map.get(step.id)
            
            if result is None:
                status = "pending"
            elif result.success:
                status = "success"
            else:
                status = "failed"

            steps_detail.append({
                "step": step.id,
                "name": step.tool or "unknown",
                "description": step.description,
                "expectations": step.expectations,
                "status": status,
                "output": ExecutionReportGenerator._compress_output(
                    result.output if result else None
                ),
                "error": result.error if result and not result.success else None,
            })

        # 统计信息
        total_steps = len(plan.subtasks)
        executed_steps = len(results)
        successful_steps = sum(1 for r in results if r.success)
        failed_steps = executed_steps - successful_steps

        duration = None
        if start_time and end_time:
            duration = (end_time - start_time).total_seconds()

        return {
            "agent_name": agent_name,
            "query": query[:500] + "..." if len(query) > 500 else query,
            "intent": plan.intent,
            "generated_at": datetime.now().isoformat(),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "duration_seconds": duration,
            "statistics": {
                "total_steps": total_steps,
                "executed_steps": executed_steps,
                "successful_steps": successful_steps,
                "failed_steps": failed_steps,
                "success_rate": round(
                    successful_steps / executed_steps * 100, 1
                ) if executed_steps > 0 else 0,
            },
            "steps": steps_detail,
            "final_state": ExecutionReportGenerator._compress_state(state),
            "mermaid_diagram": ExecutionReportGenerator.generate_mermaid(plan, results),
            "errors": plan.errors,
            "warnings": plan.warnings,
        }

    @staticmethod
    def generate_mermaid(
        plan: ExecutionPlan,
        results: List[SubTaskResult],
    ) -> str:
        """生成 Mermaid 流程图"""
        if not plan.subtasks:
            return "graph TD\n    Start([开始]) --> End([结束])"
            
        result_map = {r.step_id: r for r in results}
        lines = ["graph TD"]
        lines.append("    Start([开始]) --> Step1")

        for i, step in enumerate(plan.subtasks):
            step_id = f"Step{step.id}"
            result = result_map.get(step.id)
            
            tool_name = step.tool or "unknown"
            if result is None:
                shape = f"[{tool_name}]"
            elif result.success:
                shape = f"[{tool_name}]"
            else:
                shape = f"[[{tool_name}]]"

            lines.append(f"    {step_id}{shape}")

            if i < len(plan.subtasks) - 1:
                next_id = f"Step{plan.subtasks[i + 1].id}"
                lines.append(f"    {step_id} --> {next_id}")
            else:
                lines.append(f"    {step_id} --> End([结束])")

        # 添加样式
        lines.append("")
        for step in plan.subtasks:
            result = result_map.get(step.id)
            step_id = f"Step{step.id}"
            if result is None:
                lines.append(f"    style {step_id} fill:#E0E0E0")
            elif result.success:
                lines.append(f"    style {step_id} fill:#90EE90")
            else:
                lines.append(f"    style {step_id} fill:#FFB6C1")

        return "\n".join(lines)

    @staticmethod
    def generate_markdown_report(report_data: Dict[str, Any]) -> str:
        """生成 Markdown 格式报告"""
        lines = [
            f"# 智能体执行报告",
            f"",
            f"**Agent**: {report_data['agent_name']}",
            f"**意图**: {report_data.get('intent', 'N/A')}",
            f"**执行时间**: {report_data['generated_at']}",
            f"**耗时**: {report_data.get('duration_seconds', 'N/A')} 秒",
            f"",
            f"**用户输入**:",
            f"> {report_data['query']}",
            f"",
            f"---",
            f"",
            f"## 执行统计",
            f"",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 总步骤数 | {report_data['statistics']['total_steps']} |",
            f"| 已执行 | {report_data['statistics']['executed_steps']} |",
            f"| 成功 | {report_data['statistics']['successful_steps']} |",
            f"| 失败 | {report_data['statistics']['failed_steps']} |",
            f"| 成功率 | {report_data['statistics']['success_rate']}% |",
            f"",
            f"## 执行流程",
            f"",
            f"```mermaid",
            report_data['mermaid_diagram'],
            f"```",
            f"",
            f"## 步骤详情",
            f"",
        ]

        for step in report_data['steps']:
            status_icon = {
                "success": "✅",
                "failed": "❌", 
                "pending": "⏳",
            }.get(step['status'], "❓")
            
            lines.append(f"### {status_icon} 步骤 {step['step']}: {step['name']}")
            lines.append(f"")
            lines.append(f"- **描述**: {step['description']}")
            if step.get('expectations'):
                lines.append(f"- **期望**: {step['expectations']}")
            lines.append(f"- **状态**: {step['status']}")
            if step.get('error'):
                lines.append(f"- **错误**: `{step['error']}`")
            lines.append(f"")

        if report_data.get('errors'):
            lines.append(f"## 错误信息")
            lines.append(f"")
            for err in report_data['errors']:
                lines.append(f"- {err}")
            lines.append(f"")

        return "\n".join(lines)

    @staticmethod
    def _compress_output(output: Any) -> Any:
        """压缩输出数据"""
        if output is None:
            return None
        if isinstance(output, dict):
            compressed = {}
            for k, v in output.items():
                if k == "documents" and isinstance(v, list):
                    compressed[k] = f"[{len(v)} documents]"
                elif isinstance(v, str) and len(v) > 200:
                    compressed[k] = v[:200] + "..."
                elif isinstance(v, list) and len(v) > 10:
                    compressed[k] = f"[{len(v)} items]"
                else:
                    compressed[k] = v
            return compressed
        return output

    @staticmethod
    def _compress_state(state: Dict[str, Any]) -> Dict[str, Any]:
        """压缩状态数据"""
        compressed = {}
        for k, v in state.items():
            if k in ["inputs", "control"]:
                compressed[k] = v
            elif isinstance(v, list) and len(v) > 5:
                compressed[k] = f"[{len(v)} items]"
            elif isinstance(v, dict) and len(str(v)) > 500:
                compressed[k] = f"{{...{len(v)} keys}}"
            elif isinstance(v, str) and len(v) > 200:
                compressed[k] = v[:200] + "..."
            else:
                compressed[k] = v
        return compressed
