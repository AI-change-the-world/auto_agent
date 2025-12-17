"""
意图路由器测试
"""

import pytest

from auto_agent.core.router.intent import IntentHandler, IntentRouter


class TestIntentRouter:
    """意图路由器测试"""

    def setup_method(self):
        """每个测试前初始化"""
        self.router = IntentRouter(llm_client=None, default_handler="default")

        # 注册测试处理器
        self.router.register(
            name="writer",
            description="文档写作",
            keywords=["写", "撰写", "文档", "报告", "文章"],
        )
        self.router.register(
            name="search",
            description="信息检索",
            keywords=["搜索", "查找", "检索", "查询"],
        )
        self.router.register(
            name="analysis",
            description="数据分析",
            keywords=["分析", "统计", "数据"],
        )
        self.router.register(
            name="default",
            description="默认处理",
            keywords=[],
        )

    @pytest.mark.asyncio
    async def test_route_writer_intent(self):
        """测试路由到写作意图"""
        result = await self.router.route("帮我写一篇关于AI的报告")

        assert result.handler_name == "writer"
        assert result.confidence > 0.5
        assert "写" in result.parameters.get(
            "matched_keywords", []
        ) or "报告" in result.parameters.get("matched_keywords", [])

    @pytest.mark.asyncio
    async def test_route_search_intent(self):
        """测试路由到搜索意图"""
        result = await self.router.route("搜索关于机器学习的资料")

        assert result.handler_name == "search"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_route_analysis_intent(self):
        """测试路由到分析意图"""
        result = await self.router.route("分析这些数据的趋势")

        assert result.handler_name == "analysis"
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_route_default_no_match(self):
        """测试无匹配时使用默认处理器"""
        result = await self.router.route("随便说点什么")

        assert result.handler_name == "default"
        assert result.confidence < 0.5

    @pytest.mark.asyncio
    async def test_route_multiple_keywords(self):
        """测试多关键词匹配提高置信度"""
        result = await self.router.route("帮我写一篇文档报告")

        assert result.handler_name == "writer"
        # 多个关键词匹配应该有更高的置信度
        assert result.confidence >= 0.6

    def test_register_handler(self):
        """测试注册处理器"""
        handler = IntentHandler(
            name="custom",
            description="自定义处理",
            keywords=["自定义"],
        )
        self.router.register_handler(handler)

        retrieved = self.router.get_handler("custom")
        assert retrieved is not None
        assert retrieved.name == "custom"

    def test_get_handler_not_exists(self):
        """测试获取不存在的处理器"""
        handler = self.router.get_handler("non_existent")
        assert handler is None

    @pytest.mark.asyncio
    async def test_route_and_execute_no_handler(self):
        """测试路由执行但无执行器"""
        result = await self.router.route_and_execute("写一篇文章")

        assert result["success"] is False
        assert "no executor" in result["error"]

    @pytest.mark.asyncio
    async def test_route_and_execute_with_handler(self):
        """测试路由执行有执行器"""

        async def mock_handler(query, parameters, context):
            return {"result": f"处理: {query}"}

        self.router.register(
            name="echo",
            description="回显处理",
            keywords=["回显", "echo"],
            handler=mock_handler,
        )

        result = await self.router.route_and_execute("echo 测试")

        assert result["success"] is True
        assert "处理" in result["output"]["result"]
