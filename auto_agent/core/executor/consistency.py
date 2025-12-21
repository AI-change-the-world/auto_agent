"""
一致性检查模块

负责检查点注册和一致性验证。
"""

import json
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from auto_agent.models import PlanStep, SubTaskResult

if TYPE_CHECKING:
    from auto_agent.core.context import ConsistencyViolation, ExecutionContext
    from auto_agent.llm.client import LLMClient


class ConsistencyManager:
    """
    一致性管理器

    负责：
    1. 注册一致性检查点
    2. 检查当前步骤与历史检查点的一致性
    """

    def __init__(
        self,
        llm_client: Optional["LLMClient"] = None,
        context: Optional["ExecutionContext"] = None,
    ):
        self.llm_client = llm_client
        self.context = context

    async def register_consistency_checkpoint(
        self,
        step: PlanStep,
        result: SubTaskResult,
        state: Dict[str, Any],
    ) -> None:
        """
        注册一致性检查点

        在高影响力工具执行后，提取关键元素并注册为检查点，
        供后续步骤进行一致性检查。

        Args:
            step: 执行的步骤
            result: 执行结果
            state: 当前状态
        """
        if not self.llm_client or not self.context:
            return

        prompt = f"""分析这一步的执行结果，提取需要后续步骤保持一致的关键元素。

【步骤信息】
工具: {step.tool}
描述: {step.description}

【执行结果】
{json.dumps(result.output, ensure_ascii=False, default=str)[:2000] if result.output else "无输出"}

【任务】
从执行结果中提取以下信息：

1. 产物类型：这一步产出了什么类型的内容？
   - code: 代码（函数、类、模块）
   - interface: 接口定义（API、函数签名）
   - schema: 数据结构定义
   - config: 配置文件
   - document: 文档（大纲、报告）

2. 关键元素：后续步骤需要保持一致的关键信息
   - 如果是代码：函数名、参数列表、返回类型
   - 如果是接口：端点、请求/响应格式
   - 如果是文档：章节结构、关键术语

3. 后续约束：后续步骤必须遵守的规则

请返回 JSON：
```json
{{
    "artifact_type": "code/interface/schema/config/document",
    "description": "简短描述这个检查点",
    "key_elements": {{
        "names": ["函数名/接口名/..."],
        "signatures": {{"name": "签名"}},
        "structure": {{...}}
    }},
    "constraints": [
        "后续步骤必须遵守的约束1",
        "后续步骤必须遵守的约束2"
    ]
}}
```

如果这一步没有产出需要保持一致的内容，返回 {{"skip": true}}"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                trace_purpose="register_checkpoint",
            )

            # 提取 JSON
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    response = json_match.group()

            data = json.loads(response)

            if data.get("skip"):
                return

            # 注册检查点
            self.context.consistency_checker.register_checkpoint(
                step_id=step.id,
                artifact_type=data.get("artifact_type", "unknown"),
                key_elements=data.get("key_elements", {}),
                constraints_for_future=data.get("constraints", []),
                description=data.get("description", step.description),
            )

        except Exception:
            pass

    async def check_consistency(
        self,
        step: PlanStep,
        arguments: Dict[str, Any],
        state: Dict[str, Any],
    ) -> List["ConsistencyViolation"]:
        """
        检查当前步骤与历史检查点的一致性

        在执行步骤前调用，检查参数和意图是否与之前的检查点一致。

        Args:
            step: 即将执行的步骤
            arguments: 构造的参数
            state: 当前状态

        Returns:
            违规列表
        """
        from auto_agent.core.context import ConsistencyViolation

        if not self.llm_client or not self.context:
            return []

        checker = self.context.consistency_checker
        checkpoints = checker.get_relevant_checkpoints()

        if not checkpoints:
            return []

        # 构建检查 prompt
        checkpoints_text = []
        for cp in checkpoints:
            cp_text = f"""
[{cp.step_id}] 类型: {cp.artifact_type}
描述: {cp.description}
关键元素: {json.dumps(cp.key_elements, ensure_ascii=False)[:500]}
约束: {", ".join(cp.constraints_for_future[:3])}"""
            checkpoints_text.append(cp_text)

        prompt = f"""检查当前步骤是否与之前的检查点保持一致。

【历史检查点】
{"".join(checkpoints_text)}

【当前步骤】
工具: {step.tool}
描述: {step.description}
参数: {json.dumps(arguments, ensure_ascii=False, default=str)[:1000]}

【任务】
检查当前步骤是否违反了历史检查点的约束或与关键元素不一致。

可能的违规类型：
- interface_mismatch: 接口不匹配
- naming_conflict: 命名冲突
- constraint_violation: 违反约束
- structure_inconsistency: 结构不一致

请返回 JSON：
```json
{{
    "violations": [
        {{
            "checkpoint_id": "违反的检查点步骤ID",
            "violation_type": "interface_mismatch/naming_conflict/constraint_violation/structure_inconsistency",
            "severity": "critical/warning/info",
            "description": "违规描述",
            "suggestion": "修正建议"
        }}
    ]
}}
```

如果没有违规，返回 {{"violations": []}}"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                trace_purpose="check_consistency",
            )

            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)
            else:
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    response = json_match.group()

            data = json.loads(response)

            violations = []
            for v in data.get("violations", []):
                violation = checker.add_violation(
                    checkpoint_id=v.get("checkpoint_id", "unknown"),
                    current_step_id=step.id,
                    violation_type=v.get("violation_type", "unknown"),
                    severity=v.get("severity", "warning"),
                    description=v.get("description", ""),
                    suggestion=v.get("suggestion", ""),
                )
                violations.append(violation)

            return violations

        except Exception:
            return []
