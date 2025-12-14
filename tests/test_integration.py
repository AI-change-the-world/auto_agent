"""
集成测试 - 完整的智能体工作流程

测试场景: 文档写作智能体
1. 解析 Markdown Agent 定义
2. 注册自定义工具
3. 使用意图路由
4. 管理会话状态
5. 记录用户记忆
6. 生成执行报告
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List

import pytest

from auto_agent import (
    AgentDefinition,
    AgentMarkdownParser,
    BaseTool,
    CategorizedMemory,
    ExecutionPlan,
    ExecutionReportGenerator,
    IntentRouter,
    MemoryCategory,
    PlanStep,
    SessionManager,
    SessionStatus,
    SubTaskResult,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    tool,
)


# ==================== 测试用工具 ====================


class MockAnalyzeTool(BaseTool):
    """模拟分析工具"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_input",
            description="分析用户输入",
            parameters=[
                ToolParameter(name="query", type="string", description="用户查询", required=True),
            ],
            category="analysis",
        )

    async def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        return {
            "success": True,
            "intent": "写作",
            "topic": query[:30],
            "keywords": ["测试", "文档"],
        }


class MockSearchTool(BaseTool):
    """模拟搜索工具"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="es_fulltext_search",
            description="全文检索",
            parameters=[
                ToolParameter(name="query", type="string", description="搜索查询", required=True),
            ],
            category="retrieval",
        )

    async def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        return {
            "success": True,
            "document_ids": ["doc_1", "doc_2", "doc_3"],
            "count": 3,
        }


class MockOutlineTool(BaseTool):
    """模拟大纲生成工具"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_outline",
            description="生成文档大纲",
            parameters=[
                ToolParameter(name="topic", type="string", description="文档主题", required=True),
            ],
            category="document",
        )

    async def execute(self, topic: str, **kwargs) -> Dict[str, Any]:
        return {
            "success": True,
            "outline": {
                "title": f"关于{topic}的报告",
                "sections": [
                    {"title": "背景"},
                    {"title": "分析"},
                    {"title": "结论"},
                ],
            },
        }


class MockComposeTool(BaseTool):
    """模拟文档撰写工具"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="document_compose",
            description="撰写文档",
            parameters=[
                ToolParameter(name="outline", type="object", description="文档大纲", required=True),
            ],
            category="document",
        )

    async def execute(self, outline: Dict, **kwargs) -> Dict[str, Any]:
        title = outline.get("title", "未命名")
        return {
            "success": True,
            "document": {
                "title": title,
                "content": f"# {title}\n\n这是生成的文档内容...",
                "word_count": 100,
            },
        }


# ==================== Agent 定义 ====================

WRITER_AGENT_MD = """
## 文档写作智能体

你需要按以下步骤完成用户的需求：

1. 调用 [analyze_input] 工具，分析用户意图
2. 调用 [es_fulltext_search] 工具，检索相关文档
3. 调用 [generate_outline] 工具，生成大纲
4. 调用 [document_compose] 工具，撰写文档

### 目标
- 理解用户的写作需求
- 生成结构清晰的文档

