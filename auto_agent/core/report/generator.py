"""
智能体执行报告生成器

用于生成可视化的执行过程报告，支持 Markdown 和结构化数据导出
整合追踪系统数据，提供细粒度的执行分析
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from auto_agent.models import ExecutionPlan, SubTaskResult


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
        trace_data: Optional[Dict[str, Any]] = None,
        checkpoints: Optional[List[Dict[str, Any]]] = None,
        working_memory: Optional[Dict[str, Any]] = None,
        consistency_violations: Optional[List[Dict[str, Any]]] = None,
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
            trace_data: 追踪数据（来自 Tracer）
            checkpoints: 一致性检查点列表
            working_memory: 工作记忆数据
            consistency_violations: 一致性违规列表

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

            steps_detail.append(
                {
                    "step": step.id,
                    "name": step.tool or "unknown",
                    "description": step.description,
                    "expectations": step.expectations,
                    "status": status,
                    "output": ExecutionReportGenerator._compress_output(
                        result.output if result else None
                    ),
                    "error": result.error if result and not result.success else None,
                }
            )

        # 统计信息
        total_steps = len(plan.subtasks)
        executed_steps = len(results)
        successful_steps = sum(1 for r in results if r.success)
        failed_steps = executed_steps - successful_steps

        duration = None
        if start_time and end_time:
            duration = (end_time - start_time).total_seconds()

        # 基础报告数据
        report = {
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
                "success_rate": round(successful_steps / executed_steps * 100, 1)
                if executed_steps > 0
                else 0,
            },
            "steps": steps_detail,
            "final_state": ExecutionReportGenerator._compress_state(state),
            "mermaid_diagram": ExecutionReportGenerator.generate_mermaid(plan, results),
            "errors": plan.errors,
            "warnings": plan.warnings,
        }
        
        # 整合追踪数据
        if trace_data:
            report["trace"] = ExecutionReportGenerator._extract_trace_summary(trace_data)
        
        # 整合检查点数据
        if checkpoints:
            report["checkpoints"] = checkpoints
        
        # 整合工作记忆数据
        if working_memory:
            report["working_memory"] = working_memory
        
        # 整合一致性违规数据
        if consistency_violations:
            report["consistency_violations"] = consistency_violations
        
        return report
    
    @staticmethod
    def _extract_trace_summary(trace_data: Dict[str, Any]) -> Dict[str, Any]:
        """从追踪数据中提取摘要信息"""
        summary = trace_data.get("summary", {})
        
        return {
            "trace_id": trace_data.get("trace_id"),
            "duration_ms": trace_data.get("duration_ms"),
            "llm_usage": {
                "total_calls": summary.get("llm_calls", {}).get("count", 0),
                "total_tokens": summary.get("llm_calls", {}).get("total_tokens", 0),
                "prompt_tokens": summary.get("llm_calls", {}).get("prompt_tokens", 0),
                "response_tokens": summary.get("llm_calls", {}).get("response_tokens", 0),
                "by_purpose": summary.get("llm_calls", {}).get("by_purpose", {}),
            },
            "tool_usage": {
                "total_calls": summary.get("tool_calls", {}).get("count", 0),
                "success": summary.get("tool_calls", {}).get("success", 0),
                "failed": summary.get("tool_calls", {}).get("failed", 0),
            },
            "flow_events": {
                "retries": summary.get("flow_events", {}).get("retries", 0),
                "jumps": summary.get("flow_events", {}).get("jumps", 0),
                "aborts": summary.get("flow_events", {}).get("aborts", 0),
                "replans": summary.get("flow_events", {}).get("replans", 0),
            },
            "memory_ops": summary.get("memory_ops", {}),
            "binding_ops": summary.get("binding_ops", {}),
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
            "# 智能体执行报告",
            "",
            f"**Agent**: {report_data['agent_name']}",
            f"**意图**: {report_data.get('intent', 'N/A')}",
            f"**执行时间**: {report_data['generated_at']}",
            f"**耗时**: {report_data.get('duration_seconds', 'N/A')} 秒",
        ]
        
        # 添加追踪 ID（如果有）
        trace = report_data.get("trace", {})
        if trace.get("trace_id"):
            lines.append(f"**追踪ID**: `{trace['trace_id']}`")
        
        lines.extend([
            "",
            "**用户输入**:",
            f"> {report_data['query']}",
            "",
            "---",
            "",
            "## 执行统计",
            "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| 总步骤数 | {report_data['statistics']['total_steps']} |",
            f"| 已执行 | {report_data['statistics']['executed_steps']} |",
            f"| 成功 | {report_data['statistics']['successful_steps']} |",
            f"| 失败 | {report_data['statistics']['failed_steps']} |",
            f"| 成功率 | {report_data['statistics']['success_rate']}% |",
            "",
        ])
        
        # 添加 LLM 使用统计（如果有追踪数据）
        if trace.get("llm_usage"):
            llm = trace["llm_usage"]
            lines.extend([
                "## LLM 调用统计",
                "",
                "| 指标 | 值 |",
                "|------|-----|",
                f"| 总调用次数 | {llm.get('total_calls', 0)} |",
                f"| 总 Token 数 | {llm.get('total_tokens', 0):,} |",
                f"| Prompt Tokens | {llm.get('prompt_tokens', 0):,} |",
                f"| Response Tokens | {llm.get('response_tokens', 0):,} |",
                "",
            ])
            
            # 按目的分类
            by_purpose = llm.get("by_purpose", {})
            if by_purpose:
                lines.extend([
                    "**按调用目的分类**:",
                    "",
                    "| 目的 | 调用次数 | Token 数 |",
                    "|------|----------|----------|",
                ])
                purpose_names = {
                    "planning": "任务规划",
                    "binding_plan": "绑定规划",
                    "param_build": "参数构造",
                    "validation": "期望验证",
                    "error_analysis": "错误分析",
                    "param_fix": "参数修正",
                    "memory_query": "记忆查询",
                    "memory_summary": "记忆总结",
                    "prompt_gen": "Prompt生成",
                    "replan": "重规划",
                    "incremental_replan": "增量重规划",
                    "consistency_check": "一致性检查",
                    "checkpoint_register": "检查点注册",
                    "working_memory": "工作记忆",
                    "other": "其他",
                }
                for purpose, data in by_purpose.items():
                    name = purpose_names.get(purpose, purpose)
                    lines.append(f"| {name} | {data.get('count', 0)} | {data.get('tokens', 0):,} |")
                lines.append("")
        
        # 添加参数绑定统计（如果有）
        binding_ops = trace.get("binding_ops", {})
        if binding_ops and binding_ops.get("total_bindings", 0) > 0:
            total = binding_ops.get("total_bindings", 0)
            resolved = binding_ops.get("resolved_bindings", 0)
            fallback = binding_ops.get("fallback_bindings", 0)
            success_rate = (resolved / total * 100) if total > 0 else 0
            
            lines.extend([
                "## 参数绑定统计",
                "",
                "| 指标 | 值 |",
                "|------|-----|",
                f"| 绑定规划次数 | {binding_ops.get('plan_creates', 0)} |",
                f"| 绑定解析次数 | {binding_ops.get('resolves', 0)} |",
                f"| LLM Fallback 次数 | {binding_ops.get('fallbacks', 0)} |",
                f"| 总绑定数 | {total} |",
                f"| 成功解析 | {resolved} |",
                f"| 需要 Fallback | {fallback} |",
                f"| 绑定成功率 | {success_rate:.1f}% |",
                "",
            ])
        
        # 添加流程事件统计（如果有）
        if trace.get("flow_events"):
            flow = trace["flow_events"]
            total_events = sum(flow.values())
            if total_events > 0:
                lines.extend([
                    "## 流程控制事件",
                    "",
                    "| 事件类型 | 次数 |",
                    "|----------|------|",
                    f"| 重试 | {flow.get('retries', 0)} |",
                    f"| 跳转 | {flow.get('jumps', 0)} |",
                    f"| 中止 | {flow.get('aborts', 0)} |",
                    f"| 重规划 | {flow.get('replans', 0)} |",
                    "",
                ])
        
        # 添加一致性检查点（如果有）
        checkpoints = report_data.get("checkpoints", [])
        if checkpoints:
            lines.extend([
                "## 一致性检查点",
                "",
                "执行过程中注册的关键检查点，用于后续一致性验证和问题修正。",
                "",
            ])
            for cp in checkpoints:
                cp_id = cp.get("checkpoint_id", "unknown")
                cp_type = cp.get("checkpoint_type", "unknown")
                step_id = cp.get("step_id", "?")
                
                lines.append(f"### 📍 {cp_id} [{cp_type}]")
                lines.append("")
                lines.append(f"- **步骤**: Step {step_id}")
                
                # 显示关键元素
                key_elements = cp.get("key_elements", {})
                if key_elements:
                    lines.append("- **关键元素**:")
                    for elem_type, elements in key_elements.items():
                        if isinstance(elements, list):
                            lines.append(f"  - {elem_type}: {', '.join(str(e) for e in elements[:10])}")
                            if len(elements) > 10:
                                lines.append(f"    ... 还有 {len(elements) - 10} 个")
                        else:
                            lines.append(f"  - {elem_type}: {elements}")
                
                # 显示约束
                constraints = cp.get("constraints", [])
                if constraints:
                    lines.append("- **约束条件**:")
                    for c in constraints[:5]:
                        lines.append(f"  - {c}")
                    if len(constraints) > 5:
                        lines.append(f"  - ... 还有 {len(constraints) - 5} 条")
                
                lines.append("")
        
        # 添加一致性违规（如果有）
        violations = report_data.get("consistency_violations", [])
        if violations:
            lines.extend([
                "## ⚠️ 一致性违规",
                "",
                "执行过程中检测到的一致性问题，可用于后续修正。",
                "",
                "| 严重程度 | 检查点 | 问题描述 | 建议 |",
                "|----------|--------|----------|------|",
            ])
            for v in violations:
                severity = v.get("severity", "warning")
                severity_icon = "🔴" if severity == "critical" else "🟡"
                cp_id = v.get("checkpoint_id", "N/A")
                desc = v.get("description", "未知问题")[:50]
                suggestion = v.get("suggestion", "")[:30]
                lines.append(f"| {severity_icon} {severity} | {cp_id} | {desc} | {suggestion} |")
            lines.append("")
        
        # 添加工作记忆（如果有）
        working_memory = report_data.get("working_memory", {})
        if working_memory:
            lines.extend([
                "## 🧠 工作记忆",
                "",
                "执行过程中提取的设计决策、约束和待办事项。",
                "",
            ])
            
            # 设计决策
            decisions = working_memory.get("decisions", [])
            if decisions:
                lines.append("### 设计决策")
                lines.append("")
                for d in decisions[:10]:
                    decision = d.get("decision", "")
                    rationale = d.get("rationale", "")
                    step = d.get("step_id", "?")
                    lines.append(f"- **[Step {step}]** {decision}")
                    if rationale:
                        lines.append(f"  - 理由: {rationale[:100]}")
                if len(decisions) > 10:
                    lines.append(f"- ... 还有 {len(decisions) - 10} 条决策")
                lines.append("")
            
            # 约束条件
            constraints = working_memory.get("constraints", [])
            if constraints:
                lines.append("### 约束条件")
                lines.append("")
                for c in constraints[:10]:
                    constraint = c.get("constraint", "")
                    source = c.get("source", "")
                    lines.append(f"- {constraint}")
                    if source:
                        lines.append(f"  - 来源: {source}")
                if len(constraints) > 10:
                    lines.append(f"- ... 还有 {len(constraints) - 10} 条约束")
                lines.append("")
            
            # 接口定义
            interfaces = working_memory.get("interfaces", [])
            if interfaces:
                lines.append("### 接口定义")
                lines.append("")
                for iface in interfaces[:10]:
                    name = iface.get("name", "unknown")
                    iface_type = iface.get("type", "")
                    lines.append(f"- **{name}** ({iface_type})")
                    signature = iface.get("signature", "")
                    if signature:
                        lines.append(f"  ```")
                        lines.append(f"  {signature[:200]}")
                        lines.append(f"  ```")
                if len(interfaces) > 10:
                    lines.append(f"- ... 还有 {len(interfaces) - 10} 个接口")
                lines.append("")
            
            # 待办事项
            todos = working_memory.get("todos", [])
            if todos:
                lines.append("### 待办事项")
                lines.append("")
                for t in todos[:10]:
                    todo = t.get("todo", "")
                    priority = t.get("priority", "medium")
                    status = t.get("status", "pending")
                    status_icon = "✅" if status == "done" else "⏳"
                    lines.append(f"- {status_icon} [{priority}] {todo}")
                if len(todos) > 10:
                    lines.append(f"- ... 还有 {len(todos) - 10} 条待办")
                lines.append("")
        
        lines.extend([
            "## 执行流程",
            "",
            "```mermaid",
            report_data["mermaid_diagram"],
            "```",
            "",
            "## 步骤详情",
            "",
        ])

        for step in report_data["steps"]:
            status_icon = {
                "success": "✅",
                "failed": "❌",
                "pending": "⏳",
            }.get(step["status"], "❓")

            lines.append(f"### {status_icon} 步骤 {step['step']}: {step['name']}")
            lines.append("")
            lines.append(f"- **描述**: {step['description']}")
            if step.get("expectations"):
                lines.append(f"- **期望**: {step['expectations']}")
            lines.append(f"- **状态**: {step['status']}")
            if step.get("error"):
                lines.append(f"- **错误**: `{step['error']}`")
            lines.append("")

        if report_data.get("errors"):
            lines.append("## 错误信息")
            lines.append("")
            for err in report_data["errors"]:
                lines.append(f"- {err}")
            lines.append("")

        return "\n".join(lines)
    
    @staticmethod
    def generate_detailed_markdown_report(
        report_data: Dict[str, Any],
        trace_data: Optional[Dict[str, Any]] = None,
        show_full_content: bool = True,
    ) -> str:
        """
        生成详细的 Markdown 报告（包含完整追踪信息）
        
        Args:
            report_data: 基础报告数据
            trace_data: 完整追踪数据（包含所有 spans 和 events）
                - 建议使用 trace_full（不截断版本）以获取完整内容
            show_full_content: 是否显示完整的 prompt/response 内容
                - True: 显示完整内容（适合详细分析）
                - False: 显示预览（适合快速浏览）
            
        Returns:
            详细的 Markdown 报告
        """
        # 先生成基础报告
        lines = [ExecutionReportGenerator.generate_markdown_report(report_data)]
        
        if not trace_data:
            return lines[0]
        
        # 添加详细追踪信息
        lines.extend([
            "",
            "---",
            "",
            "## 详细追踪日志",
            "",
        ])
        
        # 遍历所有 spans
        root_span = trace_data.get("spans", {})
        if root_span:
            lines.extend(ExecutionReportGenerator._format_span_tree(root_span, 0, show_full_content))
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_span_tree(span: Dict[str, Any], depth: int, show_full: bool = True) -> List[str]:
        """
        递归格式化 span 树
        
        Args:
            span: span 数据
            depth: 缩进深度
            show_full: 是否显示完整内容
        """
        lines = []
        indent = "  " * depth
        
        name = span.get("name", "unknown")
        span_type = span.get("span_type", "")
        duration = span.get("duration_ms", 0)
        
        if name != "root":
            type_badge = f"[{span_type}]" if span_type else ""
            lines.append(f"{indent}### {type_badge} {name} ({duration:.1f}ms)")
            lines.append("")
        
        # 格式化事件
        events = span.get("events", [])
        for event in events:
            event_lines = ExecutionReportGenerator._format_event(event, depth + 1, show_full)
            lines.extend(event_lines)
        
        # 递归处理子 spans
        children = span.get("children", [])
        for child in children:
            lines.extend(ExecutionReportGenerator._format_span_tree(child, depth + 1, show_full))
        
        return lines
    
    @staticmethod
    def _format_event(event: Dict[str, Any], depth: int, show_full: bool = True) -> List[str]:
        """
        格式化单个事件
        
        Args:
            event: 事件数据
            depth: 缩进深度
            show_full: 是否显示完整内容（默认 True）
        """
        lines = []
        indent = "  " * depth
        event_type = event.get("event_type", "unknown")
        
        if event_type == "llm_call":
            purpose = event.get("purpose", "unknown")
            model = event.get("model", "unknown")
            tokens = event.get("total_tokens", 0)
            duration = event.get("duration_ms", 0)
            
            lines.append(f"{indent}- 🤖 **LLM调用** [{purpose}]")
            lines.append(f"{indent}  - 模型: {model}")
            lines.append(f"{indent}  - Tokens: {tokens:,} ({duration:.1f}ms)")
            
            # 显示 prompt（完整或预览）
            prompt = event.get("prompt", event.get("prompt_preview", ""))
            if prompt:
                if show_full:
                    # 使用代码块显示完整 prompt
                    lines.append(f"{indent}  - **Prompt**:")
                    lines.append(f"{indent}    ```")
                    for line in prompt.split("\n"):
                        lines.append(f"{indent}    {line}")
                    lines.append(f"{indent}    ```")
                else:
                    preview = prompt[:200] + "..." if len(prompt) > 200 else prompt
                    lines.append(f"{indent}  - Prompt: `{preview}`")
            
            # 显示 response（完整或预览）
            response = event.get("response", event.get("response_preview", ""))
            if response and show_full:
                lines.append(f"{indent}  - **Response**:")
                lines.append(f"{indent}    ```")
                for line in response.split("\n"):
                    lines.append(f"{indent}    {line}")
                lines.append(f"{indent}    ```")
            
            lines.append("")
            
        elif event_type == "tool_call":
            tool_name = event.get("tool_name", "unknown")
            success = event.get("success", False)
            duration = event.get("duration_ms", 0)
            status = "✅" if success else "❌"
            
            lines.append(f"{indent}- 🔧 **工具调用** {status} `{tool_name}` ({duration:.1f}ms)")
            
            if not success and event.get("error"):
                lines.append(f"{indent}  - 错误: {event['error']}")
            
            lines.append("")
            
        elif event_type == "flow":
            action = event.get("action", "unknown")
            reason = event.get("reason", "")
            from_step = event.get("from_step", "")
            to_step = event.get("to_step", "")
            
            action_icons = {
                "retry": "🔄",
                "jump": "⏭️",
                "abort": "🛑",
                "replan": "📋",
                "fallback": "↩️",
            }
            icon = action_icons.get(action, "❓")
            
            lines.append(f"{indent}- {icon} **流程控制** [{action}]")
            lines.append(f"{indent}  - 原因: {reason}")
            if from_step:
                lines.append(f"{indent}  - 从步骤: {from_step}")
            if to_step:
                lines.append(f"{indent}  - 到步骤: {to_step}")
            lines.append("")
            
        elif event_type == "memory":
            action = event.get("action", "unknown")
            layer = event.get("memory_layer", "")
            result_count = event.get("result_count", 0)
            
            lines.append(f"{indent}- 🧠 **记忆操作** [{action}] {layer}")
            if result_count:
                lines.append(f"{indent}  - 结果数: {result_count}")
            lines.append("")
        
        return lines

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
