"""
Agent Orchestrator（智能体编排器）

协调：IntentRecognizer、TaskPlanner、ExecutionEngine、MemoryManager
"""

from typing import Any, Dict, List, Optional, Tuple

from auto_agent.core.executor import ExecutionEngine
from auto_agent.core.planner import TaskPlanner
from auto_agent.llm.client import LLMClient
from auto_agent.models import ExecutionPlan, SubTaskResult
from auto_agent.retry.models import RetryConfig
from auto_agent.tools.registry import ToolRegistry


class AgentOrchestrator:
    """
    智能体编排器

    负责协调：
    - 意图识别
    - 任务规划
    - 执行引擎
    - 记忆管理
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        retry_config: RetryConfig,
        agent_goals: Optional[List[str]] = None,
        agent_constraints: Optional[List[str]] = None,
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry

        # 初始化规划器
        self.planner = TaskPlanner(
            llm_client=llm_client,
            tool_registry=tool_registry,
            agent_goals=agent_goals,
            agent_constraints=agent_constraints,
        )

        # 初始化执行引擎
        self.executor = ExecutionEngine(
            tool_registry=tool_registry,
            retry_config=retry_config,
            llm_client=llm_client,
        )

    async def execute(
        self,
        query: str,
        user_context: str,
        conversation_context: str,
        conversation_id: str,
        initial_state: Optional[Dict[str, Any]] = None,
        initial_plan: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[ExecutionPlan, List[SubTaskResult], Dict[str, Any]]:
        """
        执行完整流程：规划 -> 执行

        Args:
            query: 用户查询
            user_context: 用户长期记忆上下文
            conversation_context: 对话短期记忆上下文
            conversation_id: 对话ID
            initial_state: 初始状态字典
            initial_plan: 初始计划（含固定步骤）

        Returns:
            (ExecutionPlan, List[SubTaskResult], 最终状态)
        """
        state = initial_state or {}

        # Step 1: 意图识别（简化版，嵌入在规划中）
        # intent = await self._recognize_intent(query)

        # Step 2: 任务规划
        plan = await self.planner.plan(
            query=query,
            user_context=user_context,
            conversation_context=conversation_context,
            initial_plan=initial_plan,
        )

        # 检查规划是否成功
        if plan.errors:
            return plan, [], state

        # Step 3: 根据 state_schema 初始化状态字段
        if plan.state_schema:
            self._initialize_state_from_schema(state, plan.state_schema)

        # Step 4: 执行计划
        results, final_state = await self.executor.execute_plan(
            plan=plan,
            state=state,
            conversation_id=conversation_id,
        )

        return plan, results, final_state

    def _initialize_state_from_schema(
        self, state: Dict[str, Any], state_schema: Dict[str, Any]
    ):
        """根据 state schema 初始化状态字段"""
        for field_name, field_def in state_schema.items():
            if field_name in ["inputs", "control"]:
                continue

            field_type = field_def.get("type", "dict")
            field_default = field_def.get("default")

            if field_default is not None:
                state[field_name] = field_default
            elif field_type == "list":
                state[field_name] = []
            elif field_type == "dict":
                state[field_name] = {}
            elif field_type == "string":
                state[field_name] = ""
            elif field_type == "number":
                state[field_name] = 0
            else:
                state[field_name] = None

    async def _recognize_intent(self, query: str) -> str:
        """
        意图识别（占位实现）

        TODO: 可用 LLM 进行意图分类
        """
        return "general"
