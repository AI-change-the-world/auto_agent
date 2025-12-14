"""
ExecutionContext - Agent 执行上下文

核心思想：
- 维护整个执行过程的状态
- 每次执行步骤前，将上下文发给 LLM 让其智能构造参数
- 每次步骤执行后，让 LLM 决定如何更新状态
- 完全不硬编码任何参数映射规则

使用方式：
1. 创建 ExecutionContext，传入用户输入和 Agent 信息
2. 执行每个步骤前，调用 build_step_context() 获取 LLM 上下文
3. 执行步骤后，调用 record_step() 记录执行结果
4. 状态自动维护在 context.state 中
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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


@dataclass
class ExecutionContext:
    """
    Agent 执行上下文
    
    包含：
    - 用户输入
    - 执行计划
    - 当前状态（key-value 存储）
    - 执行历史
    - 自定义扩展数据（如数据库连接、ES 客户端等）
    """
    
    # 用户输入
    query: str
    
    # 执行计划摘要（供 LLM 参考）
    plan_summary: str = ""
    
    # 当前状态（LLM 可读写）
    state: Dict[str, Any] = field(default_factory=dict)
    
    # 执行历史
    history: List[StepRecord] = field(default_factory=list)
    
    # 自定义扩展数据（不发送给 LLM，用于存储数据库连接等）
    extensions: Dict[str, Any] = field(default_factory=dict)
    
    # Agent 元信息
    agent_name: str = ""
    agent_description: str = ""
    agent_goals: List[str] = field(default_factory=list)
    agent_constraints: List[str] = field(default_factory=list)
    
    # 当前步骤索引
    current_step: int = 0
    total_steps: int = 0
    
    def add_step_record(self, record: StepRecord):
        """添加步骤执行记录"""
        self.history.append(record)
    
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
        """记录步骤执行结果（便捷方法）"""
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
        self.history.append(record)
        self.current_step = step_num
    
    def get_state_summary(self, max_chars: int = 4000) -> str:
        """获取状态摘要（供 LLM 使用）"""
        summary = {}
        for key, value in self.state.items():
            if key == "control":
                continue  # 跳过控制字段
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
        recent = self.history[-max_steps:] if len(self.history) > max_steps else self.history
        
        lines = []
        for record in recent:
            status = "✓" if record.success else "✗"
            output_preview = str(record.output)[:200] if record.output else "无"
            lines.append(
                f"步骤{record.step_num}. [{status}] {record.tool_name}: {record.description}\n"
                f"   输出: {output_preview}"
            )
        
        return "\n".join(lines)
    
    def get_last_output(self, key: Optional[str] = None) -> Any:
        """获取上一步的输出（或指定字段）"""
        if not self.history:
            return None
        last = self.history[-1]
        if key:
            return last.output.get(key) if last.output else None
        return last.output
    
    def to_llm_context(self) -> str:
        """生成发送给 LLM 的上下文描述"""
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
        if self.history:
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
        """
        构建单个步骤的 LLM 上下文
        
        用于让 LLM 智能构造参数
        """
        parts = [self.to_llm_context()]
        
        parts.append(f"""【当前步骤】
步骤 {step_num}: {step_description}
工具: {tool_name}
工具说明: {tool_description}

【工具参数】
{json.dumps(tool_params, ensure_ascii=False, indent=2)}""")
        
        return "\n\n".join(parts)
