"""
短期记忆（Short-term Memory）

核心功能：
- 对话历史管理
- 工作记忆（执行状态）
- 智能压缩（summarize_state）
- 工具依赖关系感知
"""

import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from auto_agent.memory.models import ConversationMemory, WorkingMemory
from auto_agent.models import Message


class ShortTermMemory:
    """
    短期记忆

    支持：
    - 对话历史管理
    - 执行状态（state dict）
    - 智能压缩（避免传递大量文本给 LLM）
    """

    def __init__(
        self,
        max_history_messages: int = 20,
        max_context_chars: int = 51200,
        backend: str = "memory",
        **kwargs,
    ):
        """
        Args:
            max_history_messages: 最大历史消息数
            max_context_chars: 最大上下文字符数
            backend: 存储后端 (memory/sqlite/redis)
        """
        self.max_history_messages = max_history_messages
        self.max_context_chars = max_context_chars
        self.backend = backend
        self._conversations: Dict[str, ConversationMemory] = {}

    def create_conversation(self, user_id: str) -> str:
        """创建新对话"""
        conversation_id = str(uuid.uuid4())
        self._conversations[conversation_id] = ConversationMemory(
            conversation_id=conversation_id,
            user_id=user_id,
            created_at=int(time.time()),
            updated_at=int(time.time()),
        )
        return conversation_id

    def add_message(self, conversation_id: str, message: Message) -> None:
        """添加消息"""
        conv = self._conversations.get(conversation_id)
        if conv:
            conv.messages.append(message)
            # 限制历史消息数量
            conv.messages = conv.messages[-self.max_history_messages :]
            conv.updated_at = int(time.time())

    def get_conversation_history(
        self, conversation_id: str, limit: int = 10
    ) -> List[Message]:
        """获取对话历史"""
        conv = self._conversations.get(conversation_id)
        if conv:
            return conv.messages[-limit:]
        return []

    def get_context(self, conversation_id: str) -> Dict[str, Any]:
        """获取对话上下文"""
        conv = self._conversations.get(conversation_id)
        return conv.context if conv else {}

    def update_context(self, conversation_id: str, context: Dict[str, Any]) -> None:
        """更新对话上下文"""
        conv = self._conversations.get(conversation_id)
        if conv:
            conv.context.update(context)
            conv.updated_at = int(time.time())

    def get_working_memory(self, conversation_id: str) -> Optional[WorkingMemory]:
        """获取工作记忆"""
        conv = self._conversations.get(conversation_id)
        return conv.working_memory if conv else None

    def clear_working_memory(self, conversation_id: str) -> None:
        """清除工作记忆"""
        conv = self._conversations.get(conversation_id)
        if conv:
            conv.working_memory = WorkingMemory()

    def summarize_conversation(self, conversation_id: str) -> str:
        """总结对话"""
        messages = self.get_conversation_history(
            conversation_id, limit=self.max_history_messages
        )
        if not messages:
            return "无对话历史"

        summary = []
        for msg in messages:
            summary.append(f"{msg.role}: {msg.content}")
        return "\n".join(summary)

    # ==================== 智能压缩（核心功能） ====================

    def summarize_state(
        self,
        state: Dict[str, Any],
        step_history: List[Dict[str, Any]],
        target_tool_name: Optional[str] = None,
        max_steps: int = 10,
        compress_fn_getter: Optional[Callable[[str], Optional[Callable]]] = None,
    ) -> str:
        """
        生成压缩的状态摘要供 LLM 使用

        核心策略（来自 custom_agent_executor_v2.py）：
        1. 智能过滤：只保留与目标工具相关的历史步骤
        2. 工具压缩：使用工具自定义的 compress_function
        3. 数据摘要：大型数据只保留元信息

        Args:
            state: 当前执行状态字典
            step_history: 步骤执行历史
            target_tool_name: 目标工具名称（用于过滤相关步骤）
            max_steps: 最多保留的历史步骤数
            compress_fn_getter: 获取工具压缩函数的回调

        Returns:
            压缩后的状态描述（JSON 字符串）
        """
        compressed = {
            "query": state.get("inputs", {}).get("query", ""),
            "template_id": state.get("inputs", {}).get("template_id"),
            "step_history": [],
        }

        # 1. 智能过滤历史步骤
        relevant_steps = self._filter_relevant_steps(
            step_history, target_tool_name, max_steps
        )

        # 2. 压缩每一步的结果
        for step in relevant_steps:
            compressed_step = {
                "step": step.get("step"),
                "name": step.get("name"),
                "description": step.get("description", ""),
                "success": step.get("result", {}).get("success"),
            }

            tool_name = step.get("name", "")
            result = step.get("result", {})

            # 尝试使用工具自定义的压缩函数
            compress_func = None
            if compress_fn_getter:
                compress_func = compress_fn_getter(tool_name)

            if compress_func is not None:
                try:
                    compressed_result = compress_func(result, state)
                    if compressed_result is None:
                        # 返回 None 表示不压缩，保留完整结果
                        compressed_step["result"] = result
                    else:
                        compressed_step["result"] = compressed_result
                except Exception:
                    compressed_step["result"] = self._default_compress_result(result)
            else:
                compressed_step["result"] = self._default_compress_result(result)

            compressed["step_history"].append(compressed_step)

        # 3. 添加当前可用的中间数据摘要
        compressed["available_data"] = self._summarize_available_data(state)

        # 4. 转换为 JSON 并检查长度
        result_json = json.dumps(compressed, ensure_ascii=False, indent=1)

        # 如果超过限制，进一步压缩
        if len(result_json) > self.max_context_chars:
            compressed["step_history"] = compressed["step_history"][-3:]
            result_json = json.dumps(compressed, ensure_ascii=False, indent=1)

            if len(result_json) > self.max_context_chars:
                result_json = json.dumps(
                    compressed, ensure_ascii=False, separators=(",", ":")
                )

        return result_json

    def _filter_relevant_steps(
        self,
        step_history: List[Dict[str, Any]],
        target_tool_name: Optional[str],
        max_steps: int,
    ) -> List[Dict[str, Any]]:
        """
        智能过滤历史步骤

        基于工具依赖关系，优先保留与目标工具相关的步骤
        """
        if not target_tool_name:
            return step_history[-max_steps:]

        # 工具依赖关系表
        tool_dependencies = {
            "analyze_input": [],
            "multi_query_search": ["generate_outline", "analyze_input"],
            "get_document_contents": [
                "multi_query_search",
                "es_fulltext_search",
                "search_documents_by_classification",
            ],
            "skim_documents": ["multi_query_search", "es_fulltext_search"],
            "read_documents": ["multi_query_search", "es_fulltext_search"],
            "analyze_documents": [
                "get_document_contents",
                "skim_documents",
                "read_documents",
            ],
            "document_extraction": ["multi_query_search", "generate_outline"],
            "document_compose": ["document_extraction", "generate_outline"],
            "document_review": ["document_compose"],
            "es_fulltext_search": ["analyze_input"],
            "generate_outline": ["analyze_input"],
        }

        related_tools = tool_dependencies.get(target_tool_name, [])

        # 优先保留相关步骤
        relevant_steps = sorted(
            step_history,
            key=lambda s: (
                s.get("name") in related_tools,
                s.get("step", 0),
            ),
            reverse=True,
        )[:max_steps]

        return relevant_steps[-max_steps:] if len(relevant_steps) > max_steps else relevant_steps

    def _default_compress_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        默认结果压缩策略

        来自 custom_agent_executor_v2.py 的压缩逻辑
        """
        compressed_result = {}

        for key, value in result.items():
            # 文档内容特殊处理 - 只保留元数据
            if key == "documents" and isinstance(value, list):
                compressed_result["documents"] = [
                    {
                        "id": doc.get("id") or doc.get("document_id"),
                        "title": doc.get("title", "")[:50],
                        "content_length": len(doc.get("content", "")),
                    }
                    for doc in value[:5]
                ]
                if len(value) > 5:
                    compressed_result["documents_count"] = len(value)

            # 文档 ID 列表 - 只保留前 20 个
            elif key == "document_ids" and isinstance(value, list):
                compressed_result["document_ids"] = value[:20]
                if len(value) > 20:
                    compressed_result["document_ids_count"] = len(value)

            # 大纲结构 - 压缩处理
            elif key == "outline":
                if isinstance(value, dict):
                    compressed_outline = {
                        "title": value.get("title", "")[:100],
                        "sections_count": len(value.get("sections", [])),
                    }
                    sections = value.get("sections", [])[:3]
                    compressed_outline["sections"] = [
                        {"title": s.get("title", "")[:50]} for s in sections
                    ]
                    compressed_result["outline"] = compressed_outline
                elif isinstance(value, list):
                    compressed_result["outline"] = f"{len(value)} sections"
                else:
                    compressed_result["outline"] = value

            # 文档内容 - 只保留引用
            elif key == "document" and isinstance(value, dict):
                compressed_result["document"] = {
                    "title": value.get("title", "")[:50],
                    "word_count": value.get("word_count", 0),
                }

            # 错误信息
            elif key == "error":
                compressed_result["error"] = str(value)[:200]

            # 其他小型数据
            elif not isinstance(value, (list, dict)) or len(str(value)) < 300:
                compressed_result[key] = value

            # 大型数据只保留摘要
            else:
                compressed_result[f"{key}_summary"] = (
                    f"<{type(value).__name__}, {len(str(value))} chars>"
                )

        return compressed_result

    def _summarize_available_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成可用数据摘要
        """
        available_data = {}

        for key, value in state.items():
            if key in ["inputs", "control", "last_failure"]:
                continue

            if key == "documents" and isinstance(value, list):
                available_data["documents"] = f"{len(value)} docs available"
            elif key == "document_ids" and isinstance(value, list):
                available_data["document_ids"] = (
                    f"{len(value)} IDs: {value[:5]}..." if len(value) > 5 else value
                )
            elif key == "outline":
                if isinstance(value, dict):
                    sections_count = len(value.get("sections", []))
                    available_data["outline"] = f"outline with {sections_count} sections"
                elif isinstance(value, list):
                    available_data["outline"] = f"outline with {len(value)} sections"
            elif key == "quality" and isinstance(value, dict):
                available_data["quality"] = value
            elif key in ["composed_document", "reviewed_document"] and isinstance(
                value, dict
            ):
                available_data[key] = {
                    "title": value.get("title", "")[:50],
                    "word_count": value.get("word_count", 0),
                    "_ref": key,
                }
            elif key == "extracted_content" and isinstance(value, dict):
                chapter_count = len([k for k in value.keys() if k not in ["summary"]])
                available_data[key] = f"{chapter_count} chapters"
            elif isinstance(value, (list, dict)):
                available_data[key] = f"{type(value).__name__}({len(str(value))} chars)"
            else:
                available_data[key] = value

        return available_data
