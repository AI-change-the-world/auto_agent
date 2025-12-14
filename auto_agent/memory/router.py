"""
记忆路由器 (Memory Router)

Query → 记忆命中流程：
1. 轻量分析 Query（意图类型、领域分类）
2. 确定所需记忆层级与分类
3. 仅在相关 L2 记忆子集中检索
4. 按权重、时间衰减排序
5. Top-K 命中记忆转为文本注入上下文
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from auto_agent.memory.models import MemoryCategory
from auto_agent.memory.semantic import SemanticMemory
from auto_agent.memory.narrative import NarrativeMemoryManager


class QueryIntent:
    """查询意图"""

    INQUIRY = "inquiry"  # 询问
    DECISION = "decision"  # 决策
    REFLECTION = "reflection"  # 反思
    ACTION = "action"  # 执行动作
    UNKNOWN = "unknown"


class MemoryRouter:
    """
    记忆路由器

    核心功能：
    1. 分析 Query 的意图和领域
    2. 决定需要检索哪些记忆
    3. 控制记忆注入的 Token 预算
    """

    # 领域关键词映射
    CATEGORY_KEYWORDS = {
        MemoryCategory.WORK: [
            "工作", "项目", "代码", "开发", "技术", "API", "系统", "部署",
            "work", "project", "code", "develop", "tech", "api", "system",
        ],
        MemoryCategory.LIFE: [
            "生活", "日常", "习惯", "健康", "运动", "饮食",
            "life", "daily", "habit", "health", "exercise",
        ],
        MemoryCategory.PREFERENCE: [
            "喜欢", "偏好", "习惯", "风格", "方式",
            "prefer", "like", "style", "way",
        ],
        MemoryCategory.EMOTION: [
            "感觉", "情绪", "态度", "心情",
            "feel", "emotion", "mood", "attitude",
        ],
        MemoryCategory.STRATEGY: [
            "方法", "策略", "经验", "技巧", "怎么", "如何",
            "method", "strategy", "experience", "how", "tip",
        ],
        MemoryCategory.KNOWLEDGE: [
            "什么是", "定义", "概念", "知识", "了解",
            "what is", "define", "concept", "knowledge",
        ],
    }

    # 意图关键词映射
    INTENT_KEYWORDS = {
        QueryIntent.INQUIRY: ["什么", "为什么", "怎么", "如何", "是否", "?", "？"],
        QueryIntent.DECISION: ["选择", "决定", "应该", "建议", "推荐"],
        QueryIntent.REFLECTION: ["总结", "反思", "回顾", "学到", "经验"],
        QueryIntent.ACTION: ["帮我", "执行", "创建", "生成", "写", "做"],
    }

    def __init__(
        self,
        semantic_memory: SemanticMemory,
        narrative_memory: Optional[NarrativeMemoryManager] = None,
        default_token_budget: int = 2000,
    ):
        self.semantic_memory = semantic_memory
        self.narrative_memory = narrative_memory
        self.default_token_budget = default_token_budget

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        分析查询

        返回：
        - intent: 意图类型
        - categories: 相关领域分类
        - keywords: 提取的关键词
        """
        query_lower = query.lower()

        # 识别意图
        intent = QueryIntent.UNKNOWN
        for intent_type, keywords in self.INTENT_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                intent = intent_type
                break

        # 识别领域
        categories = []
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                categories.append(category)

        # 如果没有识别到领域，默认使用 WORK 和 KNOWLEDGE
        if not categories:
            categories = [MemoryCategory.WORK, MemoryCategory.KNOWLEDGE]

        # 提取关键词（简单分词）
        keywords = re.findall(r"[\w\u4e00-\u9fff]+", query)
        keywords = [w for w in keywords if len(w) > 1]

        return {
            "intent": intent,
            "categories": categories,
            "keywords": keywords,
        }

    def route(
        self,
        user_id: str,
        query: str,
        token_budget: Optional[int] = None,
        include_narrative: bool = True,
    ) -> Dict[str, Any]:
        """
        路由查询到相关记忆

        返回：
        - context: 注入上下文的文本
        - memories: 命中的记忆列表
        - analysis: 查询分析结果
        - token_estimate: 估计的 token 数
        """
        token_budget = token_budget or self.default_token_budget
        max_chars = token_budget * 4  # 粗略估计

        # 1. 分析查询
        analysis = self.analyze_query(query)

        # 2. 检索 L2 语义记忆
        memories = []
        char_count = 0

        # 2.1 按相关分类检索
        for category in analysis["categories"]:
            cat_memories = self.semantic_memory.get_by_category(
                user_id, category, limit=5
            )
            for mem in cat_memories:
                if mem not in memories:
                    memories.append(mem)

        # 2.2 全文检索补充
        search_results = self.semantic_memory.search(user_id, query, limit=10)
        for mem in search_results:
            if mem not in memories:
                memories.append(mem)

        # 2.3 添加高 reward 的偏好记忆
        preferences = self.semantic_memory.get_by_category(
            user_id, MemoryCategory.PREFERENCE, limit=5
        )
        for pref in preferences:
            if pref.reward > 0.3 and pref not in memories:
                memories.append(pref)

        # 3. 按得分排序
        memories.sort(
            key=lambda x: x.calculate_score(self.semantic_memory._time_decay_factor),
            reverse=True,
        )

        # 4. 生成上下文
        context_lines = []

        # 4.1 L2 语义记忆
        if memories:
            context_lines.append("【相关记忆】")
            for mem in memories:
                line = f"- [{mem.category.value}] {mem.content}"
                if char_count + len(line) > max_chars * 0.7:  # 留 30% 给叙事记忆
                    break
                context_lines.append(line)
                char_count += len(line)

        # 4.2 L3 叙事记忆
        if include_narrative and self.narrative_memory:
            remaining_chars = max_chars - char_count
            if remaining_chars > 200:
                narrative_context = self.narrative_memory.get_context_for_prompt(
                    user_id,
                    categories=analysis["categories"],
                    max_chars=remaining_chars,
                )
                if narrative_context:
                    context_lines.append("")
                    context_lines.append(narrative_context)
                    char_count += len(narrative_context)

        context = "\n".join(context_lines) if context_lines else ""

        return {
            "context": context,
            "memories": memories,
            "analysis": analysis,
            "token_estimate": char_count // 4,
        }

    def should_use_memory(
        self,
        query: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        判断是否需要使用记忆

        某些简单查询可能不需要记忆注入
        """
        if analysis is None:
            analysis = self.analyze_query(query)

        # 简单问候不需要记忆
        greetings = ["你好", "hi", "hello", "嗨", "早上好", "晚上好"]
        if any(g in query.lower() for g in greetings) and len(query) < 10:
            return False, "简单问候，无需记忆"

        # 反思类查询需要记忆
        if analysis["intent"] == QueryIntent.REFLECTION:
            return True, "反思类查询，需要历史记忆"

        # 决策类查询需要偏好记忆
        if analysis["intent"] == QueryIntent.DECISION:
            return True, "决策类查询，需要偏好记忆"

        # 有明确领域的查询需要记忆
        if analysis["categories"]:
            return True, f"领域相关查询: {[c.value for c in analysis['categories']]}"

        return True, "默认使用记忆"

    def get_memory_injection_config(
        self,
        query: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        获取记忆注入配置

        根据查询类型决定：
        - 注入哪些层级的记忆
        - Token 预算分配
        - 优先级策略
        """
        if analysis is None:
            analysis = self.analyze_query(query)

        config = {
            "use_l2_semantic": True,
            "use_l3_narrative": False,
            "token_budget": self.default_token_budget,
            "priority": "relevance",  # relevance / recency / reward
        }

        intent = analysis["intent"]

        if intent == QueryIntent.REFLECTION:
            # 反思类：使用叙事记忆，增加预算
            config["use_l3_narrative"] = True
            config["token_budget"] = int(self.default_token_budget * 1.5)
            config["priority"] = "recency"

        elif intent == QueryIntent.DECISION:
            # 决策类：优先高 reward 记忆
            config["priority"] = "reward"

        elif intent == QueryIntent.ACTION:
            # 执行类：减少记忆注入，避免干扰
            config["token_budget"] = int(self.default_token_budget * 0.5)

        return config
