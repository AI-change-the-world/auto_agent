"""
后处理策略模块

负责步骤执行后的统一后处理。
"""

import json
import re
from typing import Any, Dict, Optional, TYPE_CHECKING

from auto_agent.models import (
    ExecutionStrategy,
    PlanStep,
    SubTaskResult,
    ToolPostPolicy,
)

if TYPE_CHECKING:
    from auto_agent.llm.client import LLMClient
    from auto_agent.core.context import ExecutionContext
    from auto_agent.tools.registry import ToolRegistry


class PostPolicyManager:
    """
    后处理策略管理器
    
    负责：
    1. 应用统一的后处理策略
    2. 提取工作记忆
    3. 获取验证失败后的动作
    """

    def __init__(
        self,
        llm_client: Optional["LLMClient"] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        context: Optional["ExecutionContext"] = None,
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.context = context

    async def apply_post_policy(
        self,
        step: PlanStep,
        result: SubTaskResult,
        state: Dict[str, Any],
        execution_strategy: Optional[ExecutionStrategy],
    ) -> Dict[str, Any]:
        """
        应用统一的后处理策略

        三阶段处理流程：
        1. ValidationConfig: 验证结果
        2. PostSuccessConfig: 通过后检查
        3. ResultHandlingConfig: 结果处理

        Args:
            step: 执行的步骤
            result: 执行结果
            state: 当前状态
            execution_strategy: 全局执行策略

        Returns:
            处理结果，包含：
            - should_extract_memory: 是否需要提取工作记忆
            - should_register_checkpoint: 是否需要注册检查点
            - checkpoint_type: 检查点类型
            - compressed_result: 压缩后的结果
        """
        post_result = {
            "should_extract_memory": False,
            "should_register_checkpoint": False,
            "checkpoint_type": None,
            "compressed_result": None,
        }

        if not result.success:
            return post_result

        # 获取工具的后处理策略
        tool = self.tool_registry.get_tool(step.tool) if self.tool_registry and step.tool else None
        post_policy: Optional[ToolPostPolicy] = None

        if tool and hasattr(tool, "definition"):
            post_policy = tool.definition.get_effective_post_policy()

        # 如果没有后处理策略，使用全局策略决定
        if not post_policy or (
            not post_policy.validation
            and not post_policy.post_success
            and not post_policy.result_handling
        ):
            if execution_strategy and execution_strategy.require_phase_review:
                post_result["should_extract_memory"] = True
                post_result["should_register_checkpoint"] = True
            return post_result

        # === 第二阶段：PostSuccessConfig ===
        if post_policy.post_success:
            ps_config = post_policy.post_success

            if ps_config.high_impact:
                post_result["should_extract_memory"] = True
                post_result["should_register_checkpoint"] = True

            if ps_config.requires_consistency_check:
                post_result["should_register_checkpoint"] = True

            if ps_config.extract_working_memory:
                post_result["should_extract_memory"] = True

        # === 第三阶段：ResultHandlingConfig ===
        if post_policy.result_handling:
            rh_config = post_policy.result_handling

            if rh_config.register_as_checkpoint:
                post_result["should_register_checkpoint"] = True
                post_result["checkpoint_type"] = rh_config.checkpoint_type

            if rh_config.compress_function and result.output:
                try:
                    compressed = rh_config.compress_function(result.output, state)
                    post_result["compressed_result"] = compressed
                except Exception:
                    pass

            if rh_config.state_mapping and result.output:
                for result_key, state_key in rh_config.state_mapping.items():
                    if result_key in result.output:
                        state[state_key] = result.output[result_key]

        # 全局策略覆盖
        if execution_strategy and execution_strategy.require_phase_review:
            post_result["should_extract_memory"] = True
            post_result["should_register_checkpoint"] = True

        return post_result

    def get_validation_action(
        self,
        tool: Any,
        validation_passed: bool,
    ) -> str:
        """
        获取验证失败后的动作

        Args:
            tool: 工具实例
            validation_passed: 验证是否通过

        Returns:
            动作: "retry" / "replan" / "abort" / "continue"
        """
        if validation_passed:
            return "continue"

        if not tool or not hasattr(tool, "definition"):
            return "retry"

        post_policy = tool.definition.get_effective_post_policy()
        if post_policy and post_policy.validation:
            return post_policy.validation.on_fail

        return "retry"

    async def extract_working_memory(
        self,
        step: PlanStep,
        result: SubTaskResult,
        state: Dict[str, Any],
    ) -> None:
        """
        从步骤执行结果中提取工作记忆

        让 LLM 分析步骤输出，提取：
        - 设计决策
        - 约束条件
        - 待办事项
        - 接口定义

        Args:
            step: 执行的步骤
            result: 执行结果
            state: 当前状态
        """
        if not self.llm_client or not self.context:
            return

        prompt = f"""分析这一步的执行结果，提取需要后续步骤遵守的信息。

【步骤信息】
工具: {step.tool}
描述: {step.description}

【执行结果】
{json.dumps(result.output, ensure_ascii=False, default=str)[:2000] if result.output else "无输出"}

【任务】
从执行结果中提取以下信息（如果有的话）：

1. 设计决策：这一步做出了什么重要决定？
2. 约束条件：后续步骤必须遵守什么规则？
3. 待办事项：这一步产生了什么需要后续处理的任务？
4. 接口定义：这一步定义了什么接口/契约？

请返回 JSON（只包含有内容的字段）：
```json
{{
    "decisions": [
        {{"decision": "决策内容", "reason": "决策理由"}}
    ],
    "constraints": [
        {{"constraint": "约束内容", "priority": "critical/high/normal/low"}}
    ],
    "todos": [
        {{"todo": "待办内容", "priority": "high/normal/low"}}
    ],
    "interfaces": [
        {{"name": "接口名", "type": "function/api/schema", "definition": {{...}}}}
    ]
}}
```

如果没有需要提取的信息，返回空对象 {{}}"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                trace_purpose="extract_working_memory",
            )

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    response = json_match.group()

            data = json.loads(response)

            wm = self.context.working_memory

            for d in data.get("decisions", []):
                wm.add_decision(
                    decision=d.get("decision", ""),
                    reason=d.get("reason", ""),
                    step_id=step.id,
                )

            for c in data.get("constraints", []):
                wm.add_constraint(
                    constraint=c.get("constraint", ""),
                    source=step.id,
                    priority=c.get("priority", "normal"),
                )

            for t in data.get("todos", []):
                wm.add_todo(
                    todo=t.get("todo", ""),
                    created_by=step.id,
                    priority=t.get("priority", "normal"),
                )

            for iface in data.get("interfaces", []):
                wm.add_interface(
                    name=iface.get("name", ""),
                    definition=iface.get("definition", {}),
                    defined_by=step.id,
                    interface_type=iface.get("type", "function"),
                )

        except Exception:
            pass
