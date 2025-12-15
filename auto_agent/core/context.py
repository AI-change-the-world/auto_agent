"""
ExecutionContext - Agent 执行上下文（整合 Memory 系统）

核心设计：
- 内置 WorkingMemory (L1) 管理当前执行的短期记忆
- 可选关联 MemorySystem 访问 L2/L3 长期记忆
- 执行结束时自动提炼有价值内容到长期记忆
- 完全不硬编码任何参数映射规则
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from auto_agent.memory.system import MemorySystem


@dataclass
class StepRecord:
    """步骤执行记录"""
    step_id: str
    step_num: int
    tool_name: str
    description: str
    arguments: Dict[str, Any]
    output: Dict[str, Any]
    success: bool
    error: Optional[str] = None


class ExecutionContext:
    """
    Agent 执行上下文（整合 Memory 系统）
    
    功能：
    - 管理当前执行状态 (state dict)
    - 内置 WorkingMemory (L1) 记录执行历史
    - 可选关联 MemorySystem 访问长期记忆
    - 为 LLM 生成上下文摘要
    - 执行结束时提炼记忆
    """
    
    def __init__(
        self,
        query: str,
        user_id: str = "default",
        plan_summary: str = "",
        state: Optional[Dict[str, Any]] = None,
        agent_name: str = "",
        agent_description: str = "",
        agent_goals: Optional[List[str]] = None,
        agent_constraints: Optional[List[str]] = None,
        memory_system: Optional["MemorySystem"] = None,
        extensions: Optional[Dict[str, Any]] = None,
    ):
        # 用户信息
        self.user_id = user_id
        self.query = query
        
        # Agent 元信息
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.agent_goals = agent_goals or []
        self.agent_constraints = agent_constraints or []
        
        # 执行计划
        self.plan_summary = plan_summary
        self.total_steps = 0
        self.current_step = 0
        
        # 状态字典
        self.state = state or {}
        
        # 扩展数据（不发送给 LLM，用于存储数据库连接等）
        self.extensions = extensions or {}
        
        # Memory 系统
        self._memory_system = memory_system
        self._task_id: Optional[str] = None
        
        # 执行历史（内置 L1 短期记忆）
        self._history: List[StepRecord] = []
        
        # 初始化 WorkingMemory
        if self._memory_system:
            self._task_id = self._memory_system.start_task(user_id, query)
    
    # ==================== 执行历史管理 ====================
    
    @property
    def history(self) -> List[StepRecord]:
        """获取执行历史"""
        return self._history
    
    def record_step(
        self,
        step_id: str,
        step_num: int,
        tool_name: str,
        description: str,
        arguments: Dict[str, Any],
        output: Dict[str, Any],
        success: bool,
        error: Optional[str] = None,
    ):
        """记录步骤执行结果"""
        record = StepRecord(
            step_id=step_id,
            step_num=step_num,
            tool_name=tool_name,
            description=description,
            arguments=arguments,
            output=output,
            success=success,
            error=error,
        )
        self._history.append(record)
        self.current_step = step_num
        
        # 同步到 WorkingMemory
        if self._memory_system and self._task_id:
            wm = self._memory_system.get_working_memory(self._task_id)
            wm.add_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                result=output,
                step_id=step_id,
            )
    
    def get_last_output(self, key: Optional[str] = None) -> Any:
        """获取上一步的输出（或指定字段）"""
        if not self._history:
            return None
        last = self._history[-1]
        if key:
            return last.output.get(key) if last.output else None
        return last.output
    
    # ==================== Memory 系统集成 ====================
    
    def get_relevant_memories(self, limit: int = 5) -> str:
        """获取与当前查询相关的长期记忆"""
        if not self._memory_system:
            return ""
        
        # 从 L2 搜索相关记忆
        memories = self._memory_system.search_memory(
            user_id=self.user_id,
            query=self.query,
            limit=limit,
        )
        
        if not memories:
            return ""
        
        lines = ["【相关记忆】"]
        for m in memories:
            lines.append(f"- [{m.category.value}] {m.content}")
        
        return "\n".join(lines)
    
    def get_user_preferences(self) -> str:
        """获取用户偏好"""
        if not self._memory_system:
            return ""
        
        from auto_agent.memory.models import MemoryCategory
        
        prefs = self._memory_system.semantic.get_by_category(
            self.user_id,
            MemoryCategory.PREFERENCE,
            limit=5,
        )
        
        if not prefs:
            return ""
        
        lines = ["【用户偏好】"]
        for p in prefs:
            lines.append(f"- {p.content}")
        
        return "\n".join(lines)
    
    def add_memory(
        self,
        content: str,
        category: str = "custom",
        tags: Optional[List[str]] = None,
    ):
        """添加长期记忆"""
        if not self._memory_system:
            return
        
        from auto_agent.memory.models import MemoryCategory, MemorySource
        
        self._memory_system.add_memory(
            user_id=self.user_id,
            content=content,
            category=MemoryCategory(category),
            tags=tags,
            source=MemorySource.TASK_RESULT,
        )
    
    def end_task(self, promote_to_long_term: bool = False):
        """
        结束任务
        
        Args:
            promote_to_long_term: 是否提炼到长期记忆（默认 False）
        
        注意：
        - 默认不自动提炼执行历史到 L2 长期记忆
        - 执行历史应该保留在应用层（如 DocHive）的执行记录中
        - L2 记忆应该是可复用的策略/知识，而不是执行日志
        """
        if self._memory_system and self._task_id:
            self._memory_system.end_task(
                user_id=self.user_id,
                task_id=self._task_id,
                promote_to_long_term=promote_to_long_term,
            )
    
    # ==================== 上下文生成 ====================
    
    def get_state_summary(self, max_chars: int = 4000) -> str:
        """获取状态摘要（供 LLM 使用）"""
        summary = {}
        for key, value in self.state.items():
            if key == "control":
                continue
            if isinstance(value, list):
                if len(value) > 5:
                    summary[key] = f"[{len(value)} items, first 3: {value[:3]}]"
                else:
                    summary[key] = value
            elif isinstance(value, dict):
                if len(str(value)) > 500:
                    summary[key] = f"{{...{len(value)} keys}}"
                else:
                    summary[key] = value
            elif isinstance(value, str) and len(value) > 500:
                summary[key] = value[:500] + "..."
            else:
                summary[key] = value
        
        result = json.dumps(summary, ensure_ascii=False, indent=2)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n..."
        return result
    
    def get_history_summary(self, max_steps: int = 10) -> str:
        """获取执行历史摘要（供 LLM 使用）"""
        recent = self._history[-max_steps:] if len(self._history) > max_steps else self._history
        
        lines = []
        for record in recent:
            status = "✓" if record.success else "✗"
            output_preview = str(record.output)[:200] if record.output else "无"
            lines.append(
                f"步骤{record.step_num}. [{status}] {record.tool_name}: {record.description}\n"
                f"   输出: {output_preview}"
            )
        
        return "\n".join(lines)
    
    def to_llm_context(self, include_memories: bool = True) -> str:
        """生成发送给 LLM 的完整上下文"""
        parts = []
        
        # Agent 信息
        if self.agent_name:
            parts.append(f"【Agent】{self.agent_name}")
        if self.agent_description:
            parts.append(f"【任务描述】{self.agent_description}")
        if self.agent_goals:
            parts.append("【目标】\n" + "\n".join(f"- {g}" for g in self.agent_goals))
        if self.agent_constraints:
            parts.append("【约束】\n" + "\n".join(f"- {c}" for c in self.agent_constraints))
        
        # 用户输入
        parts.append(f"【用户输入】\n{self.query}")
        
        # 长期记忆（如果启用）
        if include_memories:
            memories = self.get_relevant_memories()
            if memories:
                parts.append(memories)
            
            prefs = self.get_user_preferences()
            if prefs:
                parts.append(prefs)
        
        # 执行计划
        if self.plan_summary:
            parts.append(f"【执行计划】\n{self.plan_summary}")
        
        # 进度
        if self.total_steps > 0:
            parts.append(f"【进度】{self.current_step}/{self.total_steps}")
        
        # 当前状态
        state_summary = self.get_state_summary()
        if state_summary and state_summary != "{}":
            parts.append(f"【当前状态】\n{state_summary}")
        
        # 执行历史
        if self._history:
            parts.append(f"【执行历史】\n{self.get_history_summary()}")
        
        return "\n\n".join(parts)
    
    def build_step_context(
        self,
        step_num: int,
        tool_name: str,
        tool_description: str,
        tool_params: List[Dict[str, Any]],
        step_description: str,
    ) -> str:
        """构建单个步骤的 LLM 上下文（用于智能参数构造）"""
        parts = [self.to_llm_context()]
        
        parts.append(f"""【当前步骤】
步骤 {step_num}: {step_description}
工具: {tool_name}
工具说明: {tool_description}

【工具参数】
{json.dumps(tool_params, ensure_ascii=False, indent=2)}""")
        
        return "\n\n".join(parts)
