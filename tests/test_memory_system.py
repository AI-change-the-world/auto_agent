"""
新记忆系统测试 (L1/L2/L3 架构)

测试：
- L1 WorkingMemory (短时记忆)
- L2 SemanticMemory (长期语义记忆)
- L3 NarrativeMemoryManager (叙事记忆)
- MemoryRouter (记忆路由)
- MemorySystem (统一系统)
"""

import pytest
import time
from auto_agent.memory import (
    MemorySystem,
    WorkingMemory,
    SemanticMemory,
    NarrativeMemoryManager,
    MemoryRouter,
    MemoryCategory,
    MemorySource,
    SemanticMemoryItem,
    WorkingMemoryItem,
    UserFeedback,
    QueryIntent,
)


class TestWorkingMemory:
    """L1 短时记忆测试"""

    def test_start_task(self):
        wm = WorkingMemory()
        task_id = wm.start_task("帮我写一篇文章")
        assert task_id is not None
        assert wm.query == "帮我写一篇文章"
        assert len(wm.get_items()) == 1  # 初始 query

    def test_add_items(self):
        wm = WorkingMemory()
        wm.start_task("测试任务")

        # 添加子任务
        wm.add_subtask({"name": "step1", "description": "第一步"}, step_id="s1")
        # 添加决策
        wm.add_decision("使用方案A", "因为更高效", step_id="s1")
        # 添加工具调用
        wm.add_tool_call(
            "search",
            {"query": "test"},
            {"success": True, "count": 10},
            step_id="s1",
        )

        items = wm.get_items()
        assert len(items) == 4  # query + subtask + decision + tool_call

    def test_get_by_type(self):
        wm = WorkingMemory()
        wm.start_task("测试")
        wm.add_decision("决策1", "原因1")
        wm.add_decision("决策2", "原因2")

        decisions = wm.get_items(item_type="decision")
        assert len(decisions) == 2

    def test_to_context_string(self):
        wm = WorkingMemory()
        wm.start_task("帮我搜索文档")
        wm.add_tool_call(
            "search",
            {"query": "AI"},
            {"success": True, "count": 5},
            step_id="s1",
        )

        context = wm.to_context_string()
        assert "帮我搜索文档" in context
        assert "search" in context

    def test_extract_for_long_term(self):
        wm = WorkingMemory()
        wm.start_task("测试")
        wm.add_tool_call("tool1", {}, {"success": True}, step_id="s1")
        wm.add_tool_call("tool2", {}, {"success": True}, step_id="s2")
        wm.add_tool_call("tool3", {}, {"success": False, "error": "失败"}, step_id="s3")

        candidates = wm.extract_for_long_term()
        assert len(candidates) >= 2  # 成功策略 + 失败经验

    def test_clear(self):
        wm = WorkingMemory()
        wm.start_task("测试")
        wm.add_decision("决策", "原因")
        wm.clear()
        assert len(wm.get_items()) == 0
        assert wm.task_id is None


