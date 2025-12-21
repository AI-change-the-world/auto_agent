"""
ExecutionContext - Agent 执行上下文（整合 Memory 系统）

核心设计：
- 内置 WorkingMemory (L1) 管理当前执行的短期记忆
- 可选关联 MemorySystem 访问 L2/L3 长期记忆
- 执行结束时自动提炼有价值内容到长期记忆
- 完全不硬编码任何参数映射规则
- 新增：跨步骤工作记忆（设计决策、约束、待办）
"""

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from auto_agent.memory.system import MemorySystem


# ==================== 工作记忆数据结构 ====================


@dataclass
class DesignDecision:
    """设计决策"""

    decision: str  # 决策内容
    reason: str  # 决策理由
    step_id: str  # 产生决策的步骤
    timestamp: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)  # 相关标签

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "step_id": self.step_id,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


@dataclass
class Constraint:
    """约束条件"""

    constraint: str  # 约束内容
    source: str  # 约束来源（步骤ID或"user"）
    scope: str = "global"  # 作用范围: "global" / "module:xxx" / "file:xxx"
    priority: str = "normal"  # 优先级: "critical" / "high" / "normal" / "low"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraint": self.constraint,
            "source": self.source,
            "scope": self.scope,
            "priority": self.priority,
            "timestamp": self.timestamp,
        }


@dataclass
class TodoItem:
    """待办事项"""

    todo: str  # 待办内容
    created_by: str  # 创建步骤ID
    target_step: Optional[str] = None  # 目标步骤（如果有）
    priority: str = "normal"  # 优先级
    completed: bool = False
    completed_by: Optional[str] = None  # 完成步骤ID
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "todo": self.todo,
            "created_by": self.created_by,
            "target_step": self.target_step,
            "priority": self.priority,
            "completed": self.completed,
            "completed_by": self.completed_by,
            "timestamp": self.timestamp,
        }


@dataclass
class InterfaceDefinition:
    """接口/契约定义"""

    name: str  # 接口名称
    definition: Dict[str, Any]  # 接口定义（如函数签名、API schema）
    defined_by: str  # 定义步骤ID
    interface_type: str = "function"  # 类型: "function" / "api" / "schema" / "config"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "definition": self.definition,
            "defined_by": self.defined_by,
            "interface_type": self.interface_type,
            "timestamp": self.timestamp,
        }


