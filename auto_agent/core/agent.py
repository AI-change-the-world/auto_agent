"""
AutoAgent 主类

核心执行流程：
1. 加载用户长期记忆
2. 加载或创建对话短期记忆
3. 动态规划（LLM）
4. 逐步执行（带重试）
5. 期望验证
6. 智能回退
7. 结果聚合
8. 更新记忆

架构说明：
- AutoAgent 是面向用户的高级 API
- 内部使用 TaskPlanner 进行规划
- 内部使用 ExecutionEngine 进行执行
- Memory 系统由 ExecutionEngine 内部管理
"""

import time
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from auto_agent.core.executor import ExecutionEngine
from auto_agent.core.planner import TaskPlanner
from auto_agent.llm.client import LLMClient
from auto_agent.models import AgentResponse, ExecutionPlan, Message, PlanStep
from auto_agent.retry.models import RetryConfig
from auto_agent.tools.registry import ToolRegistry


class AutoAgent:
    """
    Auto-Agent 主类

    核心改进：
    1. 执行时由 LLM 动态规划步骤
    2. 使用统一 state dict 管理数据流
    3. 自然语言描述期望，而非符号化 checkpoint
    4. 明确回退策略表
    5. Memory 系统由 ExecutionEngine 内部管理
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        retry_config: Optional[RetryConfig] = None,
        agent_name: str = "",
        agent_description: str = "",
        agent_goals: Optional[List[str]] = None,
        agent_constraints: Optional[List[str]] = None,
        memory_storage_path: Optional[str] = None,
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.agent_goals = agent_goals or []
        self.agent_constraints = agent_constraints or []

        # 初始化规划器
        self.planner = TaskPlanner(
            llm_client=llm_client,
            tool_registry=tool_registry,
            agent_goals=agent_goals,
            agent_constraints=agent_constraints,
        )

        # 初始化执行引擎（Memory 系统由 ExecutionEngine 内部管理）
        self.executor = ExecutionEngine(
            tool_registry=tool_registry,
            retry_config=retry_config or RetryConfig(),
            llm_client=llm_client,
            memory_storage_path=memory_storage_path,
        )

    async def run(
        self,
        query: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        template_id: Optional[int] = None,
        initial_plan: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[Callable] = None,
    ) -> AgentResponse:
        """
        执行智能体任务（非流式）

        Args:
            query: 用户查询
            user_id: 用户ID
            conversation_id: 对话ID（可选）
            template_id: 模板ID（可选）
            initial_plan: 初始计划（含固定步骤）
            tool_executor: 自定义工具执行器

        Returns:
            AgentResponse
        """
        # Step 1: 规划
        plan = await self.planner.plan(
            query=query,
            user_context="",
            conversation_context="",
            initial_plan=initial_plan,
        )

        if plan.errors:
            return AgentResponse(
                content=f"规划失败: {plan.errors}",
                conversation_id=conversation_id or "",
                plan=plan,
                execution_results=[],
                iterations=0,
            )

        # Step 2: 初始化状态
        state = self._initialize_state(query, template_id, plan.state_schema)

        # Step 3: 执行（使用 ExecutionEngine）
        agent_info = {
            "name": self.agent_name,
            "description": self.agent_description,
            "goals": self.agent_goals,
            "constraints": self.agent_constraints,
            "user_id": user_id,
        }

        results = []
        final_state = state
        
        async for event in self.executor.execute_plan_stream(
            plan=plan,
            state=state,
            conversation_id=conversation_id or "",
            tool_executor=tool_executor,
            agent_info=agent_info,
        ):
            if event["event"] == "execution_complete":
                final_state = event["data"]["state"]
                results = event["data"]["results"]

        # Step 4: 聚合结果
        final_response = self._aggregate_results(final_state)

        return AgentResponse(
            content=final_response,
            conversation_id=conversation_id or "",
            plan=plan,
            execution_results=results,
            iterations=final_state.get("control", {}).get("iterations", 0),
        )

    async def run_stream(
        self,
        query: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        template_id: Optional[int] = None,
        initial_plan: Optional[List[Dict[str, Any]]] = None,
        tool_executor: Optional[Callable] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行智能体任务

        直接复用 ExecutionEngine.execute_plan_stream()

        Yields:
            事件字典，包含：
            - event: 事件类型 (planning/stage_start/stage_complete/answer/done)
            - data: 事件数据
        """
        # Step 1: 规划阶段
        yield {"event": "planning", "data": {"message": "正在规划执行步骤..."}}

        plan = await self.planner.plan(
            query=query,
            user_context="",
            conversation_context="",
            initial_plan=initial_plan,
        )

        if plan.errors:
            yield {"event": "error", "data": {"message": "规划失败", "errors": plan.errors}}
            return

        yield {
            "event": "execution_plan",
            "data": {
                "agent_name": self.agent_name,
                "description": self.agent_description,
                "steps": [
                    {
                        "step": i + 1,
                        "step_id": s.id,
                        "name": s.tool,
                        "description": s.description,
                        "expectations": s.expectations,
                        "on_fail_strategy": s.on_fail_strategy,
                        "is_pinned": s.is_pinned,
                    }
                    for i, s in enumerate(plan.subtasks)
                ],
                "state_schema": plan.state_schema,
                "warnings": plan.warnings,
            },
        }

        # Step 2: 初始化状态
        state = self._initialize_state(query, template_id, plan.state_schema)

        # Step 3: 执行阶段（直接复用 ExecutionEngine.execute_plan_stream）
        agent_info = {
            "name": self.agent_name,
            "description": self.agent_description,
            "goals": self.agent_goals,
            "constraints": self.agent_constraints,
            "user_id": user_id,
        }

        final_state = state
        async for event in self.executor.execute_plan_stream(
            plan=plan,
            state=state,
            conversation_id=conversation_id or "",
            tool_executor=tool_executor,
            agent_info=agent_info,
        ):
            # 转发执行事件
            if event["event"] != "execution_complete":
                yield event
            else:
                final_state = event["data"]["state"]

        # Step 4: 生成答案
        final_response = self._aggregate_results(final_state)

        yield {
            "event": "answer",
            "data": {
                "answer": final_response,
                "document": final_state.get("reviewed_document")
                or final_state.get("composed_document"),
                "documents": final_state.get("documents", []),
            },
        }

        # Step 5: 完成
        yield {
            "event": "done",
            "data": {
                "success": True,
                "message": "Agent执行完成",
                "iterations": final_state.get("control", {}).get("iterations", 0),
            },
        }

    def _initialize_state(
        self,
        query: str,
        template_id: Optional[int],
        state_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """初始化统一状态字典"""
        state = {
            "inputs": {
                "query": query,
                "template_id": template_id,
            },
            "control": {
                "iterations": 0,
                "max_iterations": 20,
                "failed_steps": [],
            },
        }

        # 根据 state_schema 初始化字段
        if state_schema:
            for field, defn in state_schema.items():
                if field in ["inputs", "control"]:
                    continue
                if isinstance(defn, dict):
                    ftype = defn.get("type", "dict")
                    state[field] = (
                        [] if ftype == "list" else ({} if ftype == "dict" else defn.get("default"))
                    )
                elif isinstance(defn, str):
                    state[field] = [] if defn == "list" else ({} if defn == "dict" else None)
                else:
                    state[field] = {}

        return state

    def _aggregate_results(self, state: Dict[str, Any]) -> str:
        """聚合执行结果"""
        # 检查是否有最终文档
        final_document = state.get("reviewed_document") or state.get("composed_document")
        if final_document:
            return final_document.get("content", "执行完成")

        # 检查是否有检索结果
        documents = state.get("documents", [])
        if documents:
            return f"检索到 {len(documents)} 个相关文档"

        return "任务执行完成"

    def get_context(self):
        """获取当前执行上下文"""
        return self.executor.get_context()

    def get_context_summary(self) -> str:
        """获取执行上下文摘要"""
        return self.executor.get_context_summary()
