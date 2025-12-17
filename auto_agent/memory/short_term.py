"""
短期记忆（Short-term Memory）（部分弃用）

核心功能：
- 对话历史管理（已弃用，请使用 WorkingMemory）
- 工作记忆（执行状态）（已弃用，请使用 WorkingMemory）
- 智能压缩（summarize_state）（仍然可用）
- 工具依赖关系感知

.. deprecated::
    对话历史和工作记忆功能已弃用，请使用新的 L1 短时记忆：
    - auto_agent.memory.working.WorkingMemory

    但 summarize_state() 方法仍然可用，用于压缩执行状态。
"""

import json
import time
import uuid
import warnings
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from auto_agent.memory.models import ConversationMemory
from auto_agent.memory.models import WorkingMemoryData as WorkingMemory
from auto_agent.models import Message


def _deprecated_class_partial(cls):
    """部分弃用的类装饰器"""
    original_init = cls.__init__

    @wraps(original_init)
    def new_init(self, *args, **kwargs):
        warnings.warn(
            f"{cls.__name__} 的对话历史和工作记忆功能已弃用，请使用 WorkingMemory 替代。"
            f"但 summarize_state() 方法仍然可用。"
            f"参见 auto_agent.memory.working.WorkingMemory",
            DeprecationWarning,
            stacklevel=2,
        )
        original_init(self, *args, **kwargs)

    cls.__init__ = new_init
    return cls


@_deprecated_class_partial
class ShortTermMemory:
    """
    短期记忆（部分弃用）

    .. deprecated::
        对话历史和工作记忆功能已弃用，请使用 WorkingMemory 替代。

        迁移指南：
        - ShortTermMemory.create_conversation() -> WorkingMemory.start_task()
        - ShortTermMemory.add_message() -> WorkingMemory.add_tool_call()
        - ShortTermMemory.get_working_memory() -> MemorySystem.get_working_memory()

        注意：summarize_state() 方法仍然可用，用于压缩执行状态。

    支持：
    - 对话历史管理（已弃用）
    - 执行状态（state dict）（已弃用）
    - 智能压缩（避免传递大量文本给 LLM）（仍然可用）
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
        tool_dependencies_getter: Optional[Callable[[str], List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        智能过滤历史步骤

        基于工具依赖关系，优先保留与目标工具相关的步骤

        Args:
            step_history: 步骤历史
            target_tool_name: 目标工具名称
            max_steps: 最大步骤数
            tool_dependencies_getter: 获取工具依赖关系的回调函数
        """
        if not target_tool_name:
            return step_history[-max_steps:]

        # 从工具定义获取依赖关系
        related_tools: List[str] = []
        if tool_dependencies_getter:
            related_tools = tool_dependencies_getter(target_tool_name) or []

        if not related_tools:
            # 没有依赖关系，直接返回最近的步骤
            return step_history[-max_steps:]

        # 优先保留相关步骤
        relevant_steps = sorted(
            step_history,
            key=lambda s: (
                s.get("name") in related_tools,
                s.get("step", 0),
            ),
            reverse=True,
        )[:max_steps]

        return (
            relevant_steps[-max_steps:]
            if len(relevant_steps) > max_steps
            else relevant_steps
        )

    def _default_compress_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        默认结果压缩策略

        通用的压缩逻辑，当工具没有定义 compress_function 时使用
        """
        if not isinstance(result, dict):
            return result

        compressed_result = {}

        for key, value in result.items():
            # 错误信息 - 截断
            if key == "error":
                compressed_result["error"] = str(value)[:200]
            # 列表类型 - 限制数量并添加计数
            elif isinstance(value, list):
                if len(value) > 10:
                    compressed_result[key] = value[:10]
                    compressed_result[f"{key}_count"] = len(value)
                else:
                    compressed_result[key] = value
            # 字典类型 - 检查大小
            elif isinstance(value, dict):
                value_str = str(value)
                if len(value_str) > 500:
                    # 大型字典只保留键名和摘要
                    compressed_result[key] = {
                        "_keys": list(value.keys())[:10],
                        "_summary": f"<dict with {len(value)} keys, {len(value_str)} chars>",
                    }
                else:
                    compressed_result[key] = value
            # 字符串类型 - 截断
            elif isinstance(value, str) and len(value) > 500:
                compressed_result[key] = value[:500] + "..."
            # 其他小型数据 - 保留
            else:
                compressed_result[key] = value

        return compressed_result

    def _summarize_available_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成可用数据摘要

        通用的摘要逻辑，不依赖特定字段名
        """
        available_data = {}

        # 跳过的内部字段
        skip_keys = {"inputs", "control", "last_failure", "_internal"}

        for key, value in state.items():
            if key in skip_keys or key.startswith("_"):
                continue

            # 列表类型 - 显示数量
            if isinstance(value, list):
                if len(value) > 5:
                    available_data[key] = f"{len(value)} items: {value[:3]}..."
                else:
                    available_data[key] = value
            # 字典类型 - 显示键名和大小
            elif isinstance(value, dict):
                value_str = str(value)
                if len(value_str) > 200:
                    available_data[key] = {
                        "_keys": list(value.keys())[:5],
                        "_size": f"{len(value_str)} chars",
                    }
                else:
                    available_data[key] = value
            # 字符串类型 - 截断
            elif isinstance(value, str) and len(value) > 100:
                available_data[key] = value[:100] + "..."
            # 其他类型 - 直接保留
            else:
                available_data[key] = value

        return available_data