### 约束
- 文档长度不超过5000字
"""


# ==================== 集成测试 ====================


class TestWriterAgentIntegration:
    """文档写作智能体集成测试"""

    def setup_method(self):
        """每个测试前初始化"""
        # 工具注册表
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(MockAnalyzeTool())
        self.tool_registry.register(MockSearchTool())
        self.tool_registry.register(MockOutlineTool())
        self.tool_registry.register(MockComposeTool())

        # 会话管理器
        self.session_manager = SessionManager(default_ttl=300)

        # 分类记忆
        self.memory = CategorizedMemory(storage_path=None)

        # 意图路由器
        self.router = IntentRouter(llm_client=None, default_handler="default")
        self.router.register(
            name="writer",
            description="文档写作",
            keywords=["写", "撰写", "文档", "报告"],
        )
        self.router.register(
            name="search",
            description="信息检索",
            keywords=["搜索", "查找", "检索"],
        )
        self.router.register(
            name="default",
            description="默认处理",
            keywords=[],
        )

    @pytest.mark.asyncio
    async def test_parse_agent_definition(self):
        """测试解析 Agent 定义"""
        parser = AgentMarkdownParser(llm_client=None)
        result = await parser.parse(WRITER_AGENT_MD)

        assert result["success"] is True
        agent: AgentDefinition = result["agent"]

        assert agent.name is not None
        assert len(agent.goals) >= 1
        assert len(agent.initial_plan) == 4

        # 验证步骤
        tools = [s.tool for s in agent.initial_plan]
        assert "analyze_input" in tools
        assert "es_fulltext_search" in tools

    @pytest.mark.asyncio
    async def test_intent_routing(self):
        """测试意图路由"""
        # 写作意图
        result = await self.router.route("帮我写一篇关于AI的报告")
        assert result.handler_name == "writer"

        # 搜索意图
        result = await self.router.route("搜索机器学习资料")
        assert result.handler_name == "search"

    @pytest.mark.asyncio
    async def test_session_workflow(self):
        """测试会话工作流程"""
        user_id = "test_user"
        query = "帮我写一篇关于人工智能的报告"

        # 1. 创建会话
        session = self.session_manager.create_session(user_id, query)
        assert session.status == SessionStatus.ACTIVE

        # 2. 路由意图
        intent = await self.router.route(query)
        self.session_manager.update_session(
            session.session_id,
            state={"intent": intent.to_dict()},
        )

        # 3. 执行工具链
        analyze_tool = self.tool_registry.get_tool("analyze_input")
        result1 = await analyze_tool.execute(query=query)
        assert result1["success"] is True

        search_tool = self.tool_registry.get_tool("es_fulltext_search")
        result2 = await search_tool.execute(query=result1["topic"])
        assert result2["success"] is True

        outline_tool = self.tool_registry.get_tool("generate_outline")
        result3 = await outline_tool.execute(topic=result1["topic"])
        assert result3["success"] is True

        compose_tool = self.tool_registry.get_tool("document_compose")
        result4 = await compose_tool.execute(outline=result3["outline"])
        assert result4["success"] is True

        # 4. 完成会话
        self.session_manager.complete_session(
            session.session_id,
            final_result=result4["document"]["content"],
        )

        # 验证会话状态
        final_session = self.session_manager.get_session(session.session_id)
        assert final_session.status == SessionStatus.COMPLETED
        assert len(final_session.messages) == 2  # 用户消息 + 结果消息

    @pytest.mark.asyncio
    async def test_memory_integration(self):
        """测试记忆系统集成"""
        user_id = "test_user"

        # 1. 记录用户偏好
        self.memory.set_preference(user_id, "language", "中文")
        self.memory.set_preference(user_id, "style", "formal")

        # 2. 记录用户行为
        self.memory.add_behavior(user_id, "write_document", {"topic": "AI"})

        # 3. 添加用户反馈
        self.memory.add_feedback(user_id, "生成的文档很好", rating=5)

        # 4. 添加知识
        self.memory.add_knowledge(user_id, "用户是技术人员", tags=["职业"])

        # 5. 获取上下文摘要
        summary = self.memory.get_context_summary(user_id)
        assert "用户偏好" in summary
        assert "language" in summary

        # 6. 搜索记忆
        results = self.memory.search(user_id, "文档")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_execution_report(self):
        """测试执行报告生成"""
        # 模拟执行计划
        plan = ExecutionPlan(
            intent="文档写作",
            subtasks=[
                PlanStep(id="1", tool="analyze_input", description="分析输入"),
                PlanStep(id="2", tool="es_fulltext_search", description="检索文档"),
                PlanStep(id="3", tool="generate_outline", description="生成大纲"),
                PlanStep(id="4", tool="document_compose", description="撰写文档"),
            ],
        )

        # 模拟执行结果
        results = [
            SubTaskResult(step_id="1", success=True, output={"intent": "写作"}),
            SubTaskResult(step_id="2", success=True, output={"count": 5}),
            SubTaskResult(step_id="3", success=True, output={"outline": {}}),
            SubTaskResult(step_id="4", success=True, output={"document": {}}),
        ]

        # 生成报告
        start_time = datetime.now()
        report_data = ExecutionReportGenerator.generate_report_data(
            agent_name="文档写作智能体",
            query="写一篇AI报告",
            plan=plan,
            results=results,
            state={},
            start_time=start_time,
            end_time=datetime.now(),
        )

        # 验证报告数据
        assert report_data["agent_name"] == "文档写作智能体"
        assert report_data["statistics"]["total_steps"] == 4
        assert report_data["statistics"]["successful_steps"] == 4
        assert report_data["statistics"]["success_rate"] == 100.0

        # 生成 Markdown 报告
        markdown = ExecutionReportGenerator.generate_markdown_report(report_data)
        assert "# 智能体执行报告" in markdown
        assert "✅" in markdown  # 成功标记
        assert "mermaid" in markdown  # 流程图

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """测试完整工作流程"""
        user_id = "integration_test_user"
        query = "帮我写一篇关于机器学习的调研报告"

        # 1. 解析 Agent 定义
        parser = AgentMarkdownParser(llm_client=None)
        parse_result = await parser.parse(WRITER_AGENT_MD)
        assert parse_result["success"] is True
        agent_def = parse_result["agent"]

        # 2. 创建会话
        session = self.session_manager.create_session(user_id, query)

        # 3. 路由意图
        intent = await self.router.route(query)
        assert intent.handler_name == "writer"

        # 4. 记录用户行为
        self.memory.add_behavior(user_id, "start_task", {"query": query})

        # 5. 执行工具链
        execution_results = []
        state = {"query": query}

        for step in agent_def.initial_plan:
            tool = self.tool_registry.get_tool(step.tool)
            if tool:
                # 准备参数
                if step.tool == "analyze_input":
                    params = {"query": query}
                elif step.tool == "es_fulltext_search":
                    params = {"query": state.get("topic", query)}
                elif step.tool == "generate_outline":
                    params = {"topic": state.get("topic", query)}
                elif step.tool == "document_compose":
                    params = {"outline": state.get("outline", {})}
                else:
                    params = {}

                result = await tool.execute(**params)

                execution_results.append(
                    SubTaskResult(
                        step_id=step.id,
                        success=result.get("success", False),
                        output=result,
                    )
                )

                # 更新状态
                if result.get("success"):
                    if "topic" in result:
                        state["topic"] = result["topic"]
                    if "outline" in result:
                        state["outline"] = result["outline"]
                    if "document" in result:
                        state["document"] = result["document"]

        # 6. 生成执行报告
        plan = ExecutionPlan(
            intent=intent.intent,
            subtasks=agent_def.initial_plan,
        )

        report_data = ExecutionReportGenerator.generate_report_data(
            agent_name=agent_def.name,
            query=query,
            plan=plan,
            results=execution_results,
            state=state,
        )

        # 7. 完成会话
        final_content = state.get("document", {}).get("content", "完成")
        self.session_manager.complete_session(session.session_id, final_content)

        # 8. 记录反馈
        self.memory.add_feedback(user_id, "任务完成", rating=5)

        # 验证结果
        assert report_data["statistics"]["successful_steps"] == 4
        assert self.session_manager.get_session(session.session_id).status == SessionStatus.COMPLETED

        # 验证记忆
        behaviors = self.memory.get_by_category(user_id, MemoryCategory.BEHAVIOR_PATTERN)
        assert len(behaviors) >= 1

    @pytest.mark.asyncio
    async def test_session_with_user_intervention(self):
        """测试带用户干预的会话"""
        user_id = "intervention_user"
        query = "帮我写文档"

        # 1. 创建会话
        session = self.session_manager.create_session(user_id, query)

        # 2. 模拟需要用户输入
        self.session_manager.wait_for_input(
            session.session_id,
            prompt="请提供更多关于文档主题的信息",
        )

        # 验证等待状态
        waiting_session = self.session_manager.get_session(session.session_id)
        assert waiting_session.status == SessionStatus.WAITING_INPUT
        assert waiting_session.waiting_prompt is not None

        # 3. 用户提供输入
        self.session_manager.resume_session(
            session.session_id,
            user_input="主题是人工智能在医疗领域的应用",
        )

        # 验证恢复状态
        resumed_session = self.session_manager.get_session(session.session_id)
        assert resumed_session.status == SessionStatus.ACTIVE
        assert len(resumed_session.messages) == 2

        # 4. 完成会话
        self.session_manager.complete_session(session.session_id)
        final_session = self.session_manager.get_session(session.session_id)
        assert final_session.status == SessionStatus.COMPLETED


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
