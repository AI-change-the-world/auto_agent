"""
Agent Markdown 解析器

使用 LLM 解析 Markdown 格式的 Agent 定义，转换为结构化配置
"""

import json
import re
from typing import Any, Dict, List, Optional

from auto_agent.llm.client import LLMClient
from auto_agent.models import PlanStep


class AgentDefinition:
    """Agent 定义结构"""

    def __init__(
        self,
        name: str,
        description: str,
        goals: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        initial_plan: Optional[List[PlanStep]] = None,
        state_schema: Optional[Dict[str, Any]] = None,
        rollback_plan: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.description = description
        self.goals = goals or []
        self.constraints = constraints or []
        self.initial_plan = initial_plan or []
        self.state_schema = state_schema or {}
        self.rollback_plan = rollback_plan or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "goals": self.goals,
            "constraints": self.constraints,
            "initial_plan": [
                {
                    "id": s.id,
                    "tool": s.tool,
                    "description": s.description,
                    "parameters": s.parameters,
                    "expectations": s.expectations,
                    "is_pinned": s.is_pinned,
                }
                for s in self.initial_plan
            ],
            "state_schema": self.state_schema,
            "rollback_plan": self.rollback_plan,
        }


class AgentMarkdownParser:
    """
    Agent Markdown 解析器

    支持两种解析模式:
    1. LLM 解析: 使用大模型理解自然语言描述
    2. 规则解析: 基于简单规则提取结构化信息
    """

    PARSE_PROMPT = """你是一个专业的 Agent 规划助手。

【任务】
用户会用 Markdown 描述他想要的 Agent 功能。你需要将其转换为结构化的 Agent 定义。

【Markdown 格式说明】
用户的 Markdown 通常包含:
1. **标题**: Agent 名称或角色描述
2. **描述**: Agent 的功能描述
3. **目标/需要**: Agent 要达成的目标列表
4. **约束**: 执行时的约束条件
5. **步骤**: 执行步骤描述，可能包含工具名称如 [tool_name]

【核心原则】
1. 提取目标和约束是最重要的
2. 识别步骤中的工具调用 (用 [] 包裹的通常是工具名)
3. 理解步骤之间的依赖关系

【可用工具列表】
{tools_catalog}

【返回格式】
返回 JSON:
{{
    "name": "Agent 名称",
    "description": "Agent 描述",
    "goals": ["目标1", "目标2"],
    "constraints": ["约束1", "约束2"],
    "initial_plan": [
        {{
            "step": 1,
            "name": "工具名称",
            "description": "步骤描述",
            "expectations": "期望结果",
            "is_pinned": false
        }}
    ],
    "state_schema": {{
        "field_name": {{"type": "string", "description": "字段描述"}}
    }},
    "errors": [],
    "warnings": []
}}

【用户输入】
{content}
"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client

    async def parse(
        self,
        content: str,
        tools_catalog: str = "",
    ) -> Dict[str, Any]:
        """
        解析 Markdown 格式的 Agent 定义

        Args:
            content: Markdown 内容
            tools_catalog: 可用工具目录

        Returns:
            解析结果，包含 agent 定义和错误/警告信息
        """
        if self.llm_client:
            return await self._parse_with_llm(content, tools_catalog)
        else:
            return self._parse_with_rules(content)

    async def _parse_with_llm(
        self,
        content: str,
        tools_catalog: str,
    ) -> Dict[str, Any]:
        """使用 LLM 解析"""
        prompt = self.PARSE_PROMPT.format(
            content=content,
            tools_catalog=tools_catalog or "无可用工具信息",
        )

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的 Agent 规划助手，请返回有效的 JSON 格式。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.llm_client.chat(messages, temperature=0.3)

            # 提取 JSON
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                response = json_match.group(1)

            result = json.loads(response)

            # 转换为 AgentDefinition
            agent = AgentDefinition(
                name=result.get("name", "Unnamed Agent"),
                description=result.get("description", ""),
                goals=result.get("goals", []),
                constraints=result.get("constraints", []),
                initial_plan=[
                    PlanStep(
                        id=str(s.get("step", i + 1)),
                        tool=s.get("name"),
                        description=s.get("description", ""),
                        expectations=s.get("expectations"),
                        is_pinned=s.get("is_pinned", False),
                    )
                    for i, s in enumerate(result.get("initial_plan", []))
                ],
                state_schema=result.get("state_schema", {}),
            )

            return {
                "success": True,
                "agent": agent,
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
            }

        except Exception as e:
            return {
                "success": False,
                "agent": None,
                "errors": [f"LLM 解析失败: {str(e)}"],
                "warnings": [],
            }

    def _parse_with_rules(self, content: str) -> Dict[str, Any]:
        """使用规则解析 (无 LLM 时的降级方案)"""
        lines = content.strip().split("\n")

        name = "Unnamed Agent"
        description = ""
        goals = []
        constraints = []
        steps = []

        current_section = None
        step_counter = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 解析标题
            if line.startswith("# "):
                name = line[2:].strip()
            elif line.startswith("## "):
                section = line[3:].strip().lower()
                if "目标" in section or "需要" in section or "goal" in section:
                    current_section = "goals"
                elif "约束" in section or "constraint" in section:
                    current_section = "constraints"
                elif "步骤" in section or "step" in section:
                    current_section = "steps"
                else:
                    current_section = "description"
            elif line.startswith("- ") or line.startswith("* "):
                item = line[2:].strip()
                if current_section == "goals":
                    goals.append(item)
                elif current_section == "constraints":
                    constraints.append(item)
            elif re.match(r"^\d+\.", line):
                # 解析步骤
                step_text = re.sub(r"^\d+\.\s*", "", line)
                step_counter += 1

                # 提取工具名 [tool_name]
                tool_match = re.search(r"\[(\w+)\]", step_text)
                tool_name = tool_match.group(1) if tool_match else None

                steps.append(
                    PlanStep(
                        id=str(step_counter),
                        tool=tool_name,
                        description=step_text,
                    )
                )
            elif current_section == "description" or current_section is None:
                if description:
                    description += " "
                description += line

        # 如果没有明确的目标，从描述中提取
        if not goals and description:
            goals = [description]

        agent = AgentDefinition(
            name=name,
            description=description,
            goals=goals,
            constraints=constraints,
            initial_plan=steps,
        )

        return {
            "success": True,
            "agent": agent,
            "errors": [],
            "warnings": ["使用规则解析，可能不够准确"] if not self.llm_client else [],
        }

    def to_agent_config(self, agent: AgentDefinition) -> Dict[str, Any]:
        """将 AgentDefinition 转换为 AutoAgent 配置"""
        return {
            "agent_goals": agent.goals,
            "agent_constraints": agent.constraints,
            "initial_plan": [
                {
                    "step": int(s.id),
                    "name": s.tool,
                    "description": s.description,
                    "expectations": s.expectations,
                    "is_pinned": s.is_pinned,
                }
                for s in agent.initial_plan
            ],
        }
