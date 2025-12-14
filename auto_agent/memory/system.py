"""
统一记忆系统 (Memory System)

整合 L1/L2/L3 三层记忆，提供统一接口
"""

import time
from typing import Any, Dict, List, Optional

from auto_agent.memory.models import (
    MemoryCategory,
    MemorySource,
    SemanticMemoryItem,
    UserFeedback,
)
from auto_agent.memory.working import WorkingMemory
from auto_agent.memory.semantic import SemanticMemory
from auto_agent.memory.narrative import NarrativeMemoryManager
from auto_agent.memory.router import MemoryRouter


class MemorySystem:
    """
    统一记忆系统

    整合三层记忆：
    - L1: WorkingMemory (短时记忆)
    - L2: SemanticMemory (长期语义记忆)
    - L3: NarrativeMemoryManager (叙事记忆)

    提供：
    - 统一的记忆访问接口
    - 记忆路由与注入
    - 反馈驱动的学习
    - 记忆提炼与总结
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        auto_save: bool = True,
        token_budget: int = 2000,
    ):
        self.storage_path = storage_path

        # L1: 短时记忆（每个任务独立）
        self._working_memories: Dict[str, WorkingMemory] = {}

        # L2: 长期语义记忆
        self.semantic = SemanticMemory(
            storage_path=storage_path,
            auto_save=auto_save,
        )

        # L3: 叙事记忆
        self.narrative = NarrativeMemoryManager(
            storage_path=storage_path,
        )

        # 记忆路由器
        self.router = MemoryRouter(
            semantic_memory=self.semantic,
            narrative_memory=self.narrative,
            default_token_budget=token_budget,
        )

    # ==================== L1 短时记忆 ====================

    def get_working_memory(self, task_id: str) -> WorkingMemory:
        """获取或创建任务的短时记忆"""
        if task_id not in self._working_memories:
            self._working_memories[task_id] = WorkingMemory()
        return self._working_memories[task_id]

    def start_task(self, user_id: str, query: str, task_id: Optional[str] = None) -> str:
        """开始新任务"""
        wm = WorkingMemory()
        actual_task_id = wm.start_task(query, task_id)
        self._working_memories[actual_task_id] = wm
        return actual_task_id

    def end_task(self, user_id: str, task_id: str, promote_to_long_term: bool = True):
        """
        结束任务

        可选：将短时记忆中的有价值内容提炼到长期记忆
        """
        wm = self._working_memories.get(task_id)
        if not wm:
            return

        if promote_to_long_term:
            # 提取候选记忆
            candidates = wm.extract_for_long_term()
            # 提炼到 L2
            self.semantic.promote_from_working(user_id, candidates)

        # 清理短时记忆
        del self._working_memories[task_id]

    # ==================== L2 长期记忆 ====================

    def add_memory(
        self,
        user_id: str,
        content: str,
        category: MemoryCategory = MemoryCategory.CUSTOM,
        subcategory: str = "",
        tags: Optional[List[str]] = None,
        source: MemorySource = MemorySource.USER_INPUT,
        confidence: float = 0.5,
    ) -> SemanticMemoryItem:
        """添加长期记忆"""
        return self.semantic.add(
            user_id=user_id,
            content=content,
            category=category,
            subcategory=subcategory,
            tags=tags,
            source=source,
            confidence=confidence,
        )

    def search_memory(
        self,
        user_id: str,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 20,
    ) -> List[SemanticMemoryItem]:
        """搜索记忆"""
        return self.semantic.search(user_id, query, category, limit)

    def get_memory(self, user_id: str, memory_id: str) -> Optional[SemanticMemoryItem]:
        """获取记忆"""
        return self.semantic.get(user_id, memory_id)

    # ==================== 反馈系统 ====================

    def add_feedback(
        self,
        user_id: str,
        memory_id: str,
        rating: int,
        comment: Optional[str] = None,
    ) -> Optional[UserFeedback]:
        """
        添加用户反馈

        rating: 1-5 分，或 -1(👎) / 1(👍)
        """
        return self.semantic.add_feedback(user_id, memory_id, rating, comment)

    def thumbs_up(self, user_id: str, memory_id: str) -> Optional[UserFeedback]:
        """👍 正反馈"""
        return self.add_feedback(user_id, memory_id, 1)

    def thumbs_down(self, user_id: str, memory_id: str, reason: Optional[str] = None) -> Optional[UserFeedback]:
        """👎 负反馈"""
        return self.add_feedback(user_id, memory_id, -1, reason)

    # ==================== 记忆路由与注入 ====================

    def get_context_for_query(
        self,
        user_id: str,
        query: str,
        token_budget: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        为查询获取记忆上下文

        返回：
        - context: 可直接注入 Prompt 的文本
        - memories: 命中的记忆列表
        - analysis: 查询分析结果
        """
        # 检查是否需要记忆
        should_use, reason = self.router.should_use_memory(query)
        if not should_use:
            return {
                "context": "",
                "memories": [],
                "analysis": {"skip_reason": reason},
                "token_estimate": 0,
            }

        # 获取注入配置
        config = self.router.get_memory_injection_config(query)
        budget = token_budget or config["token_budget"]

        # 路由并获取记忆
        return self.router.route(
            user_id=user_id,
            query=query,
            token_budget=budget,
            include_narrative=config["use_l3_narrative"],
        )

    # ==================== 记忆总结与反思 ====================

    def generate_reflection(
        self,
        user_id: str,
        title: str,
        category: MemoryCategory = MemoryCategory.STRATEGY,
        memory_ids: Optional[List[str]] = None,
    ) -> Any:
        """
        生成反思总结（L3 叙事记忆）

        从指定的 L2 记忆生成 Markdown 总结
        """
        # 获取相关记忆
        if memory_ids:
            memories = [
                self.semantic.get(user_id, mid)
                for mid in memory_ids
                if self.semantic.get(user_id, mid)
            ]
        else:
            # 获取该分类的 top 记忆
            memories = self.semantic.get_top_memories(user_id, limit=10, category=category)

        if not memories:
            return None

        return self.narrative.generate_from_semantic_memories(
            user_id=user_id,
            memories=memories,
            title=title,
            category=category,
        )

    # ==================== 便捷方法 ====================

    def set_preference(
        self,
        user_id: str,
        key: str,
        value: str,
    ) -> SemanticMemoryItem:
        """设置用户偏好"""
        return self.add_memory(
            user_id=user_id,
            content=f"{key}: {value}",
            category=MemoryCategory.PREFERENCE,
            tags=["preference", key],
            source=MemorySource.USER_INPUT,
            confidence=0.8,
        )

    def add_knowledge(
        self,
        user_id: str,
        fact: str,
        tags: Optional[List[str]] = None,
    ) -> SemanticMemoryItem:
        """添加知识"""
        return self.add_memory(
            user_id=user_id,
            content=fact,
            category=MemoryCategory.KNOWLEDGE,
            tags=tags or ["knowledge"],
            source=MemorySource.USER_INPUT,
            confidence=0.7,
        )

    def add_strategy(
        self,
        user_id: str,
        strategy: str,
        is_successful: bool = True,
        tags: Optional[List[str]] = None,
    ) -> SemanticMemoryItem:
        """添加策略经验"""
        return self.add_memory(
            user_id=user_id,
            content=strategy,
            category=MemoryCategory.STRATEGY,
            tags=tags or ["strategy"],
            source=MemorySource.TASK_RESULT,
            confidence=0.6 if is_successful else 0.3,
        )

    # ==================== 统计与管理 ====================

    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """获取记忆统计"""
        semantic_stats = self.semantic.get_stats(user_id)
        narrative_count = len(self.narrative.get_all(user_id))

        return {
            "semantic": semantic_stats,
            "narrative_count": narrative_count,
            "active_tasks": len(self._working_memories),
        }

    def cleanup(self, user_id: str) -> Dict[str, int]:
        """清理过期记忆"""
        expired_semantic = self.semantic.cleanup_expired(user_id)

        return {
            "expired_semantic": expired_semantic,
        }

    def get_context_summary(self, user_id: str, max_items: int = 10) -> str:
        """
        获取用户上下文摘要（兼容旧接口）
        """
        lines = []

        # 偏好
        prefs = self.semantic.get_by_category(user_id, MemoryCategory.PREFERENCE, limit=5)
        if prefs:
            lines.append("用户偏好:")
            for p in prefs:
                lines.append(f"  - {p.content}")

        # 知识
        knowledge = self.semantic.get_by_category(user_id, MemoryCategory.KNOWLEDGE, limit=5)
        if knowledge:
            lines.append("已知信息:")
            for k in knowledge:
                lines.append(f"  - {k.content}")

        # 策略
        strategies = self.semantic.get_by_category(user_id, MemoryCategory.STRATEGY, limit=3)
        if strategies:
            lines.append("经验策略:")
            for s in strategies:
                lines.append(f"  - {s.content}")

        return "\n".join(lines) if lines else "无用户上下文"