class CrossStepWorkingMemory:
    """
    跨步骤工作记忆

    存储跨步骤的决策、约束、待办，让后续步骤能看到全局上下文
    """

    def __init__(self):
        self.design_decisions: List[DesignDecision] = []
        self.constraints: List[Constraint] = []
        self.todos: List[TodoItem] = []
        self.interfaces: Dict[str, InterfaceDefinition] = {}
        self.dependencies: Dict[str, List[str]] = {}  # {file: [依赖的文件]}

    def add_decision(
        self,
        decision: str,
        reason: str,
        step_id: str,
        tags: Optional[List[str]] = None,
    ):
        """添加设计决策"""
        self.design_decisions.append(
            DesignDecision(
                decision=decision,
                reason=reason,
                step_id=step_id,
                tags=tags or [],
            )
        )

    def add_constraint(
        self,
        constraint: str,
        source: str,
        scope: str = "global",
        priority: str = "normal",
    ):
        """添加约束条件"""
        self.constraints.append(
            Constraint(
                constraint=constraint,
                source=source,
                scope=scope,
                priority=priority,
            )
        )

    def add_todo(
        self,
        todo: str,
        created_by: str,
        target_step: Optional[str] = None,
        priority: str = "normal",
    ):
        """添加待办事项"""
        self.todos.append(
            TodoItem(
                todo=todo,
                created_by=created_by,
                target_step=target_step,
                priority=priority,
            )
        )

    def complete_todo(self, todo_index: int, completed_by: str):
        """完成待办事项"""
        if 0 <= todo_index < len(self.todos):
            self.todos[todo_index].completed = True
            self.todos[todo_index].completed_by = completed_by

    def add_interface(
        self,
        name: str,
        definition: Dict[str, Any],
        defined_by: str,
        interface_type: str = "function",
    ):
        """添加接口定义"""
        self.interfaces[name] = InterfaceDefinition(
            name=name,
            definition=definition,
            defined_by=defined_by,
            interface_type=interface_type,
        )

    def add_dependency(self, file: str, depends_on: List[str]):
        """添加文件依赖关系"""
        if file not in self.dependencies:
            self.dependencies[file] = []
        for dep in depends_on:
            if dep not in self.dependencies[file]:
                self.dependencies[file].append(dep)

    def get_pending_todos(self) -> List[TodoItem]:
        """获取未完成的待办事项"""
        return [t for t in self.todos if not t.completed]

    def get_relevant_context(
        self,
        current_step_description: str,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        获取与当前步骤相关的工作记忆上下文

        Args:
            current_step_description: 当前步骤描述
            tags: 相关标签（用于过滤）

        Returns:
            格式化的上下文字符串
        """
        parts = []

        # 设计决策
        if self.design_decisions:
            decisions_text = []
            for d in self.design_decisions[-10:]:  # 最近 10 个
                decisions_text.append(f"- {d.decision} (理由: {d.reason})")
            if decisions_text:
                parts.append("【已做出的设计决策】\n" + "\n".join(decisions_text))

        # 约束条件
        if self.constraints:
            # 按优先级排序
            priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
            sorted_constraints = sorted(
                self.constraints, key=lambda c: priority_order.get(c.priority, 2)
            )
            constraints_text = []
            for c in sorted_constraints[:10]:
                prefix = "⚠️" if c.priority in ["critical", "high"] else "-"
                constraints_text.append(f"{prefix} {c.constraint}")
            if constraints_text:
                parts.append("【必须遵守的约束】\n" + "\n".join(constraints_text))

        # 待办事项
        pending = self.get_pending_todos()
        if pending:
            todos_text = []
            for t in pending[:5]:
                todos_text.append(f"- {t.todo}")
            if todos_text:
                parts.append("【待处理事项】\n" + "\n".join(todos_text))

        # 接口定义
        if self.interfaces:
            interfaces_text = []
            for name, iface in list(self.interfaces.items())[:5]:
                interfaces_text.append(f"- {name} ({iface.interface_type})")
            if interfaces_text:
                parts.append("【已定义的接口】\n" + "\n".join(interfaces_text))

        return "\n\n".join(parts) if parts else ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于持久化）"""
        return {
            "design_decisions": [d.to_dict() for d in self.design_decisions],
            "constraints": [c.to_dict() for c in self.constraints],
            "todos": [t.to_dict() for t in self.todos],
            "interfaces": {k: v.to_dict() for k, v in self.interfaces.items()},
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossStepWorkingMemory":
        """从字典恢复（用于持久化）"""
        wm = cls()

        for d in data.get("design_decisions", []):
            wm.design_decisions.append(
                DesignDecision(
                    decision=d["decision"],
                    reason=d["reason"],
                    step_id=d["step_id"],
                    timestamp=d.get("timestamp", time.time()),
                    tags=d.get("tags", []),
                )
            )

        for c in data.get("constraints", []):
            wm.constraints.append(
                Constraint(
                    constraint=c["constraint"],
                    source=c["source"],
                    scope=c.get("scope", "global"),
                    priority=c.get("priority", "normal"),
                    timestamp=c.get("timestamp", time.time()),
                )
            )

        for t in data.get("todos", []):
            wm.todos.append(
                TodoItem(
                    todo=t["todo"],
                    created_by=t["created_by"],
                    target_step=t.get("target_step"),
                    priority=t.get("priority", "normal"),
                    completed=t.get("completed", False),
                    completed_by=t.get("completed_by"),
                    timestamp=t.get("timestamp", time.time()),
                )
            )

        for name, iface in data.get("interfaces", {}).items():
            wm.interfaces[name] = InterfaceDefinition(
                name=name,
                definition=iface["definition"],
                defined_by=iface["defined_by"],
                interface_type=iface.get("interface_type", "function"),
                timestamp=iface.get("timestamp", time.time()),
            )

        wm.dependencies = data.get("dependencies", {})

        return wm


# ==================== 一致性检查数据结构（阶段三）====================


@dataclass
class ConsistencyCheckpoint:
    """
    一致性检查点

    记录步骤产出的关键元素，供后续步骤进行一致性检查
    """

    step_id: str  # 产生检查点的步骤 ID
    artifact_type: (
        str  # 产物类型: "code" / "document" / "config" / "interface" / "schema"
    )
    key_elements: Dict[str, Any]  # 关键元素（函数签名、接口定义、配置项等）
    constraints_for_future: List[str]  # 后续步骤必须遵守的约束
    timestamp: float = field(default_factory=time.time)
    description: str = ""  # 检查点描述

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "artifact_type": self.artifact_type,
            "key_elements": self.key_elements,
            "constraints_for_future": self.constraints_for_future,
            "timestamp": self.timestamp,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsistencyCheckpoint":
        return cls(
            step_id=data["step_id"],
            artifact_type=data["artifact_type"],
            key_elements=data.get("key_elements", {}),
            constraints_for_future=data.get("constraints_for_future", []),
            timestamp=data.get("timestamp", time.time()),
            description=data.get("description", ""),
        )


@dataclass
class ConsistencyViolation:
    """一致性违规"""

    checkpoint_id: str  # 违反的检查点步骤 ID
    current_step_id: str  # 当前步骤 ID
    violation_type: str  # 违规类型: "interface_mismatch" / "naming_conflict" / "constraint_violation"
    severity: str  # 严重程度: "critical" / "warning" / "info"
    description: str  # 违规描述
    suggestion: str = ""  # 修正建议

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "current_step_id": self.current_step_id,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "description": self.description,
            "suggestion": self.suggestion,
        }


class GlobalConsistencyChecker:
    """
    全局一致性检查器

    功能：
    - 注册步骤产出的检查点
    - 检查当前步骤与历史检查点的一致性
    - 返回违规列表
    """

    def __init__(self):
        self.checkpoints: Dict[str, ConsistencyCheckpoint] = {}  # step_id -> checkpoint
        self.violations: List[ConsistencyViolation] = []

    def register_checkpoint(
        self,
        step_id: str,
        artifact_type: str,
        key_elements: Dict[str, Any],
        constraints_for_future: Optional[List[str]] = None,
        description: str = "",
    ) -> ConsistencyCheckpoint:
        """
        注册检查点

        Args:
            step_id: 步骤 ID
            artifact_type: 产物类型
            key_elements: 关键元素
            constraints_for_future: 后续约束
            description: 描述

        Returns:
            创建的检查点
        """
        checkpoint = ConsistencyCheckpoint(
            step_id=step_id,
            artifact_type=artifact_type,
            key_elements=key_elements,
            constraints_for_future=constraints_for_future or [],
            description=description,
        )
        self.checkpoints[step_id] = checkpoint
        return checkpoint

    def get_relevant_checkpoints(
        self,
        artifact_types: Optional[List[str]] = None,
    ) -> List[ConsistencyCheckpoint]:
        """
        获取相关的检查点

        Args:
            artifact_types: 过滤的产物类型（可选）

        Returns:
            检查点列表
        """
        checkpoints = list(self.checkpoints.values())
        if artifact_types:
            checkpoints = [c for c in checkpoints if c.artifact_type in artifact_types]
        return checkpoints

    def get_all_constraints(self) -> List[str]:
        """获取所有检查点的约束"""
        constraints = []
        for cp in self.checkpoints.values():
            constraints.extend(cp.constraints_for_future)
        return constraints

    def add_violation(
        self,
        checkpoint_id: str,
        current_step_id: str,
        violation_type: str,
        severity: str,
        description: str,
        suggestion: str = "",
    ) -> ConsistencyViolation:
        """添加违规记录"""
        violation = ConsistencyViolation(
            checkpoint_id=checkpoint_id,
            current_step_id=current_step_id,
            violation_type=violation_type,
            severity=severity,
            description=description,
            suggestion=suggestion,
        )
        self.violations.append(violation)
        return violation

    def get_violations(
        self,
        severity: Optional[str] = None,
    ) -> List[ConsistencyViolation]:
        """获取违规列表"""
        if severity:
            return [v for v in self.violations if v.severity == severity]
        return self.violations

    def has_critical_violations(self) -> bool:
        """是否有严重违规"""
        return any(v.severity == "critical" for v in self.violations)

    def clear_violations(self):
        """清除违规记录"""
        self.violations = []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于持久化）"""
        return {
            "checkpoints": {k: v.to_dict() for k, v in self.checkpoints.items()},
            "violations": [v.to_dict() for v in self.violations],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalConsistencyChecker":
        """从字典恢复"""
        checker = cls()
        for step_id, cp_data in data.get("checkpoints", {}).items():
            checker.checkpoints[step_id] = ConsistencyCheckpoint.from_dict(cp_data)
        for v_data in data.get("violations", []):
            checker.violations.append(
                ConsistencyViolation(
                    checkpoint_id=v_data["checkpoint_id"],
                    current_step_id=v_data["current_step_id"],
                    violation_type=v_data["violation_type"],
                    severity=v_data["severity"],
                    description=v_data["description"],
                    suggestion=v_data.get("suggestion", ""),
                )
            )
        return checker

    def get_context_for_llm(self) -> str:
        """
        生成供 LLM 使用的一致性上下文

        Returns:
            格式化的上下文字符串
        """
        if not self.checkpoints:
            return ""

        parts = ["【已注册的一致性检查点】"]

        for step_id, cp in self.checkpoints.items():
            parts.append(f"\n[{cp.artifact_type}] {cp.description or step_id}")

            # 关键元素摘要
            if cp.key_elements:
                elements_str = json.dumps(cp.key_elements, ensure_ascii=False)
                if len(elements_str) > 200:
                    elements_str = elements_str[:200] + "..."
                parts.append(f"  关键元素: {elements_str}")

            # 约束
            if cp.constraints_for_future:
                for constraint in cp.constraints_for_future[:3]:
                    parts.append(f"  ⚠️ 约束: {constraint}")

        return "\n".join(parts)


@dataclass
class StepRecord:
    """
    步骤执行记录（增强版）

    新增结构化字段用于 LLM 语义理解：
    - target: 这一步的目标
    - semantic_description: 对结果的语义描述（供 LLM 判断参数关联）
    - input_summary: 输入数据摘要
    - output_summary: 输出数据摘要
    """

    step_id: str
    step_num: int
    tool_name: str
    description: str  # 步骤描述（来自计划）
    arguments: Dict[str, Any]
    output: Dict[str, Any]
    success: bool
    error: Optional[str] = None

    # 新增：结构化语义字段
    target: str = ""  # 这一步的目标，如 "查找相关文档"
    semantic_description: str = ""  # 语义描述，如 "找到了3个文档，相关性0.9/0.8/0.7"
    input_summary: Dict[str, Any] = field(
        default_factory=dict
    )  # {"type": "list", "keys": [...]}
    output_summary: Dict[str, Any] = field(
        default_factory=dict
    )  # {"type": "dict", "keys": [...]}

    def to_semantic_dict(self) -> Dict[str, Any]:
        """转换为语义字典（供 LLM 参数映射使用）"""
        return {
            "step_id": self.step_id,
            "step_num": self.step_num,
            "tool": self.tool_name,
            "target": self.target or self.description,
            "description": self.semantic_description
            or f"{'成功' if self.success else '失败'}: {self.description}",
            "input": self.input_summary,
            "output": self.output_summary,
            "success": self.success,
            "error": self.error,
        }

    def to_llm_summary(self) -> str:
        """生成供 LLM 理解的单行摘要"""
        status = "✓" if self.success else "✗"
        desc = self.semantic_description or self.description
        return f"步骤{self.step_num}[{self.tool_name}] {status}: {desc}"


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

        # 跨步骤工作记忆（阶段二新增）
        self.working_memory = CrossStepWorkingMemory()

        # 全局一致性检查器（阶段三新增）
        self.consistency_checker = GlobalConsistencyChecker()

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
        target: Optional[str] = None,
        semantic_description: Optional[str] = None,
    ):
        """
        记录步骤执行结果（增强版）

        Args:
            step_id: 步骤 ID
            step_num: 步骤序号
            tool_name: 工具名称
            description: 步骤描述（来自计划）
            arguments: 工具参数
            output: 工具输出
            success: 是否成功
            error: 错误信息
            target: 这一步的目标（可选，默认使用 description）
            semantic_description: 语义描述（可选，自动生成）
        """
        # 生成输入/输出摘要
        input_summary = self._generate_data_summary(arguments, "input")
        output_summary = self._generate_data_summary(output, "output")

        # 自动生成语义描述（如果未提供）
        if not semantic_description:
            semantic_description = self._generate_semantic_description(
                tool_name, arguments, output, success, error
            )

        record = StepRecord(
            step_id=step_id,
            step_num=step_num,
            tool_name=tool_name,
            description=description,
            arguments=arguments,
            output=output,
            success=success,
            error=error,
            target=target or description,
            semantic_description=semantic_description,
            input_summary=input_summary,
            output_summary=output_summary,
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

    def _generate_data_summary(self, data: Any, data_type: str) -> Dict[str, Any]:
        """
        生成数据摘要（用于 LLM 理解数据结构）

        Args:
            data: 原始数据
            data_type: 数据类型标识（input/output）

        Returns:
            结构化摘要，如 {"type": "dict", "keys": ["docs", "scores"], "sample": {...}}
        """
        if data is None:
            return {"type": "null", "value": None}

        if isinstance(data, dict):
            keys = list(data.keys())
            summary = {
                "type": "dict",
                "keys": keys[:20],  # 最多 20 个 key
                "key_count": len(keys),
            }
            # 添加关键字段的值预览
            preview = {}
            for k in keys[:5]:
                v = data[k]
                if isinstance(v, (str, int, float, bool)):
                    preview[k] = v if len(str(v)) < 100 else str(v)[:100] + "..."
                elif isinstance(v, list):
                    preview[k] = f"[{len(v)} items]"
                elif isinstance(v, dict):
                    preview[k] = f"{{...{len(v)} keys}}"
            summary["preview"] = preview
            return summary

        if isinstance(data, list):
            summary = {
                "type": "list",
                "length": len(data),
            }
            # 分析列表元素类型
            if data:
                first = data[0]
                if isinstance(first, dict):
                    summary["item_type"] = "dict"
                    summary["item_keys"] = list(first.keys())[:10]
                elif isinstance(first, (str, int, float)):
                    summary["item_type"] = type(first).__name__
                    summary["sample"] = data[:3]
            return summary

        if isinstance(data, str):
            return {
                "type": "string",
                "length": len(data),
                "preview": data[:200] + "..." if len(data) > 200 else data,
            }

        return {"type": type(data).__name__, "value": str(data)[:100]}

    def _generate_semantic_description(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        output: Dict[str, Any],
        success: bool,
        error: Optional[str],
    ) -> str:
        """
        自动生成语义描述（供 LLM 理解步骤结果）

        这个描述会被用于后续步骤的参数映射判断
        """
        if not success:
            return f"执行失败: {error or '未知错误'}"

        if not output:
            return "执行成功，无输出数据"

        # 根据输出结构生成描述
        parts = []

        # 检查常见的输出字段
        if isinstance(output, dict):
            # 文档相关
            if "documents" in output or "docs" in output:
                docs = output.get("documents") or output.get("docs") or []
                if isinstance(docs, list):
                    parts.append(f"返回了 {len(docs)} 个文档")

            # 搜索结果
            if "results" in output:
                results = output["results"]
                if isinstance(results, list):
                    parts.append(f"找到 {len(results)} 条结果")

            # 生成内容
            if "content" in output:
                content = output["content"]
                if isinstance(content, str):
                    parts.append(f"生成了 {len(content)} 字符的内容")

            # 大纲
            if "outline" in output:
                outline = output["outline"]
                if isinstance(outline, list):
                    parts.append(f"生成了 {len(outline)} 项大纲")

            # 查询
            if "queries" in output or "search_queries" in output:
                queries = output.get("queries") or output.get("search_queries") or []
                if isinstance(queries, list):
                    parts.append(f"生成了 {len(queries)} 个查询")

            # 通用：列出主要输出字段
            if not parts:
                keys = [
                    k
                    for k in output.keys()
                    if k not in ("success", "error", "metadata")
                ]
                if keys:
                    parts.append(f"输出字段: {', '.join(keys[:5])}")

        return "; ".join(parts) if parts else "执行成功"

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
        recent = (
            self._history[-max_steps:]
            if len(self._history) > max_steps
            else self._history
        )

        lines = []
        for record in recent:
            status = "✓" if record.success else "✗"
            output_preview = str(record.output)[:200] if record.output else "无"
            lines.append(
                f"步骤{record.step_num}. [{status}] {record.tool_name}: {record.description}\n"
                f"   输出: {output_preview}"
            )

        return "\n".join(lines)

    def get_semantic_history(self, max_steps: int = 10) -> List[Dict[str, Any]]:
        """
        获取语义化的执行历史（供 LLM 参数映射使用）

        返回结构化的步骤信息，包含：
        - target: 步骤目标
        - description: 语义描述
        - input/output: 数据摘要

        Args:
            max_steps: 最大返回步骤数

        Returns:
            语义化的步骤列表
        """
        recent = (
            self._history[-max_steps:]
            if len(self._history) > max_steps
            else self._history
        )
        return [record.to_semantic_dict() for record in recent]

    def get_semantic_history_text(self, max_steps: int = 10) -> str:
        """
        获取语义化执行历史的文本格式（供 LLM prompt 使用）

        格式示例：
        步骤1[analyze_input] ✓: 分析用户输入，提取关键词
          目标: 分析用户需求
          输入: {"type": "dict", "keys": ["query"]}
          输出: {"type": "dict", "keys": ["keywords", "intent"]}
        """
        recent = (
            self._history[-max_steps:]
            if len(self._history) > max_steps
            else self._history
        )

        lines = []
        for record in recent:
            semantic = record.to_semantic_dict()
            status = "✓" if record.success else "✗"

            lines.append(
                f"步骤{record.step_num}[{record.tool_name}] {status}: {semantic['description']}"
            )
            lines.append(f"  目标: {semantic['target']}")

            # 简化输入输出显示
            if semantic["input"]:
                input_str = json.dumps(semantic["input"], ensure_ascii=False)
                if len(input_str) > 150:
                    input_str = input_str[:150] + "..."
                lines.append(f"  输入: {input_str}")

            if semantic["output"]:
                output_str = json.dumps(semantic["output"], ensure_ascii=False)
                if len(output_str) > 150:
                    output_str = output_str[:150] + "..."
                lines.append(f"  输出: {output_str}")

            lines.append("")  # 空行分隔

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
            parts.append(
                "【约束】\n" + "\n".join(f"- {c}" for c in self.agent_constraints)
            )

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

        # 跨步骤工作记忆（阶段二新增）
        working_memory_context = self.working_memory.get_relevant_context(
            current_step_description=self.plan_summary
        )
        if working_memory_context:
            parts.append(working_memory_context)

        # 一致性检查点上下文（阶段三新增）
        consistency_context = self.consistency_checker.get_context_for_llm()
        if consistency_context:
            parts.append(consistency_context)

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
