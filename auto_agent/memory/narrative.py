"""
L3 叙事记忆 (Narrative Memory)

对长期记忆的语义压缩与自我认知表达
- Markdown 格式存储
- 高语义密度
- 用于 Prompt 注入和人类理解
"""

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from auto_agent.memory.models import MemoryCategory, NarrativeMemory


class NarrativeMemoryManager:
    """
    L3 叙事记忆管理器

    存储形式：Markdown（自然语言）
    来源：
    - L2 记忆的自动总结
    - 多次经验的抽象反思

    用途：
    - Prompt 注入（高语义密度）
    - 人类理解与调试
    - Agent 行为风格与长期一致性塑造
    """

    def __init__(self, storage_path: Optional[str] = None):
        self._narratives: Dict[
            str, Dict[str, NarrativeMemory]
        ] = {}  # user_id -> {narrative_id -> item}
        self._storage_path = Path(storage_path) if storage_path else None

        if self._storage_path:
            self._storage_path.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        user_id: str,
        title: str,
        content_md: str,
        related_memory_ids: Optional[List[str]] = None,
        category: MemoryCategory = MemoryCategory.CUSTOM,
    ) -> NarrativeMemory:
        """创建叙事记忆"""
        if user_id not in self._narratives:
            self._narratives[user_id] = {}

        narrative_id = f"nar_{time.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"

        narrative = NarrativeMemory(
            narrative_id=narrative_id,
            title=title,
            content_md=content_md,
            related_memory_ids=related_memory_ids or [],
            category=category,
        )

        self._narratives[user_id][narrative_id] = narrative

        # 保存 Markdown 文件
        if self._storage_path:
            self._save_narrative(user_id, narrative)

        return narrative

    def get(self, user_id: str, narrative_id: str) -> Optional[NarrativeMemory]:
        """获取叙事记忆"""
        self._ensure_loaded(user_id)
        return self._narratives.get(user_id, {}).get(narrative_id)

    def get_by_category(
        self,
        user_id: str,
        category: MemoryCategory,
        limit: int = 10,
    ) -> List[NarrativeMemory]:
        """按分类获取叙事记忆"""
        self._ensure_loaded(user_id)

        items = [
            n
            for n in self._narratives.get(user_id, {}).values()
            if n.category == category
        ]
        items.sort(key=lambda x: x.updated_at, reverse=True)
        return items[:limit]

    def get_all(self, user_id: str) -> List[NarrativeMemory]:
        """获取所有叙事记忆"""
        self._ensure_loaded(user_id)
        items = list(self._narratives.get(user_id, {}).values())
        items.sort(key=lambda x: x.updated_at, reverse=True)
        return items

    def update(
        self,
        user_id: str,
        narrative_id: str,
        title: Optional[str] = None,
        content_md: Optional[str] = None,
        related_memory_ids: Optional[List[str]] = None,
    ) -> Optional[NarrativeMemory]:
        """更新叙事记忆"""
        narrative = self.get(user_id, narrative_id)
        if not narrative:
            return None

        if title is not None:
            narrative.title = title
        if content_md is not None:
            narrative.content_md = content_md
        if related_memory_ids is not None:
            narrative.related_memory_ids = related_memory_ids

        narrative.updated_at = int(time.time())

        if self._storage_path:
            self._save_narrative(user_id, narrative)

        return narrative

    def delete(self, user_id: str, narrative_id: str) -> bool:
        """删除叙事记忆"""
        if user_id in self._narratives and narrative_id in self._narratives[user_id]:
            del self._narratives[user_id][narrative_id]

            # 删除 Markdown 文件
            if self._storage_path:
                md_path = self._get_narrative_path(user_id, narrative_id)
                if md_path.exists():
                    md_path.unlink()

            return True
        return False

    def generate_from_semantic_memories(
        self,
        user_id: str,
        memories: List[Any],  # List[SemanticMemoryItem]
        title: str,
        category: MemoryCategory = MemoryCategory.CUSTOM,
    ) -> NarrativeMemory:
        """
        从 L2 语义记忆生成 L3 叙事记忆

        将多条结构化记忆总结为自然语言叙述
        """
        # 按分类分组
        by_category: Dict[str, List[str]] = {}
        memory_ids = []

        for mem in memories:
            cat = mem.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(mem.content)
            memory_ids.append(mem.memory_id)

        # 生成 Markdown
        lines = [f"# {title}", "", f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}", ""]

        for cat, contents in by_category.items():
            lines.append(f"## {cat.title()}")
            lines.append("")
            for content in contents[:5]:  # 每个分类最多 5 条
                lines.append(f"- {content}")
            lines.append("")

        content_md = "\n".join(lines)

        return self.create(
            user_id=user_id,
            title=title,
            content_md=content_md,
            related_memory_ids=memory_ids,
            category=category,
        )

    def get_context_for_prompt(
        self,
        user_id: str,
        categories: Optional[List[MemoryCategory]] = None,
        max_chars: int = 2000,
    ) -> str:
        """
        获取用于 Prompt 注入的叙事上下文

        高语义密度，适合直接注入 LLM
        """
        self._ensure_loaded(user_id)

        narratives = []
        if categories:
            for cat in categories:
                narratives.extend(self.get_by_category(user_id, cat, limit=3))
        else:
            narratives = self.get_all(user_id)[:5]

        if not narratives:
            return ""

        lines = ["【Agent 认知与反思】"]
        char_count = 0

        for nar in narratives:
            # 提取 Markdown 的核心内容（跳过标题和元信息）
            content_lines = nar.content_md.split("\n")
            core_lines = [
                line
                for line in content_lines
                if line.strip()
                and not line.startswith("#")
                and not line.startswith(">")
            ]
            core_content = "\n".join(core_lines[:10])  # 最多 10 行

            if char_count + len(core_content) > max_chars:
                break

            lines.append(f"\n### {nar.title}")
            lines.append(core_content)
            char_count += len(core_content)

        return "\n".join(lines)

    # ==================== 持久化 ====================

    def _ensure_loaded(self, user_id: str):
        """确保用户数据已加载"""
        if user_id not in self._narratives:
            self._load_user(user_id)

    def _get_user_dir(self, user_id: str) -> Path:
        return self._storage_path / user_id / "narratives"

    def _get_narrative_path(self, user_id: str, narrative_id: str) -> Path:
        return self._get_user_dir(user_id) / f"{narrative_id}.md"

    def _save_narrative(self, user_id: str, narrative: NarrativeMemory):
        """保存叙事记忆为 Markdown 文件"""
        if not self._storage_path:
            return

        user_dir = self._get_user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        md_path = self._get_narrative_path(user_id, narrative.narrative_id)

        # 添加元信息到 Markdown
        meta = f"""---
narrative_id: {narrative.narrative_id}
category: {narrative.category.value}
related_memories: {narrative.related_memory_ids}
created_at: {narrative.created_at}
updated_at: {narrative.updated_at}
---

"""
        md_path.write_text(meta + narrative.content_md, encoding="utf-8")

    def _load_user(self, user_id: str):
        """加载用户的叙事记忆"""
        self._narratives[user_id] = {}

        if not self._storage_path:
            return

        user_dir = self._get_user_dir(user_id)
        if not user_dir.exists():
            return

        import re

        for md_file in user_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")

                # 解析 YAML front matter
                meta_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
                if meta_match:
                    meta_str = meta_match.group(1)
                    content_md = content[meta_match.end() :]

                    # 简单解析 YAML
                    narrative_id = re.search(r"narrative_id:\s*(.+)", meta_str)
                    category = re.search(r"category:\s*(.+)", meta_str)
                    created_at = re.search(r"created_at:\s*(\d+)", meta_str)
                    updated_at = re.search(r"updated_at:\s*(\d+)", meta_str)

                    if narrative_id:
                        nar = NarrativeMemory(
                            narrative_id=narrative_id.group(1).strip(),
                            title=md_file.stem,
                            content_md=content_md.strip(),
                            category=MemoryCategory(category.group(1).strip())
                            if category
                            else MemoryCategory.CUSTOM,
                            created_at=int(created_at.group(1))
                            if created_at
                            else int(time.time()),
                            updated_at=int(updated_at.group(1))
                            if updated_at
                            else int(time.time()),
                        )
                        self._narratives[user_id][nar.narrative_id] = nar
            except Exception:
                continue
