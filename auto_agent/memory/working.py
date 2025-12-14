"""
L1 短时记忆 (Working Memory)

单次 Agent 执行过程中的上下文状态管理
- 当前 Query
- 子任务拆解结果
- 中间决策与工具调用
- 任务结束后被丢弃或提炼到 L2
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from auto_agent.memory.models import WorkingMemoryItem


class WorkingMemory:
    """
    L1 短时记忆

    生命周期：仅在一次任务内有效
    用途：
    - 保证 Agent 内部推理连续性
    - 为长期记忆提炼提供原材料
    """

    def __init__(self, max_items: int = 100, max_context_chars: int = 8000):
        self._items: List[WorkingMemoryItem] = []
        self._max_items = max_items
        self._max_context_chars = max_context_chars
        self._task_id: Optional[str] = None
        self._query: Optional[str] = None
        self._start_time: Optional[int] = None

    def start_task(self, query: str, task_id: Optional[str] = None) -> str:
        """开始新任务，清空之前的短时记忆"""
        self.clear()
        self._task_id = task_id or str(uuid.uuid4())
        self._query = query
        self._start_time = int(time.time())

        # 记录初始 Query
        self.add("query", query, metadata={"is_initial": True})

        return self._task_id

    def add(
        self,
        item_type: str,
        content: Any,
        step_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkingMemoryItem:
        """添加记忆条目"""
        item = WorkingMemoryItem(
            item_id=f"wm_{len(self._items)}_{uuid.uuid4().hex[:6]}",
            item_type=item_type,
            content=content,
            step_id=step_id,
            metadata=metadata or {},
        )
        self._items.append(item)

        # 超过最大数量时，移除最早的非关键条目
        if len(self._items) > self._max_items:
            self._prune()

        return item

    def add_subtask(self, subtask: Dict[str, Any], step_id: str) -> WorkingMemoryItem:
        """记录子任务"""
        return self.add("subtask", subtask, step_id=step_id)

    def add_decision(self, decision: str, reasoning: str, step_id: Optional[str] = None) -> WorkingMemoryItem:
        """记录决策"""
        return self.add(
            "decision",
            {"decision": decision, "reasoning": reasoning},
            step_id=step_id,
        )

    def add_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        step_id: str,
    ) -> WorkingMemoryItem:
        """记录工具调用"""
        return self.add(
            "tool_call",
            {
                "tool": tool_name,
                "arguments": self._compress_arguments(arguments),
                "result": self._compress_result(result),
                "success": result.get("success", False),
            },
            step_id=step_id,
        )

    def add_result(self, result: Any, step_id: Optional[str] = None) -> WorkingMemoryItem:
        """记录结果"""
        return self.add("result", result, step_id=step_id)

    def get_items(self, item_type: Optional[str] = None) -> List[WorkingMemoryItem]:
        """获取记忆条目"""
        if item_type:
            return [item for item in self._items if item.item_type == item_type]
        return self._items.copy()

    def get_recent(self, n: int = 10) -> List[WorkingMemoryItem]:
        """获取最近 N 条记忆"""
        return self._items[-n:]

    def get_by_step(self, step_id: str) -> List[WorkingMemoryItem]:
        """获取指定步骤的记忆"""
        return [item for item in self._items if item.step_id == step_id]

    def clear(self):
        """清空短时记忆"""
        self._items.clear()
        self._task_id = None
        self._query = None
        self._start_time = None

    def to_context_string(self, max_chars: Optional[int] = None) -> str:
        """
        转换为上下文字符串（供 LLM 使用）

        智能压缩，优先保留：
        1. 初始 Query
        2. 最近的工具调用结果
        3. 关键决策
        """
        max_chars = max_chars or self._max_context_chars

        lines = []
        if self._query:
            lines.append(f"【用户查询】{self._query}")

        # 按类型分组
        tool_calls = [i for i in self._items if i.item_type == "tool_call"]
        decisions = [i for i in self._items if i.item_type == "decision"]

        # 添加工具调用摘要
        if tool_calls:
            lines.append("\n【执行历史】")
            for tc in tool_calls[-5:]:  # 最近 5 个
                content = tc.content
                status = "✓" if content.get("success") else "✗"
                lines.append(f"  {status} {content.get('tool')}: {self._summarize(content.get('result'))}")

        # 添加决策
        if decisions:
            lines.append("\n【关键决策】")
            for d in decisions[-3:]:  # 最近 3 个
                lines.append(f"  - {d.content.get('decision')}")

        result = "\n".join(lines)

        # 截断
        if len(result) > max_chars:
            result = result[: max_chars - 3] + "..."

        return result

    def extract_for_long_term(self) -> List[Dict[str, Any]]:
        """
        提取可转化为长期记忆的内容

        返回潜在的 L2 记忆候选
        """
        candidates = []

        # 提取成功的策略
        successful_tools = [
            i for i in self._items if i.item_type == "tool_call" and i.content.get("success")
        ]

        if successful_tools:
            # 提取成功的工具链
            tool_chain = [tc.content.get("tool") for tc in successful_tools]
            candidates.append({
                "type": "strategy",
                "content": f"成功执行工具链: {' -> '.join(tool_chain)}",
                "category": "strategy",
                "source": "task_result",
            })

        # 提取失败的经验
        failed_tools = [
            i for i in self._items if i.item_type == "tool_call" and not i.content.get("success")
        ]

        for ft in failed_tools:
            error = ft.content.get("result", {}).get("error", "未知错误")
            candidates.append({
                "type": "strategy",
                "content": f"工具 {ft.content.get('tool')} 失败: {error}",
                "category": "strategy",
                "source": "task_result",
                "is_negative": True,
            })

        return candidates

    def _prune(self):
        """修剪记忆，保留关键条目"""
        # 保留初始 Query
        initial = [i for i in self._items if i.metadata.get("is_initial")]
        # 保留最近的条目
        recent = self._items[-self._max_items // 2 :]
        # 合并去重
        kept_ids = {i.item_id for i in initial + recent}
        self._items = [i for i in self._items if i.item_id in kept_ids]

    def _compress_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """压缩参数"""
        compressed = {}
        for k, v in arguments.items():
            if isinstance(v, list) and len(v) > 5:
                compressed[k] = f"[{len(v)} items]"
            elif isinstance(v, str) and len(v) > 200:
                compressed[k] = v[:200] + "..."
            else:
                compressed[k] = v
        return compressed

    def _compress_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """压缩结果"""
        compressed = {"success": result.get("success", False)}

        if result.get("error"):
            compressed["error"] = str(result["error"])[:200]

        # 保留关键字段
        for key in ["count", "total", "document_ids", "outline"]:
            if key in result:
                value = result[key]
                if isinstance(value, list) and len(value) > 10:
                    compressed[key] = value[:10]
                else:
                    compressed[key] = value

        return compressed

    def _summarize(self, data: Any, max_len: int = 100) -> str:
        """生成摘要"""
        if data is None:
            return "无"
        if isinstance(data, dict):
            if "error" in data:
                return f"错误: {data['error'][:50]}"
            if "count" in data:
                return f"{data['count']} 条结果"
            return json.dumps(data, ensure_ascii=False)[:max_len]
        return str(data)[:max_len]

    @property
    def task_id(self) -> Optional[str]:
        return self._task_id

    @property
    def query(self) -> Optional[str]:
        return self._query

    @property
    def duration(self) -> Optional[int]:
        """任务持续时间（秒）"""
        if self._start_time:
            return int(time.time()) - self._start_time
        return None