class TestSemanticMemory:
    """L2 长期语义记忆测试"""

    def test_add_and_get(self):
        sm = SemanticMemory()
        item = sm.add(
            user_id="user1",
            content="用户喜欢简洁的代码风格",
            category=MemoryCategory.PREFERENCE,
            tags=["code", "style"],
        )

        assert item.memory_id is not None
        assert item.category == MemoryCategory.PREFERENCE

        retrieved = sm.get("user1", item.memory_id)
        assert retrieved is not None
        assert retrieved.content == "用户喜欢简洁的代码风格"

    def test_get_by_category(self):
        sm = SemanticMemory()
        sm.add("user1", "偏好1", category=MemoryCategory.PREFERENCE)
        sm.add("user1", "偏好2", category=MemoryCategory.PREFERENCE)
        sm.add("user1", "知识1", category=MemoryCategory.KNOWLEDGE)

        prefs = sm.get_by_category("user1", MemoryCategory.PREFERENCE)
        assert len(prefs) == 2

    def test_get_by_tags(self):
        sm = SemanticMemory()
        sm.add("user1", "Python技巧", tags=["python", "tips"])
        sm.add("user1", "Java技巧", tags=["java", "tips"])
        sm.add("user1", "其他", tags=["other"])

        results = sm.get_by_tags("user1", ["tips"])
        assert len(results) == 2

        results_all = sm.get_by_tags("user1", ["python", "tips"], match_all=True)
        assert len(results_all) == 1

    def test_search(self):
        sm = SemanticMemory()
        sm.add("user1", "Python是一种编程语言")
        sm.add("user1", "JavaScript用于前端开发")
        sm.add("user1", "数据库存储数据")

        # 搜索单个词
        results = sm.search("user1", "Python")
        assert len(results) >= 1
        assert "Python" in results[0].content

    def test_feedback_positive(self):
        sm = SemanticMemory()
        item = sm.add("user1", "测试记忆", confidence=0.5)
        original_confidence = item.confidence

        feedback = sm.add_feedback("user1", item.memory_id, rating=1)  # 👍
        assert feedback is not None

        updated = sm.get("user1", item.memory_id)
        assert updated.confidence > original_confidence
        assert updated.reward > 0

    def test_feedback_negative(self):
        sm = SemanticMemory()
        item = sm.add("user1", "测试记忆", confidence=0.5)

        sm.add_feedback("user1", item.memory_id, rating=-1)  # 👎

        updated = sm.get("user1", item.memory_id)
        assert updated.confidence < 0.5
        assert updated.reward < 0
        assert updated.needs_revision is True

    def test_calculate_score(self):
        item = SemanticMemoryItem(
            memory_id="test",
            content="测试",
            confidence=0.8,
            reward=0.5,
        )
        score = item.calculate_score()
        assert 0 < score < 1

    def test_ttl_expiration(self):
        sm = SemanticMemory()
        item = sm.add("user1", "临时记忆", ttl=1)  # 1秒过期

        # 立即获取应该存在
        assert sm.get("user1", item.memory_id) is not None

        # 等待过期（2秒确保过期）
        time.sleep(2)
        assert sm.get("user1", item.memory_id) is None

    def test_promote_from_working(self):
        sm = SemanticMemory()
        candidates = [
            {"content": "成功策略1", "category": "strategy", "source": "task_result"},
            {"content": "失败经验", "category": "strategy", "source": "task_result", "is_negative": True},
        ]

        created = sm.promote_from_working("user1", candidates)
        assert len(created) == 2

        # 负面经验 confidence 更低
        negative = [c for c in created if "失败" in c.content][0]
        positive = [c for c in created if "成功" in c.content][0]
        assert negative.confidence < positive.confidence


class TestNarrativeMemory:
    """L3 叙事记忆测试"""

    def test_create_and_get(self):
        nm = NarrativeMemoryManager()
        nar = nm.create(
            user_id="user1",
            title="代码风格反思",
            content_md="# 反思\n\n简洁代码更易维护",
            category=MemoryCategory.STRATEGY,
        )

        assert nar.narrative_id is not None
        retrieved = nm.get("user1", nar.narrative_id)
        assert retrieved is not None
        assert "简洁代码" in retrieved.content_md

    def test_get_by_category(self):
        nm = NarrativeMemoryManager()
        nm.create("user1", "策略1", "内容1", category=MemoryCategory.STRATEGY)
        nm.create("user1", "策略2", "内容2", category=MemoryCategory.STRATEGY)
        nm.create("user1", "偏好1", "内容3", category=MemoryCategory.PREFERENCE)

        strategies = nm.get_by_category("user1", MemoryCategory.STRATEGY)
        assert len(strategies) == 2

    def test_get_context_for_prompt(self):
        nm = NarrativeMemoryManager()
        nm.create(
            "user1",
            "编码经验",
            "# 经验\n\n- 保持代码简洁\n- 写好注释",
            category=MemoryCategory.STRATEGY,
        )

        context = nm.get_context_for_prompt("user1")
        assert "保持代码简洁" in context or "Agent" in context


