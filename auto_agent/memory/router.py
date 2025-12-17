"""
记忆路由器 (Memory Router)

基于 docs/MEMORY.md 设计的智能记忆检索流程：

1. Query 进入系统
2. LLM 轻量分析 Query（意图类型、领域分类、关键词）
3. 确定所需记忆层级与分类
4. 仅在相关 L2 记忆子集中检索
5. 按权重、时间衰减排序
6. LLM 总结上下文（可选）
7. Top-K 命中记忆转为文本注入上下文
"""

import json
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from auto_agent.memory.models import MemoryCategory, SemanticMemoryItem
from auto_agent.memory.narrative import NarrativeMemoryManager
from auto_agent.memory.semantic import SemanticMemory

if TYPE_CHECKING:
    from auto_agent.llm.client import LLMClient


class QueryIntent:
    """查询意图"""

    INQUIRY = "inquiry"  # 询问
    DECISION = "decision"  # 决策
    REFLECTION = "reflection"  # 反思
    ACTION = "action"  # 执行动作
    CHAT = "chat"  # 闲聊
    UNKNOWN = "unknown"


class MemoryRouter:
    """
    智能记忆路由器

    核心功能：
    1. LLM 分析 Query 的意图和领域
    2. 智能决定需要检索哪些记忆
    3. 控制记忆注入的 Token 预算
    4. LLM 总结上下文（避免信息过载）
    """

    def __init__(
        self,
        semantic_memory: SemanticMemory,
        narrative_memory: Optional[NarrativeMemoryManager] = None,
        llm_client: Optional["LLMClient"] = None,
        default_token_budget: int = 2000,
    ):
        self.semantic_memory = semantic_memory
        self.narrative_memory = narrative_memory
        self.llm_client = llm_client
        self.default_token_budget = default_token_budget

    async def load_context(
        self,
        user_id: str,
        query: str,
        token_budget: Optional[int] = None,
        summarize: bool = True,
    ) -> Dict[str, Any]:
        """
        智能加载记忆上下文（主入口）

        流程：
        1. LLM 分析 Query（意图、领域、关键词）
        2. 从 JSON 索引中筛选候选记忆
        3. 加载相关 Markdown 详细内容
        4. LLM 总结上下文（可选）
        5. 返回可注入 Prompt 的上下文

        Args:
            user_id: 用户 ID
            query: 用户查询
            token_budget: Token 预算
            summarize: 是否使用 LLM 总结上下文

        Returns:
            {
                "context": str,  # 可直接注入 Prompt 的上下文
                "memories": List[SemanticMemoryItem],  # 命中的记忆
                "analysis": Dict,  # 查询分析结果
                "token_estimate": int,  # 估计的 token 数
            }
        """
        token_budget = token_budget or self.default_token_budget

        # 1. 分析 Query
        if self.llm_client:
            analysis = await self._analyze_query_with_llm(query)
        else:
            analysis = self._analyze_query_simple(query)

        # 2. 判断是否需要记忆
        should_use, reason = self.should_use_memory(query, analysis)
        if not should_use:
            return {
                "context": "",
                "memories": [],
                "analysis": {"skip_reason": reason, **analysis},
                "token_estimate": 0,
            }

        # 3. 从 JSON 索引中筛选候选记忆
        candidates = self._search_candidates(user_id, analysis)

        if not candidates:
            return {
                "context": "",
                "memories": [],
                "analysis": analysis,
                "token_estimate": 0,
            }

        # 4. 加载 Markdown 详细内容（如果有）
        memories_with_content = self._load_memory_contents(user_id, candidates)

        # 5. 生成上下文
        if summarize and self.llm_client and len(memories_with_content) > 3:
            # LLM 总结上下文
            context = await self._summarize_context_with_llm(
                query, memories_with_content, token_budget
            )
        else:
            # 直接拼接
            context = self._build_context_simple(memories_with_content, token_budget)

        return {
            "context": context,
            "memories": candidates,
            "analysis": analysis,
            "token_estimate": len(context) // 4,
        }

    async def _analyze_query_with_llm(self, query: str) -> Dict[str, Any]:
        """使用 LLM 分析查询"""
        prompt = f"""分析以下用户查询，提取关键信息。

【用户查询】
{query}

请返回 JSON 格式：
```json
{{
    "intent": "inquiry|decision|reflection|action|chat",
    "categories": ["work", "life", "preference", "strategy", "knowledge"],
    "keywords": ["关键词1", "关键词2"],
    "domain": "编程|设计|写作|其他",
    "needs_history": true/false
}}
```

说明：
- intent: 用户意图（inquiry=询问, decision=决策, reflection=反思, action=执行, chat=闲聊）
- categories: 相关领域（可多选）
- keywords: 用于检索的关键词
- domain: 具体领域
- needs_history: 是否需要历史记忆

只返回 JSON，不要其他内容。"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
            )

            # 提取 JSON
            json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                # 转换 categories 为 MemoryCategory
                result["categories"] = [
                    MemoryCategory(c)
                    for c in result.get("categories", [])
                    if c in [mc.value for mc in MemoryCategory]
                ]
                return result
        except Exception:
            pass

        # 失败时使用简单分析
        return self._analyze_query_simple(query)

    def _analyze_query_simple(self, query: str) -> Dict[str, Any]:
        """简单的查询分析（无 LLM）"""
        query_lower = query.lower()

        # 意图识别
        intent = QueryIntent.UNKNOWN
        intent_keywords = {
            QueryIntent.INQUIRY: ["什么", "为什么", "怎么", "如何", "是否", "?", "？"],
            QueryIntent.DECISION: ["选择", "决定", "应该", "建议", "推荐"],
            QueryIntent.REFLECTION: ["总结", "反思", "回顾", "学到", "经验"],
            QueryIntent.ACTION: ["帮我", "执行", "创建", "生成", "写", "做"],
            QueryIntent.CHAT: ["你好", "hi", "hello", "嗨"],
        }
        for intent_type, keywords in intent_keywords.items():
            if any(kw in query_lower for kw in keywords):
                intent = intent_type
                break

        # 领域识别
        category_keywords = {
            MemoryCategory.WORK: ["工作", "项目", "代码", "开发", "技术", "编程"],
            MemoryCategory.STRATEGY: ["方法", "策略", "经验", "技巧", "怎么", "如何"],
            MemoryCategory.KNOWLEDGE: ["什么是", "定义", "概念", "知识"],
            MemoryCategory.PREFERENCE: ["喜欢", "偏好", "习惯", "风格"],
        }
        categories = []
        for category, keywords in category_keywords.items():
            if any(kw in query_lower for kw in keywords):
                categories.append(category)

        if not categories:
            categories = [MemoryCategory.WORK, MemoryCategory.KNOWLEDGE]

        # 提取关键词
        keywords = re.findall(r"[\w\u4e00-\u9fff]+", query)
        keywords = [w for w in keywords if len(w) > 1]

        return {
            "intent": intent,
            "categories": categories,
            "keywords": keywords,
            "domain": "unknown",
            "needs_history": intent != QueryIntent.CHAT,
        }

    def _search_candidates(
        self,
        user_id: str,
        analysis: Dict[str, Any],
        limit: int = 20,
    ) -> List[SemanticMemoryItem]:
        """从 JSON 索引中筛选候选记忆"""
        candidates = []
        seen_ids = set()

        # 1. 按分类检索
        for category in analysis.get("categories", []):
            cat_memories = self.semantic_memory.get_by_category(
                user_id, category, limit=5
            )
            for mem in cat_memories:
                if mem.memory_id not in seen_ids:
                    candidates.append(mem)
                    seen_ids.add(mem.memory_id)

        # 2. 按关键词检索
        keywords = analysis.get("keywords", [])
        if keywords:
            query_str = " ".join(keywords)
            search_results = self.semantic_memory.search(user_id, query_str, limit=10)
            for mem in search_results:
                if mem.memory_id not in seen_ids:
                    candidates.append(mem)
                    seen_ids.add(mem.memory_id)

        # 3. 添加高 reward 的偏好记忆
        preferences = self.semantic_memory.get_by_category(
            user_id, MemoryCategory.PREFERENCE, limit=5
        )
        for pref in preferences:
            if pref.reward > 0.3 and pref.memory_id not in seen_ids:
                candidates.append(pref)
                seen_ids.add(pref.memory_id)

        # 4. 按得分排序
        candidates.sort(
            key=lambda x: x.calculate_score(self.semantic_memory._time_decay_factor),
            reverse=True,
        )

        return candidates[:limit]

    def _load_memory_contents(
        self,
        user_id: str,
        memories: List[SemanticMemoryItem],
    ) -> List[Dict[str, Any]]:
        """加载记忆的详细内容（从 Markdown）"""
        results = []
        for mem in memories:
            item = {
                "memory_id": mem.memory_id,
                "category": mem.category.value,
                "summary": mem.content,  # JSON 中的简短摘要
                "detail": None,  # Markdown 中的详细内容
                "confidence": mem.confidence,
                "reward": mem.reward,
            }

            # 如果有关联的 Markdown，加载详细内容
            if mem.summary_md_ref:
                detail = self.semantic_memory.get_markdown_content(
                    user_id, mem.memory_id
                )
                if detail:
                    item["detail"] = detail

            results.append(item)

        return results

    async def _summarize_context_with_llm(
        self,
        query: str,
        memories: List[Dict[str, Any]],
        token_budget: int,
    ) -> str:
        """使用 LLM 总结记忆上下文"""
        # 构建记忆列表
        memory_texts = []
        for mem in memories:
            text = f"[{mem['category']}] {mem['summary']}"
            if mem.get("detail"):
                text += f"\n详细: {mem['detail'][:500]}"
            memory_texts.append(text)

        memories_str = "\n\n".join(memory_texts)

        prompt = f"""根据用户查询，从以下记忆中提取相关信息，生成简洁的上下文摘要。

