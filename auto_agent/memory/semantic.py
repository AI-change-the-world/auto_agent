"""
L2 长期语义记忆 (Semantic Memory)

基于 docs/MEMORY.md 设计：
- JSON 作为索引层（决策与检索）
- Markdown 作为语义表达层（具体内容）
- 一个用户一个 memory.json + 多个 reflections/*.md

存储结构：
    {storage_path}/
    └── {user_id}/
        ├── memory.json          # 唯一的索引文件
        └── reflections/         # Markdown 内容目录
            ├── {memory_id}.md
            └── ...
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from auto_agent.memory.models import (
    MemoryCategory,
    MemorySource,
    SemanticMemoryItem,
    UserFeedback,
)


class SemanticMemory:
    """
    L2 长期语义记忆

    设计原则（来自 MEMORY.md）：
    - JSON 负责：是否命中、是否注入上下文、注入优先级判断、学习与权重更新
    - Markdown 负责：高语义密度内容、强可读性、供模型理解与人工查看

    存储结构：
    - {user_id}/memory.json: 索引文件，存储所有记忆的元数据
    - {user_id}/reflections/{memory_id}.md: 具体内容文件
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        auto_save: bool = True,
        time_decay_factor: float = 0.01,
    ):
        self._memories: Dict[
            str, Dict[str, SemanticMemoryItem]
        ] = {}  # user_id -> {memory_id -> item}
        self._feedbacks: Dict[str, List[UserFeedback]] = {}  # user_id -> feedbacks
        self._storage_path = Path(storage_path) if storage_path else None
        self._auto_save = auto_save
        self._time_decay_factor = time_decay_factor

        if self._storage_path:
            self._storage_path.mkdir(parents=True, exist_ok=True)

    # ==================== 基础 CRUD ====================

    def add(
        self,
        user_id: str,
        content: str,
        category: MemoryCategory = MemoryCategory.CUSTOM,
        subcategory: str = "",
        tags: Optional[List[str]] = None,
        confidence: float = 0.5,
        source: MemorySource = MemorySource.AGENT_INFERENCE,
        metadata: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
        detail_content: Optional[str] = None,  # 详细内容（存入 Markdown）
    ) -> SemanticMemoryItem:
        """
        添加记忆

        Args:
            user_id: 用户 ID
            content: 简短摘要（存入 JSON 索引）
            category: 分类
            subcategory: 子分类
            tags: 标签列表
            confidence: 置信度
            source: 来源
            metadata: 元数据
            ttl: 过期时间（秒）
            detail_content: 详细内容（可选，存入 Markdown 文件）

        Returns:
            SemanticMemoryItem
        """
        self._ensure_loaded(user_id)

        memory_id = SemanticMemoryItem.generate_id()
        current_time = int(time.time())

        # 如果有详细内容，创建 Markdown 文件
        md_ref = None
        if detail_content and self._storage_path:
            md_ref = f"reflections/{memory_id}.md"
            self._save_markdown(user_id, memory_id, detail_content, category, tags)

        item = SemanticMemoryItem(
            memory_id=memory_id,
            category=category,
            subcategory=subcategory,
            tags=tags or [],
            content=content,  # JSON 中只存简短摘要
            confidence=confidence,
            source=source,
            created_at=current_time,
            updated_at=current_time,
            expires_at=current_time + ttl if ttl else None,
            metadata=metadata or {},
            summary_md_ref=md_ref,  # 关联 Markdown 文件
        )

        self._memories[user_id][memory_id] = item

        if self._auto_save and self._storage_path:
            self._save_user(user_id)

        return item

    def get(self, user_id: str, memory_id: str) -> Optional[SemanticMemoryItem]:
        """获取记忆"""
        self._ensure_loaded(user_id)
        item = self._memories.get(user_id, {}).get(memory_id)

        if item and item.is_expired():
            self.delete(user_id, memory_id)
            return None

        # 更新访问信息
        if item:
            item.access_count += 1
            item.last_accessed_at = int(time.time())

        return item

    def update(
        self,
        user_id: str,
        memory_id: str,
        content: Optional[str] = None,
        confidence: Optional[float] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[SemanticMemoryItem]:
        """更新记忆"""
        item = self.get(user_id, memory_id)
        if not item:
            return None

        if content is not None:
            item.content = content
        if confidence is not None:
            item.confidence = confidence
        if tags is not None:
            item.tags = tags
        if metadata is not None:
            item.metadata.update(metadata)

        item.updated_at = int(time.time())
        item.needs_revision = False  # 更新后清除修订标记

        if self._auto_save and self._storage_path:
            self._save_user(user_id)

        return item

    def delete(self, user_id: str, memory_id: str) -> bool:
        """删除记忆（同时删除关联的 Markdown 文件）"""
        if user_id in self._memories and memory_id in self._memories[user_id]:
            # 删除关联的 Markdown 文件
            self.delete_markdown(user_id, memory_id)
            # 删除索引
            del self._memories[user_id][memory_id]
            if self._auto_save and self._storage_path:
                self._save_user(user_id)
            return True
        return False

    # ==================== 查询方法 ====================

    def get_by_category(
        self,
        user_id: str,
        category: MemoryCategory,
        subcategory: Optional[str] = None,
        limit: int = 50,
    ) -> List[SemanticMemoryItem]:
        """按分类获取记忆"""
        self._ensure_loaded(user_id)

        items = []
        for item in self._memories.get(user_id, {}).values():
            if item.is_expired():
                continue
            if item.category != category:
                continue
            if subcategory and item.subcategory != subcategory:
                continue
            items.append(item)

        # 按综合得分排序
        items.sort(
            key=lambda x: x.calculate_score(self._time_decay_factor), reverse=True
        )
        return items[:limit]

    def get_by_tags(
        self,
        user_id: str,
        tags: List[str],
        match_all: bool = False,
        limit: int = 50,
    ) -> List[SemanticMemoryItem]:
        """按标签获取记忆"""
        self._ensure_loaded(user_id)

        items = []
        for item in self._memories.get(user_id, {}).values():
            if item.is_expired():
                continue
            if match_all:
                if all(tag in item.tags for tag in tags):
                    items.append(item)
            else:
                if any(tag in item.tags for tag in tags):
                    items.append(item)

        items.sort(
            key=lambda x: x.calculate_score(self._time_decay_factor), reverse=True
        )
        return items[:limit]

    def search(
        self,
        user_id: str,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 20,
    ) -> List[SemanticMemoryItem]:
        """全文检索"""
        self._ensure_loaded(user_id)

        query_lower = query.lower()
        query_words = set(re.findall(r"\w+", query_lower))
        results = []

        for item in self._memories.get(user_id, {}).values():
            if item.is_expired():
                continue
            if category and item.category != category:
                continue

            # 计算匹配分数
            searchable = f"{item.content} {item.subcategory} {' '.join(item.tags)}"
            searchable_lower = searchable.lower()

            match_score = 0
            # 完整匹配
            if query_lower in searchable_lower:
                match_score += 10
            # 词匹配
            for word in query_words:
                if word in searchable_lower:
                    match_score += 1

            if match_score > 0:
                # 综合得分 = 匹配分数 * 记忆质量分数
                total_score = match_score * item.calculate_score(
                    self._time_decay_factor
                )
                results.append((total_score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:limit]]

    def get_top_memories(
        self,
        user_id: str,
        limit: int = 10,
        category: Optional[MemoryCategory] = None,
    ) -> List[SemanticMemoryItem]:
        """获取得分最高的记忆"""
        self._ensure_loaded(user_id)

        items = []
        for item in self._memories.get(user_id, {}).values():
            if item.is_expired():
                continue
            if category and item.category != category:
                continue
            items.append(item)

        items.sort(
            key=lambda x: x.calculate_score(self._time_decay_factor), reverse=True
        )
        return items[:limit]

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
        item = self.get(user_id, memory_id)
        if not item:
            return None

        # 创建反馈记录
        feedback = UserFeedback(
            feedback_id=f"fb_{int(time.time())}_{memory_id[-8:]}",
            memory_id=memory_id,
            rating=rating,
            comment=comment,
        )

        if user_id not in self._feedbacks:
            self._feedbacks[user_id] = []
        self._feedbacks[user_id].append(feedback)

        # 更新记忆的 reward
        self._apply_feedback(item, rating)

        if self._auto_save and self._storage_path:
            self._save_user(user_id)

        return feedback

    def _apply_feedback(self, item: SemanticMemoryItem, rating: int):
        """应用反馈到记忆"""
        # 归一化 rating 到 [-1, 1]
        if rating in [-1, 1]:
            normalized = rating
        else:
            normalized = (rating - 3) / 2  # 1-5 -> [-1, 1]

        # 更新 reward（累积）
        item.reward = max(-1.0, min(1.0, item.reward + normalized * 0.2))

        # 更新 confidence
        if normalized > 0:
            item.confidence = min(1.0, item.confidence + 0.1)
        else:
            item.confidence = max(0.1, item.confidence - 0.1)
            # 负反馈标记需要修订
            if normalized < -0.3:
                item.needs_revision = True

        item.updated_at = int(time.time())

    # ==================== 记忆提炼 ====================

    def promote_from_working(
        self,
        user_id: str,
        candidates: List[Dict[str, Any]],
    ) -> List[SemanticMemoryItem]:
        """
        从短时记忆提炼到长期记忆

        Args:
            user_id: 用户 ID
            candidates: 候选记忆列表（来自 WorkingMemory.extract_for_long_term）

        Returns:
            创建的长期记忆列表
        """
        created = []

        for candidate in candidates:
            content = candidate.get("content", "")
            if not content:
                continue

            # 检查是否已存在相似记忆
            existing = self.search(user_id, content, limit=1)
            if existing and self._is_similar(content, existing[0].content):
                # 更新现有记忆的 confidence
                existing[0].confidence = min(1.0, existing[0].confidence + 0.1)
                existing[0].access_count += 1
                continue

            # 创建新记忆
            category = MemoryCategory(candidate.get("category", "custom"))
            source = MemorySource(candidate.get("source", "task_result"))

            # 负面经验降低初始 confidence
            confidence = 0.3 if candidate.get("is_negative") else 0.5

            item = self.add(
                user_id=user_id,
                content=content,
                category=category,
                source=source,
                confidence=confidence,
                tags=candidate.get("tags", []),
            )
            created.append(item)

        return created

    def _is_similar(self, content1: str, content2: str, threshold: float = 0.7) -> bool:
        """简单相似度判断"""
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())
        if not words1 or not words2:
            return False
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union > threshold

    # ==================== 上下文生成 ====================

    def get_context_for_query(
        self,
        user_id: str,
        query: str,
        categories: Optional[List[MemoryCategory]] = None,
        max_tokens: int = 2000,
    ) -> str:
        """
        为查询生成记忆上下文

        按需注入，只返回相关且必要的记忆
        """
        lines = []
        char_count = 0
        max_chars = max_tokens * 4  # 粗略估计

        # 1. 搜索相关记忆
        relevant = self.search(user_id, query, limit=10)

        # 2. 如果指定了分类，补充分类记忆
        if categories:
            for cat in categories:
                cat_memories = self.get_by_category(user_id, cat, limit=5)
                for m in cat_memories:
                    if m not in relevant:
                        relevant.append(m)

        # 3. 添加高 reward 的偏好记忆
        preferences = self.get_by_category(user_id, MemoryCategory.PREFERENCE, limit=5)
        for p in preferences:
            if p not in relevant and p.reward > 0.3:
                relevant.append(p)

        # 4. 按得分排序
        relevant.sort(
            key=lambda x: x.calculate_score(self._time_decay_factor), reverse=True
        )

        # 5. 生成上下文
        for item in relevant:
            line = f"- [{item.category.value}] {item.content}"
            if char_count + len(line) > max_chars:
                break
            lines.append(line)
            char_count += len(line)

        if not lines:
            return ""

        return "【相关记忆】\n" + "\n".join(lines)

    # ==================== 持久化 ====================

    def _get_user_dir(self, user_id: str) -> Path:
        """获取用户目录"""
        return self._storage_path / user_id

    def _get_user_file(self, user_id: str) -> Path:
        """获取用户索引文件（唯一的 JSON 文件）"""
        return self._get_user_dir(user_id) / "memory.json"

    def _get_reflections_dir(self, user_id: str) -> Path:
        """获取用户 Markdown 目录"""
        return self._get_user_dir(user_id) / "reflections"

    def _ensure_loaded(self, user_id: str):
        """确保用户数据已加载"""
        if user_id not in self._memories:
            self._load_user(user_id)

    def _save_user(self, user_id: str):
        """保存用户记忆索引（JSON）"""
        if not self._storage_path:
            return

        user_dir = self._get_user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_user_file(user_id)
        data = {
            "user_id": user_id,
            "version": "2.0",  # 新版本标识
            "memories": {
                mid: item.to_dict()
                for mid, item in self._memories.get(user_id, {}).items()
            },
            "feedbacks": [f.to_dict() for f in self._feedbacks.get(user_id, [])],
        }
        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _load_user(self, user_id: str):
        """加载用户记忆"""
        self._memories[user_id] = {}
        self._feedbacks[user_id] = []

        if not self._storage_path:
            return

        file_path = self._get_user_file(user_id)
        if not file_path.exists():
            # 尝试兼容旧格式
            old_file = self._storage_path / f"{user_id}_semantic.json"
            if old_file.exists():
                self._migrate_old_format(user_id, old_file)
                return
            return

        try:
            data = json.loads(file_path.read_text())
            for mid, item_data in data.get("memories", {}).items():
                self._memories[user_id][mid] = SemanticMemoryItem.from_dict(item_data)
            for fb_data in data.get("feedbacks", []):
                self._feedbacks[user_id].append(
                    UserFeedback(
                        feedback_id=fb_data["feedback_id"],
                        memory_id=fb_data["memory_id"],
                        rating=fb_data["rating"],
                        comment=fb_data.get("comment"),
                        timestamp=fb_data.get("timestamp", 0),
                    )
                )
        except Exception:
            pass

    def _migrate_old_format(self, user_id: str, old_file: Path):
        """迁移旧格式数据"""
        try:
            data = json.loads(old_file.read_text())
            for mid, item_data in data.get("memories", {}).items():
                self._memories[user_id][mid] = SemanticMemoryItem.from_dict(item_data)
            for fb_data in data.get("feedbacks", []):
                self._feedbacks[user_id].append(
                    UserFeedback(
                        feedback_id=fb_data["feedback_id"],
                        memory_id=fb_data["memory_id"],
                        rating=fb_data["rating"],
                        comment=fb_data.get("comment"),
                        timestamp=fb_data.get("timestamp", 0),
                    )
                )
            # 保存为新格式
            self._save_user(user_id)
            # 删除旧文件
            old_file.unlink()
        except Exception:
            pass

    def _save_markdown(
        self,
        user_id: str,
        memory_id: str,
        content: str,
        category: MemoryCategory,
        tags: Optional[List[str]] = None,
    ):
        """保存 Markdown 内容文件"""
        if not self._storage_path:
            return

        reflections_dir = self._get_reflections_dir(user_id)
        reflections_dir.mkdir(parents=True, exist_ok=True)

        md_path = reflections_dir / f"{memory_id}.md"

        # 生成 Markdown 文件（带 front-matter）
        front_matter = f"""---
memory_id: {memory_id}
category: {category.value}
tags: {json.dumps(tags or [], ensure_ascii=False)}
created_at: {time.strftime("%Y-%m-%d %H:%M:%S")}
---

"""
        md_path.write_text(front_matter + content, encoding="utf-8")

    def get_markdown_content(self, user_id: str, memory_id: str) -> Optional[str]:
        """获取记忆的 Markdown 详细内容"""
        if not self._storage_path:
            return None

        md_path = self._get_reflections_dir(user_id) / f"{memory_id}.md"
        if not md_path.exists():
            return None

        try:
            content = md_path.read_text(encoding="utf-8")
            # 去除 front-matter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    return parts[2].strip()
            return content
        except Exception:
            return None

    def delete_markdown(self, user_id: str, memory_id: str):
        """删除 Markdown 文件"""
        if not self._storage_path:
            return

        md_path = self._get_reflections_dir(user_id) / f"{memory_id}.md"
        if md_path.exists():
            md_path.unlink()

    def cleanup_expired(self, user_id: str) -> int:
        """清理过期记忆"""
        self._ensure_loaded(user_id)

        expired = [
            mid
            for mid, item in self._memories.get(user_id, {}).items()
            if item.is_expired()
        ]

        for mid in expired:
            del self._memories[user_id][mid]

        if expired and self._auto_save and self._storage_path:
            self._save_user(user_id)

        return len(expired)

    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """获取记忆统计"""
        self._ensure_loaded(user_id)

        memories = self._memories.get(user_id, {})
        by_category = {}
        total_reward = 0.0

        for item in memories.values():
            cat = item.category.value
            by_category[cat] = by_category.get(cat, 0) + 1
            total_reward += item.reward

        return {
            "total_memories": len(memories),
            "by_category": by_category,
            "total_feedbacks": len(self._feedbacks.get(user_id, [])),
            "average_reward": total_reward / len(memories) if memories else 0,
        }
