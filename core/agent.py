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
"""

import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from auto_agent.core.orchestrator import AgentOrchestrator
from auto_agent.llm.client import LLMClient
from auto_agent.memory.long_term import LongTermMemory
from auto_agent.memory.short_term import ShortTermMemory
from auto_agent.models import AgentResponse, ExecutionPlan, Message, PlanStep
from auto_agent.retry.models import RetryConfig
from auto_agent.tools.registry import ToolRegistry


class AutoAgent:
    """
    Auto-Agent 主类

    核心改进（来自 custom_agent_executor_v2.py）：
    1. 执行时由 LLM 动态规划步骤
    2. 使用统一 state dict 管理数据流
    3. 自然语言描述期望，而非符号化 checkpoint
    4. 明确回退策略表
    5. 短期记忆智能压缩
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        long_term_memory: LongTermMemory,
        short_term_memory: ShortTermMemory,
        retry_config: Optional[RetryConfig] = None,
        agent_goals: Optional[List[str]] = None,
        agent_constraints: Optional[List[str]] = None,
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.ltm = long_term_memory
        self.stm = short_term_memory
        self.agent_goals = agent_goals or []
        self.agent_constraints = agent_constraints or []

        # 初始化编排器
        self.orchestrator = AgentOrchestrator(
            llm_client=llm_client,
            tool_registry=tool_registry,
            retry_config=retry_config or RetryConfig(),
            agent_goals=agent_goals,
            agent_constraints=agent_constraints,
        )

    async def run(
        self,
        query: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        template_id: Optional[int] = None,
        initial_plan: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
    ) -> AgentResponse:
        """
        执行智能体任务

        Args:
            query: 用户查询
            user_id: 用户ID
            conversation_id: 对话ID（可选）
            template_id: 模板ID（可选）
            initial_plan: 初始计划（含固定步骤）
            stream: 是否流式返回

        Returns:
            AgentResponse
        """
        # Step 1: 加载长期记忆
        user_context = self.ltm.get_relevant_context(user_id, query)

        # Step 2: 创建或获取对话
        if not conversation_id:
            conversation_id = self.stm.create_conversation(user_id)

        # Step 3: 添加用户消息
        self.stm.add_message(
            conversation_id,
            Message(
                role="user", content=query, timestamp=int(time.time()), metadata={}
            ),
        )

        # Step 4: 获取对话上下文（压缩版）
        conversation_context = self.stm.summarize_conversation(conversation_id)

        # Step 5: 初始化状态字典
        state = self._initialize_state(query, template_id)

        # Step 6: 使用编排器执行（规划+执行）
        plan, results, final_state = await self.orchestrator.execute(
            query=query,
            user_context=user_context,
            conversation_context=conversation_context,
            conversation_id=conversation_id,
            initial_state=state,
            initial_plan=initial_plan,
        )

        # Step 7: 聚合结果
        final_response = await self._aggregate_results(results, plan, final_state)

        # Step 8: 添加助手消息
        self.stm.add_message(
            conversation_id,
            Message(
                role="assistant",
                content=final_response,
                timestamp=int(time.time()),
                metadata={"plan": plan.__dict__, "results": [r.__dict__ for r in results]},
            ),
        )

        # Step 9: 更新长期记忆
        await self._update_long_term_memory(user_id, conversation_id, plan, results)

        return AgentResponse(
            content=final_response,
            conversation_id=conversation_id,
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
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行智能体任务

        Yields:
            事件字典，包含：
            - event: 事件类型 (planning/stage_start/stage_complete/answer/done)
            - data: 事件数据
        """
        # Step 1: 加载记忆
        user_context = self.ltm.get_relevant_context(user_id, query)

        if not conversation_id:
            conversation_id = self.stm.create_conversation(user_id)

        self.stm.add_message(
            conversation_id,
            Message(
                role="user", content=query, timestamp=int(time.time()), metadata={}
            ),
        )

        conversation_context = self.stm.summarize_conversation(conversation_id)

        # Step 2: 初始化状态
        state = self._initialize_state(query, template_id)

        # Step 3: 规划阶段
        yield {"event": "planning", "data": {"message": "正在规划执行步骤..."}}

        plan = await self.orchestrator.planner.plan(
            query=query,
            user_context=user_context,
            conversation_context=conversation_context,
            initial_plan=initial_plan,
        )

        if plan.errors:
            yield {"event": "error", "data": {"message": "规划失败", "errors": plan.errors}}
            return

        yield {
            "event": "execution_plan",
            "data": {
                "steps": [s.__dict__ for s in plan.subtasks],
                "state_schema": plan.state_schema,
                "warnings": plan.warnings,
            },
        }

        # Step 4: 执行阶段
        results = []

        async def on_step_complete(subtask: PlanStep, result):
            yield_data = {
                "event": "stage_complete",
                "data": {
                    "step": subtask.id,
                    "name": subtask.tool,
                    "description": subtask.description,
                    "success": result.success,
                    "status": "completed" if result.success else "failed",
                },
            }
            # 注意：这里不能直接 yield，需要通过回调处理

        results, final_state = await self.orchestrator.executor.execute_plan(
            plan=plan,
            state=state,
            conversation_id=conversation_id,
        )

        # Step 5: 生成答案
        final_response = await self._aggregate_results(results, plan, final_state)

        yield {
            "event": "answer",
            "data": {
                "answer": final_response,
                "document": final_state.get("reviewed_document")
                or final_state.get("composed_document"),
                "documents": final_state.get("documents", []),
            },
        }

        # Step 6: 完成
        yield {
            "event": "done",
            "data": {
                "success": True,
                "message": "Agent执行完成",
                "iterations": final_state.get("control", {}).get("iterations", 0),
            },
        }

    def _initialize_state(
        self, query: str, template_id: Optional[int]
    ) -> Dict[str, Any]:
        """初始化统一状态字典"""
        return {
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

    async def _aggregate_results(
        self, results, plan: ExecutionPlan, state: Dict[str, Any]
    ) -> str:
        """聚合执行结果"""
        # 检查是否有最终文档
        final_document = state.get("reviewed_document") or state.get("composed_document")
        if final_document:
            return final_document.get("content", "执行完成")

        # 检查是否有检索结果
        documents = state.get("documents", [])
        if documents:
            return f"检索到 {len(documents)} 个相关文档"

        # 简单拼接成功的输出
        outputs = [r.output for r in results if r.success and r.output]
        if outputs:
            return "\n".join(str(o) for o in outputs)

        return "任务执行完成"

    async def _update_long_term_memory(
        self, user_id: str, conversation_id: str, plan: ExecutionPlan, results
    ):
        """更新长期记忆（提取关键信息）"""
        # 简化实现：暂不自动更新
        # TODO: 使用 LLM 提取关键信息并保存
        pass