class TestMemoryRouter:
    """记忆路由器测试"""

    def test_analyze_query_intent(self):
        sm = SemanticMemory()
        router = MemoryRouter(sm)

        # 询问类
        analysis = router.analyze_query("什么是Python?")
        assert analysis["intent"] == QueryIntent.INQUIRY

        # 决策类 - 不包含询问词
        analysis = router.analyze_query("选择哪个方案比较好")
        assert analysis["intent"] == QueryIntent.DECISION

        # 执行类
        analysis = router.analyze_query("帮我写一个函数")
        assert analysis["intent"] == QueryIntent.ACTION

    def test_analyze_query_category(self):
        sm = SemanticMemory()
        router = MemoryRouter(sm)

        analysis = router.analyze_query("这个项目的代码怎么部署?")
        assert MemoryCategory.WORK in analysis["categories"]

        analysis = router.analyze_query("我喜欢什么风格?")
        assert MemoryCategory.PREFERENCE in analysis["categories"]

    def test_should_use_memory(self):
        sm = SemanticMemory()
        router = MemoryRouter(sm)

        # 简单问候不需要记忆
        should_use, reason = router.should_use_memory("你好")
        assert should_use is False

        # 复杂查询需要记忆
        should_use, reason = router.should_use_memory("帮我总结一下之前的经验")
        assert should_use is True

    def test_route(self):
        sm = SemanticMemory()
        sm.add("user1", "用户偏好Python", category=MemoryCategory.PREFERENCE, tags=["python"])
        sm.add("user1", "之前用过FastAPI", category=MemoryCategory.WORK, tags=["fastapi"])

        router = MemoryRouter(sm)
        result = router.route("user1", "帮我写一个Python API")

        assert "context" in result
        assert "memories" in result
        assert len(result["memories"]) > 0

    def test_get_memory_injection_config(self):
        sm = SemanticMemory()
        router = MemoryRouter(sm)

        # 反思类增加预算
        config = router.get_memory_injection_config("总结一下我的学习经验")
        assert config["use_l3_narrative"] is True
        assert config["token_budget"] > router.default_token_budget

        # 执行类减少预算
        config = router.get_memory_injection_config("帮我创建一个文件")
        assert config["token_budget"] < router.default_token_budget


class TestMemorySystem:
    """统一记忆系统测试"""

    def test_start_and_end_task(self):
        ms = MemorySystem()
        task_id = ms.start_task("user1", "测试任务")
        assert task_id is not None

        wm = ms.get_working_memory(task_id)
        assert wm.query == "测试任务"

        # 结束任务
        ms.end_task("user1", task_id, promote_to_long_term=False)
        # 任务结束后 working memory 被清理
        assert task_id not in ms._working_memories

    def test_add_and_search_memory(self):
        ms = MemorySystem()
        item = ms.add_memory(
            user_id="user1",
            content="Python是最好的语言",
            category=MemoryCategory.KNOWLEDGE,
            tags=["python"],
        )

        results = ms.search_memory("user1", "Python")
        assert len(results) >= 1

    def test_feedback(self):
        ms = MemorySystem()
        item = ms.add_memory("user1", "测试记忆")

        # 👍
        ms.thumbs_up("user1", item.memory_id)
        updated = ms.get_memory("user1", item.memory_id)
        assert updated.reward > 0

        # 👎
        ms.thumbs_down("user1", item.memory_id, reason="不准确")
        updated = ms.get_memory("user1", item.memory_id)
        # reward 会下降

    def test_convenience_methods(self):
        ms = MemorySystem()

        # 设置偏好
        pref = ms.set_preference("user1", "language", "Python")
        assert pref.category == MemoryCategory.PREFERENCE

        # 添加知识
        knowledge = ms.add_knowledge("user1", "地球是圆的")
        assert knowledge.category == MemoryCategory.KNOWLEDGE

        # 添加策略
        strategy = ms.add_strategy("user1", "先写测试再写代码", is_successful=True)
        assert strategy.category == MemoryCategory.STRATEGY

    def test_get_context_for_query(self):
        ms = MemorySystem()
        ms.add_memory("user1", "用户喜欢简洁代码", category=MemoryCategory.PREFERENCE)
        ms.add_memory("user1", "之前用过Django", category=MemoryCategory.WORK)

        result = ms.get_context_for_query("user1", "帮我写一个Web应用")
        assert "context" in result
        assert "memories" in result

    def test_get_stats(self):
        ms = MemorySystem()
        ms.add_memory("user1", "记忆1", category=MemoryCategory.WORK)
        ms.add_memory("user1", "记忆2", category=MemoryCategory.PREFERENCE)

        stats = ms.get_stats("user1")
        assert stats["semantic"]["total_memories"] == 2
        assert "work" in stats["semantic"]["by_category"]

    def test_get_context_summary(self):
        ms = MemorySystem()
        ms.set_preference("user1", "style", "简洁")
        ms.add_knowledge("user1", "Python 3.10 支持模式匹配")

        summary = ms.get_context_summary("user1")
        assert "偏好" in summary or "已知" in summary