【用户查询】
{query}

【可用记忆】
{memories_str}

【要求】
1. 只提取与查询相关的信息
2. 保持简洁，控制在 {token_budget // 2} 字以内
3. 如果记忆中没有相关信息，返回空字符串
4. 使用自然语言，不要列表格式

请直接返回摘要内容，不要包含任何解释。"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            summary = response.strip()
            if summary and summary != "空" and len(summary) > 10:
                return f"【相关记忆】\n{summary}"
        except Exception:
            pass

        # 失败时使用简单拼接
        return self._build_context_simple(memories, token_budget)

    def _build_context_simple(
        self,
        memories: List[Dict[str, Any]],
        token_budget: int,
    ) -> str:
        """简单拼接记忆上下文"""
        if not memories:
            return ""

        max_chars = token_budget * 4
        lines = ["【相关记忆】"]
        char_count = 0

        for mem in memories:
            line = f"- [{mem['category']}] {mem['summary']}"
            if char_count + len(line) > max_chars:
                break
            lines.append(line)
            char_count += len(line)

        return "\n".join(lines) if len(lines) > 1 else ""

    def should_use_memory(
        self,
        query: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """判断是否需要使用记忆"""
        if analysis is None:
            analysis = self._analyze_query_simple(query)

        # 闲聊不需要记忆
        if analysis.get("intent") == QueryIntent.CHAT:
            return False, "闲聊类查询，无需记忆"

        # 明确不需要历史
        if analysis.get("needs_history") is False:
            return False, "查询不需要历史记忆"

        return True, "需要记忆"

    # ==================== 兼容旧接口 ====================

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """分析查询（同步版本，兼容旧接口）"""
        return self._analyze_query_simple(query)

    def route(
        self,
        user_id: str,
        query: str,
        token_budget: Optional[int] = None,
        include_narrative: bool = True,
    ) -> Dict[str, Any]:
        """
        路由查询到相关记忆（同步版本，兼容旧接口）

        注意：此方法不使用 LLM，仅做简单匹配
        推荐使用 load_context() 异步方法
        """
        token_budget = token_budget or self.default_token_budget
        analysis = self._analyze_query_simple(query)

        should_use, reason = self.should_use_memory(query, analysis)
        if not should_use:
            return {
                "context": "",
                "memories": [],
                "analysis": {"skip_reason": reason, **analysis},
                "token_estimate": 0,
            }

        candidates = self._search_candidates(user_id, analysis)
        memories_with_content = self._load_memory_contents(user_id, candidates)
        context = self._build_context_simple(memories_with_content, token_budget)

        return {
            "context": context,
            "memories": candidates,
            "analysis": analysis,
            "token_estimate": len(context) // 4,
        }

    def get_memory_injection_config(
        self,
        query: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """获取记忆注入配置"""
        if analysis is None:
            analysis = self._analyze_query_simple(query)

        config = {
            "use_l2_semantic": True,
            "use_l3_narrative": False,
            "token_budget": self.default_token_budget,
            "priority": "relevance",
        }

        intent = analysis.get("intent", QueryIntent.UNKNOWN)

        if intent == QueryIntent.REFLECTION:
            config["use_l3_narrative"] = True
            config["token_budget"] = int(self.default_token_budget * 1.5)
            config["priority"] = "recency"
        elif intent == QueryIntent.DECISION:
            config["priority"] = "reward"
        elif intent == QueryIntent.ACTION:
            config["token_budget"] = int(self.default_token_budget * 0.5)

        return config
