"""
记忆系统数据模型

基于 docs/MEMORY.md 设计：
- L1: 短时记忆 (WorkingMemory)
- L2: 长期语义记忆 (SemanticMemory) - JSON 结构化
- L3: 叙事记忆 (NarrativeMemory) - Markdown 语义表达
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryLayer(Enum):
    """记忆层级"""

    L1_WORKING = "L1"  # 短时记忆
    L2_SEMANTIC = "L2"  # 长期语义记忆
    L3_NARRATIVE = "L3"  # 叙事记忆


class MemoryCategory(Enum):
    """记忆一级分类"""

    WORK = "work"  # 工作/技术/业务
    LIFE = "life"  # 生活经验/日常事实
    PREFERENCE = "preference"  # 用户或 Agent 偏好
    EMOTION = "emotion"  # 态度、情感倾向
    STRATEGY = "strategy"  # 方法论、成功/失败策略
    KNOWLEDGE = "knowledge"  # 知识/事实
    CUSTOM = "custom"  # 自定义


class MemorySource(Enum):
    """记忆来源"""

    USER_INPUT = "user_input"  # 用户直接输入
    USER_FEEDBACK = "user_feedback"  # 用户反馈
    AGENT_INFERENCE = "agent_inference"  # Agent 推理产生
    TASK_RESULT = "task_result"  # 任务执行结果
    REFLECTION = "reflection"  # 反思总结
    SYSTEM = "system"  # 系统预设


@dataclass
class SemanticMemoryItem:
    """
    L2 长期语义记忆条目 (JSON 结构化)

    用于系统层决策：命中判断、注入优先级、学习更新
    """

    memory_id: str
    layer: MemoryLayer = MemoryLayer.L2_SEMANTIC
    category: MemoryCategory = MemoryCategory.CUSTOM
    subcategory: str = ""
    tags: List[str] = field(default_factory=list)
    content: str = ""  # 核心内容
    confidence: float = 0.5  # 置信度 0-1
    reward: float = 0.0  # 奖励分数（用户反馈累积）
    source: MemorySource = MemorySource.AGENT_INFERENCE
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    access_count: int = 0  # 访问次数
    last_accessed_at: Optional[int] = None
    expires_at: Optional[int] = None  # 过期时间
    summary_md_ref: Optional[str] = None  # 关联的 Markdown 文件路径
    metadata: Dict[str, Any] = field(default_factory=dict)
    needs_revision: bool = False  # 是否需要修订

    @staticmethod
    def generate_id() -> str:
        """生成记忆 ID"""
        timestamp = time.strftime("%Y%m%d")
        short_uuid = uuid.uuid4().hex[:8]
        return f"mem_{timestamp}_{short_uuid}"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "memory_id": self.memory_id,
            "layer": self.layer.value,
            "category": self.category.value,
            "subcategory": self.subcategory,
            "tags": self.tags,
            "content": self.content,
            "confidence": self.confidence,
            "reward": self.reward,
            "source": self.source.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at,
            "expires_at": self.expires_at,
            "summary_md_ref": self.summary_md_ref,
            "metadata": self.metadata,
            "needs_revision": self.needs_revision,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticMemoryItem":
        """从字典创建"""
        return cls(
            memory_id=data["memory_id"],
            layer=MemoryLayer(data.get("layer", "L2")),
            category=MemoryCategory(data.get("category", "custom")),
            subcategory=data.get("subcategory", ""),
            tags=data.get("tags", []),
            content=data.get("content", ""),
            confidence=data.get("confidence", 0.5),
            reward=data.get("reward", 0.0),
            source=MemorySource(data.get("source", "agent_inference")),
            created_at=data.get("created_at", int(time.time())),
            updated_at=data.get("updated_at", int(time.time())),
            access_count=data.get("access_count", 0),
            last_accessed_at=data.get("last_accessed_at"),
            expires_at=data.get("expires_at"),
            summary_md_ref=data.get("summary_md_ref"),
            metadata=data.get("metadata", {}),
            needs_revision=data.get("needs_revision", False),
        )

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return int(time.time()) > self.expires_at

    def calculate_score(self, time_decay_factor: float = 0.01) -> float:
        """
        计算记忆综合得分（用于排序）

        综合考虑：confidence, reward, 时间衰减, 访问频率
        """
        current_time = int(time.time())
        age_days = (current_time - self.created_at) / 86400

        # 时间衰减
        time_decay = 1.0 / (1.0 + time_decay_factor * age_days)

        # 访问频率加成
        access_bonus = min(0.2, self.access_count * 0.02)

        # 综合得分
        score = (self.confidence * 0.4 + self.reward * 0.3 + time_decay * 0.2 + access_bonus * 0.1)

        # 需要修订的记忆降权
        if self.needs_revision:
            score *= 0.5

        return score


@dataclass
class WorkingMemoryItem:
    """
    L1 短时记忆条目

    单次任务执行过程中的上下文状态
    """

    item_id: str
    item_type: str  # query, subtask, decision, tool_call, result
    content: Any
    timestamp: int = field(default_factory=lambda: int(time.time()))
    step_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "content": self.content,
            "timestamp": self.timestamp,
            "step_id": self.step_id,
            "metadata": self.metadata,
        }


@dataclass
class NarrativeMemory:
    """
    L3 叙事记忆

    对长期记忆的语义压缩与自我认知表达 (Markdown)
    """

    narrative_id: str
    title: str
    content_md: str  # Markdown 内容
    related_memory_ids: List[str] = field(default_factory=list)  # 关联的 L2 记忆
    category: MemoryCategory = MemoryCategory.CUSTOM
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "narrative_id": self.narrative_id,
            "title": self.title,
            "content_md": self.content_md,
            "related_memory_ids": self.related_memory_ids,
            "category": self.category.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeMemory":
        return cls(
            narrative_id=data["narrative_id"],
            title=data.get("title", ""),
            content_md=data.get("content_md", ""),
            related_memory_ids=data.get("related_memory_ids", []),
            category=MemoryCategory(data.get("category", "custom")),
            created_at=data.get("created_at", int(time.time())),
            updated_at=data.get("updated_at", int(time.time())),
        )


@dataclass
class UserFeedback:
    """用户反馈"""

    feedback_id: str
    memory_id: str  # 关联的记忆 ID
    rating: int  # 1-5 分，或 -1(👎) / 1(👍)
    comment: Optional[str] = None
    timestamp: int = field(default_factory=lambda: int(time.time()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "memory_id": self.memory_id,
            "rating": self.rating,
            "comment": self.comment,
            "timestamp": self.timestamp,
        }


# ==================== 兼容旧接口 ====================


@dataclass
class UserMemory:
    """用户记忆（兼容旧接口）"""

    user_id: str
    preferences: Dict[str, Any] = field(default_factory=dict)
    knowledge: List[str] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    custom_context: str = ""


@dataclass
class ConversationMemory:
    """对话记忆（兼容旧接口）"""

    conversation_id: str
    user_id: str
    messages: List[Any] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    working_memory: Dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))


# 注意：新架构中 WorkingMemory 是一个类，这里为兼容旧接口保留 dataclass 版本
# 新代码应使用 auto_agent.memory.working.WorkingMemory
@dataclass
class WorkingMemoryData:
    """工作记忆数据（兼容旧接口）"""

    current_task: Optional[Dict[str, Any]] = None
    task_history: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: Dict[str, Any] = field(default_factory=dict)
    intermediate_steps: List[Dict[str, Any]] = field(default_factory=list)
