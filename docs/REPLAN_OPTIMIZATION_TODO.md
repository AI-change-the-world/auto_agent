# Auto-Agent 跨步骤智能规划优化 TODO

## 背景问题

当前框架的 replan 机制是**被动触发**的（连续失败3次、循环执行才触发），缺乏真正的跨步骤全局视野，导致：
- 写了 A 模块，忘了更新 B 模块的引用
- 生成了大纲，但后续内容偏离了大纲
- 前面定义了接口，后面实现时参数不一致

---

## 优化清单

### 阶段一：任务复杂度分级（优先级：高）✅ 已完成

> 目标：在入口处识别任务复杂度，决定后续执行策略

- [x] **1.1 定义任务复杂度枚举** ✅
  - `SIMPLE`: 单步或线性任务（查天气、算数）
  - `MODERATE`: 多步但独立（搜索+总结）
  - `COMPLEX`: 多步且有依赖（研究报告）
  - `PROJECT`: 项目级（写完整项目、重构代码库）
  - 📍 实现位置: `auto_agent/models.py` - `TaskComplexity`

- [x] **1.2 定义 TaskProfile 数据结构** ✅
  - 📍 实现位置: `auto_agent/models.py` - `TaskProfile`

- [x] **1.3 实现意图分类器** ✅
  - 在 `TaskPlanner.plan()` 入口处调用
  - 使用 LLM 分析用户输入，返回 TaskProfile
  - 📍 实现位置: `auto_agent/core/planner.py` - `classify_task_complexity()`

- [x] **1.4 定义 ExecutionStrategy（全局策略）** ✅
  - 📍 实现位置: `auto_agent/models.py` - `ExecutionStrategy`

- [x] **1.5 定义 ToolReplanPolicy（工具级策略）** ✅
  - 📍 实现位置: `auto_agent/models.py` - `ToolReplanPolicy`

- [x] **1.6 在 ToolDefinition 中添加 replan_policy 字段** ✅
  - 📍 实现位置: `auto_agent/models.py` - `ToolDefinition.replan_policy`

- [x] **1.7 实现 `_should_trigger_replan()` 判断逻辑** ✅
  - 优先级：工具级策略 > 全局周期性策略 > 失败触发
  - 简单工具即使到了周期性检查点也跳过
  - 高影响力工具执行后强制检查
  - 📍 实现位置: `auto_agent/core/executor.py` - `_should_trigger_replan()`

- [x] **1.8 策略选择器** ✅
  - 根据 TaskProfile 返回对应的 ExecutionStrategy
  - 📍 实现位置: `auto_agent/core/planner.py` - `get_execution_strategy()`

---

### 阶段二：工作记忆 WorkingMemory（优先级：高）✅ 已完成

> 目标：存储跨步骤的决策、约束、待办，让后续步骤能看到全局上下文

- [x] **2.1 定义 WorkingMemory 数据结构** ✅
  - `DesignDecision`: 设计决策
  - `Constraint`: 约束条件
  - `TodoItem`: 待办事项
  - `InterfaceDefinition`: 接口定义
  - `CrossStepWorkingMemory`: 跨步骤工作记忆管理类
  - 📍 实现位置: `auto_agent/core/context.py`

- [x] **2.2 在 ExecutionContext 中集成 WorkingMemory** ✅
  - 每步执行后，让 LLM 提取决策/约束/待办
  - 存入 WorkingMemory
  - 📍 实现位置: `auto_agent/core/context.py` - `ExecutionContext.working_memory`
  - 📍 提取逻辑: `auto_agent/core/executor.py` - `_extract_working_memory()`

- [x] **2.3 实现 WorkingMemory 的上下文注入** ✅
  - 在 `to_llm_context()` 中注入相关的决策、约束、待办
  - 让 LLM 在构造参数时能看到全局约束
  - 📍 实现位置: `auto_agent/core/context.py` - `CrossStepWorkingMemory.get_relevant_context()`

- [x] **2.4 实现 WorkingMemory 的持久化** ✅
  - 支持保存/加载（用于长任务中断恢复）
  - 📍 实现位置: `auto_agent/core/context.py` - `CrossStepWorkingMemory.to_dict()` / `from_dict()`

---

### 阶段三：全局一致性检查器（优先级：中）✅ 已完成

> 目标：检查当前步骤与历史步骤的语义一致性

- [x] **3.1 定义 ConsistencyCheckpoint** ✅
  - `ConsistencyCheckpoint`: 一致性检查点数据结构
  - `ConsistencyViolation`: 一致性违规数据结构
  - 📍 实现位置: `auto_agent/core/context.py`

- [x] **3.2 实现 GlobalConsistencyChecker** ✅
  - `register_checkpoint()`: 步骤完成后注册检查点
  - `check_consistency()`: 检查当前步骤与历史检查点的一致性
  - `get_relevant_checkpoints()`: 获取相关检查点
  - `add_violation()`: 添加违规记录
  - `get_context_for_llm()`: 生成供 LLM 使用的上下文
  - 📍 实现位置: `auto_agent/core/context.py` - `GlobalConsistencyChecker`

- [x] **3.3 定义触发时机** ✅
  - 高影响力工具执行后自动注册检查点
  - `requires_consistency_check` 策略控制
  - PROJECT 级别任务总是检查
  - 📍 实现位置: `auto_agent/core/executor.py` - `execute_plan_stream()`

- [x] **3.4 一致性违规处理** ✅
  - 轻微违规：记录到 violations 列表
  - 严重违规：发送 `consistency_violation` 事件，可触发重规划
  - 📍 实现位置: `auto_agent/core/executor.py` - `_check_consistency()`

- [x] **3.5 在 ExecutionContext 中集成 ConsistencyChecker** ✅
  - 📍 实现位置: `auto_agent/core/context.py` - `ExecutionContext.consistency_checker`

- [x] **3.6 实现 LLM 驱动的检查点注册和一致性检查** ✅
  - `_register_consistency_checkpoint()`: 使用 LLM 提取关键元素
  - `_check_consistency()`: 使用 LLM 检查一致性
  - 📍 实现位置: `auto_agent/core/executor.py`

---

### 阶段四：增量式重规划（优先级：中）✅ 已完成

> 目标：只调整后续步骤，保留已完成的工作

- [x] **4.1 实现 `_incremental_replan()`** ✅
  - 输入：当前计划、当前步骤索引、问题描述、状态
  - 保留已完成步骤
  - 只重新规划剩余步骤
  - 确保新步骤能利用已完成步骤的产出
  - 📍 实现位置: `auto_agent/core/executor.py` - `_incremental_replan()`

- [x] **4.2 修改现有 `evaluate_and_replan()`** ✅
  - 新增 `current_step_index` 和 `use_incremental` 参数
  - 默认使用增量式重规划
  - 只有严重问题（如循环依赖）才全量重规划
  - 📍 实现位置: `auto_agent/core/executor.py` - `evaluate_and_replan()`

- [x] **4.3 增量重规划的 prompt 设计** ✅
  - 明确告知 LLM 哪些步骤已完成、产出了什么
  - 包含工作记忆和一致性检查点上下文
  - 要求新计划必须基于已有产出
  - 📍 实现位置: `auto_agent/core/executor.py` - `_incremental_replan()` prompt

---

### 阶段五：前瞻性规划（优先级：低）

> 目标：执行前预判当前决策对后续的影响

- [ ] **5.1 实现 `lookahead_check()`**
  - 在执行当前步骤前调用
  - 分析当前步骤的输出是否能满足后续步骤
  - 预判可能的冲突

- [ ] **5.2 定义触发条件**
  - 仅对 PROJECT 级任务启用
  - 或在检测到潜在风险时启用

- [ ] **5.3 前瞻检查的响应**
  - 建议调整当前步骤参数
  - 建议插入缺失的步骤
  - 警告潜在问题

---

### 阶段六：项目级任务的阶段化管理（优先级：低）

> 目标：大型任务分阶段执行，阶段切换时做全面审查

- [ ] **6.1 定义 ProjectPhase**
  ```python
  @dataclass
  class ProjectPhase:
      name: str           # "设计阶段"、"实现阶段"
      goals: List[str]
      deliverables: List[str]
      validation_criteria: List[str]  # 进入下一阶段的条件
  ```

- [ ] **6.2 实现 `plan_project_phases()`**
  - 项目级任务先规划阶段
  - 再规划每个阶段的具体步骤

- [ ] **6.3 阶段切换审查**
  - 检查当前阶段的 deliverables 是否完成
  - 检查 validation_criteria 是否满足
  - 全面一致性检查
  - 必要时重规划下一阶段

---

## 实施顺序建议

```
阶段一（任务分级）✅ ──→ 阶段二（工作记忆）✅ ──→ 阶段三（一致性检查）✅
                                                    │
                                                    ▼
                          阶段四（增量重规划）✅ ←──┘
                                                    │
                                                    ▼
                          阶段五（前瞻规划）+ 阶段六（阶段化管理）
```

**已完成**：
1. ✅ 阶段一（任务分级）- 成本低，收益高，决定后续策略
2. ✅ 阶段二（工作记忆）- 最小改动，最大收益，让 LLM 能看到全局
3. ✅ 阶段三（一致性检查）- 发现接口不一致、命名冲突等问题
4. ✅ 阶段四（增量重规划）- 保留已完成工作，减少重复劳动

**待实现**：
- 阶段五（前瞻规划）- 主要针对 PROJECT 级任务
- 阶段六（阶段化管理）- 大型项目的阶段化执行

---

## 预期收益

| 优化项 | 解决的问题 | 额外成本 |
|--------|-----------|---------|
| 任务分级 | 简单任务不过度消耗，复杂任务不掉以轻心 | 1次LLM调用/任务 |
| 工作记忆 | 后续步骤能看到之前的决策和约束 | 每步1次LLM提取 |
| 一致性检查 | 发现接口不一致、命名冲突等问题 | 关键步骤后1次LLM调用 |
| 增量重规划 | 保留已完成工作，减少重复劳动 | 仅在需要时触发 |
| 前瞻规划 | 提前发现问题，避免返工 | 仅PROJECT级启用 |

---

## 架构重构：统一后处理机制（长期规划）

### 背景

当前 ToolDefinition 中存在多个功能重叠的字段：
- `validate_function`: 验证结果对不对
- `replan_policy`: 判断要不要调整计划
- `compress_function`: 压缩结果
- `error_recovery_strategies`: 错误恢复

这些都是「工具执行后的处理逻辑」，但分散在不同字段，概念边界模糊。

### 目标架构

将所有后处理逻辑统一到 `ToolPostPolicy`：

```python
@dataclass
class ToolPostPolicy:
    """工具执行后的统一策略"""
    
    # === 第一阶段：结果验证 ===
    validation: Optional["ValidationConfig"] = None
    
    # === 第二阶段：通过后的额外检查 ===
    post_success: Optional["PostSuccessConfig"] = None
    
    # === 第三阶段：结果处理 ===
    result_handling: Optional["ResultHandlingConfig"] = None


@dataclass
class ValidationConfig:
    """结果验证配置（整合原 validate_function）"""
    
    # 验证函数: (result, expectations, state, mode) -> (passed, reason)
    validate_function: Optional[Callable] = None
    
    # 验证失败后的动作
    on_fail: str = "retry"  # "retry" / "replan" / "abort" / "continue"
    
    # 最大重试次数（仅 on_fail="retry" 时生效）
    max_retries: int = 3


@dataclass
class PostSuccessConfig:
    """验证通过后的检查（整合原 replan_policy）"""
    
    # 是否是高影响力工具（输出会影响后续多个步骤）
    high_impact: bool = False
    
    # 是否需要与历史步骤做一致性检查
    requires_consistency_check: bool = False
    consistency_check_against: List[str] = field(default_factory=list)
    
    # 自定义的 replan 触发条件（验证通过后才评估）
    replan_condition: Optional[str] = None


@dataclass
class ResultHandlingConfig:
    """结果处理配置（整合原 compress_function 等）"""
    
    # 结果压缩函数
    compress_function: Optional[Callable] = None
    
    # 缓存策略
    cache_policy: str = "none"  # "none" / "session" / "persistent"
    
    # 是否注册为检查点（供后续一致性检查使用）
    register_as_checkpoint: bool = False
    checkpoint_type: Optional[str] = None  # "interface" / "schema" / "config"
```

### 执行流程

```
工具执行完成
      │
      ▼
┌─────────────────────────────────────┐
│  第一阶段：ValidationConfig         │
│  - 调用 validate_function           │
│  - 失败 → on_fail 决定动作          │
│    ├─ "retry": 重试当前步骤         │
│    ├─ "replan": 触发重规划          │
│    ├─ "abort": 中止执行             │
│    └─ "continue": 忽略继续          │
└─────────────────────────────────────┘
      │ 通过
      ▼
┌─────────────────────────────────────┐
│  第二阶段：PostSuccessConfig        │
│  - high_impact → 注册检查点         │
│  - requires_consistency_check       │
│    → 与历史检查点对比               │
│  - replan_condition 满足            │
│    → 触发重规划                     │
└─────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  第三阶段：ResultHandlingConfig     │
│  - compress_function 压缩结果       │
│  - cache_policy 决定缓存策略        │
│  - register_as_checkpoint           │
│    → 注册为一致性检查点             │
└─────────────────────────────────────┘
      │
      ▼
    继续下一步
```

### 迁移计划

#### Phase 1：兼容期（当前版本）
- 保持现有字段（validate_function, replan_policy 等）
- 新增 `post_policy` 字段
- 内部实现 `get_effective_post_policy()` 兼容旧字段

```python
@dataclass
class ToolDefinition:
    # 旧字段（deprecated，保持兼容）
    validate_function: Optional[Callable] = None
    compress_function: Optional[Callable] = None
    replan_policy: Optional[ToolReplanPolicy] = None
    
    # 新字段（推荐使用）
    post_policy: Optional[ToolPostPolicy] = None
    
    def get_effective_post_policy(self) -> ToolPostPolicy:
        """获取生效的后处理策略（兼容旧字段）"""
        if self.post_policy:
            return self.post_policy
        
        # 从旧字段构造
        return ToolPostPolicy(
            validation=ValidationConfig(
                validate_function=self.validate_function
            ) if self.validate_function else None,
            post_success=PostSuccessConfig(
                high_impact=self.replan_policy.high_impact if self.replan_policy else False,
                requires_consistency_check=self.replan_policy.requires_consistency_check if self.replan_policy else False,
                replan_condition=self.replan_policy.replan_condition if self.replan_policy else None,
            ) if self.replan_policy else None,
            result_handling=ResultHandlingConfig(
                compress_function=self.compress_function
            ) if self.compress_function else None,
        )
```

#### Phase 2：过渡期（下一版本）
- 旧字段标记 `@deprecated`
- 文档引导用户迁移到 `post_policy`
- 新工具必须使用 `post_policy`

#### Phase 3：清理期（未来版本）
- 移除旧字段
- 只保留 `post_policy`

### TODO 清单

- [x] **P1.1 定义 ToolPostPolicy 及子配置类** ✅
  - `ValidationConfig`: 结果验证配置
  - `PostSuccessConfig`: 验证通过后检查配置
  - `ResultHandlingConfig`: 结果处理配置
  - `ToolPostPolicy`: 统一后处理策略
  - 📍 实现位置: `auto_agent/models.py`

- [x] **P1.2 在 ToolDefinition 中添加 post_policy 字段** ✅
  - 📍 实现位置: `auto_agent/models.py` - `ToolDefinition.post_policy`

- [x] **P1.3 实现 get_effective_post_policy() 兼容方法** ✅
  - 优先使用 `post_policy`，否则从旧字段构造
  - 实现 `ToolPostPolicy.from_legacy()` 静态方法
  - 📍 实现位置: `auto_agent/models.py` - `ToolDefinition.get_effective_post_policy()`

- [x] **P1.4 修改 ExecutionEngine 使用统一的后处理流程** ✅
  - 实现 `_apply_post_policy()` 方法
  - 实现 `_get_validation_action()` 方法
  - 替换执行循环中的分散逻辑
  - 📍 实现位置: `auto_agent/core/executor.py`

- [x] **P1.5 更新 @tool 和 @func_tool 装饰器支持 post_policy 参数** ✅
  - `@tool` 装饰器支持 `replan_policy` 和 `post_policy` 参数
  - `@func_tool` 装饰器支持 `replan_policy` 和 `post_policy` 参数
  - 更新文档示例
  - 📍 实现位置: `auto_agent/tools/registry.py`

- [x] **P1.6 迁移内置工具到新的 post_policy 配置** ✅
  - `code_executor`: 高影响力工具，配置一致性检查和工作记忆提取
  - `web_search`: 配置结果缓存策略
  - `calculator`: 简单工具，无需特殊后处理
  - 📍 实现位置: `auto_agent/tools/builtin/`

- [x] **P2.1 标记旧字段为 deprecated** ✅
  - `validate_function`: 标记为废弃，推荐使用 `post_policy.validation`
  - `compress_function`: 标记为废弃，推荐使用 `post_policy.result_handling`
  - `replan_policy`: 标记为废弃，推荐使用 `post_policy.post_success`
  - `param_aliases`: 标记为废弃，推荐使用 LLM 语义理解
  - `state_mapping`: 标记为废弃，推荐使用 `post_policy.result_handling.state_mapping`
  - 更新 `ToolDefinition` 类文档，添加迁移指南
  - 📍 实现位置: `auto_agent/models.py`

- [x] **P2.2 更新文档和示例** ✅
  - 在 `docs/TOOLS.md` 中添加 "统一后处理策略 (ToolPostPolicy)" 章节
  - 包含核心概念、配置类定义、使用方式、辅助方法、迁移指南、最佳实践
  - 更新目录结构
  - 📍 实现位置: `docs/TOOLS.md`

- [ ] **P3.1 移除旧字段（breaking change）**

---

## 阶段七：参数绑定规划器 Binding Planner ✅ 已完成

> 目标：减少运行时参数构造的 LLM 调用，将参数依赖分析提前到规划阶段

### 背景问题

当前框架在执行每个步骤时，都需要调用 LLM 来构造工具参数，导致：
- Token 消耗大（每步都要发送完整上下文）
- 延迟高（每步都要等待 LLM 响应）
- 重复推理（相同的参数依赖关系被多次分析）

### 解决方案

引入 Binding Planner，在规划阶段一次性分析所有步骤的参数依赖链路：

```
原有流程:
Plan → Execute Step1 → [LLM构造参数] → Execute Step2 → [LLM构造参数] → ...
                          ↑ 每步都要调用 LLM

新流程:
Plan → [Binding Planner] → Execute Step1 → Execute Step2 → ...
              ↑ 只调用一次 LLM，后续直接按绑定取值
```

### 实现清单

- [x] **7.1 定义数据结构** ✅
  - `BindingSourceType`: 参数来源类型枚举
  - `BindingFallbackPolicy`: 回退策略枚举
  - `ParameterBinding`: 单个参数的绑定配置
  - `StepBindings`: 单个步骤的所有参数绑定
  - `BindingPlan`: 完整的参数绑定计划
  - 📍 实现位置: `auto_agent/models.py`

- [x] **7.2 实现 BindingPlanner** ✅
  - `create_binding_plan()`: 为执行计划创建参数绑定
  - `_collect_steps_info()`: 收集步骤的工具参数信息
  - `_build_binding_prompt()`: 构建 LLM prompt
  - `_parse_binding_result()`: 解析 LLM 返回的绑定结果
  - 📍 实现位置: `auto_agent/core/binding_planner.py`

- [x] **7.3 修改 ExecutionEngine 支持 BindingPlan** ✅
  - `execute_plan_stream()` 新增 `binding_plan` 参数
  - `_build_tool_arguments()` 优先使用绑定解析参数
  - `_resolve_bindings()`: 解析步骤的参数绑定
  - `_resolve_single_binding()`: 解析单个参数绑定
  - `_resolve_step_output_binding()`: 解析步骤输出绑定
  - 保存步骤输出到 `_step_outputs` 供后续绑定使用
  - 📍 实现位置: `auto_agent/core/executor.py`

- [x] **7.4 修改 AutoAgent 集成 BindingPlanner** ✅
  - 初始化 `BindingPlanner` 实例
  - `run()` 和 `run_stream()` 在规划后调用 BindingPlanner
  - 新增 `enable_binding` 参数控制是否启用
  - 发送 `binding_plan` 事件通知绑定规划结果
  - 📍 实现位置: `auto_agent/core/agent.py`

- [x] **7.5 更新导出** ✅
  - 在 `auto_agent/__init__.py` 中导出新增的类
  - 📍 实现位置: `auto_agent/__init__.py`

- [x] **7.6 添加测试** ✅
  - 数据结构序列化/反序列化测试
  - BindingPlanner 功能测试
  - 📍 实现位置: `tests/test_binding_planner.py`

- [x] **7.7 添加文档** ✅
  - 📍 实现位置: `docs/BINDING_PLANNER.md`

### 预期收益

| 指标 | 原有方式 | 使用 Binding Planner |
|------|---------|---------------------|
| LLM 调用次数（5步任务） | 5 次 | 1 次 |
| 参数构造 Token 消耗 | ~2500 tokens | ~800 tokens |
| Token 节省 | - | ~68% |

---

---

## 阶段八：执行引擎模块化重构 ✅ 已完成

> 目标：将 executor.py（3200+ 行）拆分为多个职责单一的模块

### 背景问题

`executor.py` 文件过长（3200+ 行），包含了多个不同职责的代码：
- 核心执行逻辑
- 参数构造和绑定解析
- 重规划逻辑
- 一致性检查
- 后处理策略
- 状态管理

### 解决方案

将 `executor.py` 拆分为 `auto_agent/core/executor/` 目录下的多个模块：

```
auto_agent/core/executor/
├── __init__.py          # 导出
├── base.py              # ExecutionEngine 核心执行逻辑
├── param_builder.py     # 参数构造（绑定解析、LLM 推理、验证）
├── replan.py            # 重规划（模式检测、增量重规划）
├── consistency.py       # 一致性检查
├── post_policy.py       # 后处理策略
└── state.py             # 状态管理工具
```

### 实现清单

- [x] **8.1 创建 state.py** ✅
  - `get_nested_value()`: 从嵌套字典获取值
  - `compress_state_for_llm()`: 压缩状态供 LLM 使用
  - `update_state_from_result()`: 更新状态
  - 📍 实现位置: `auto_agent/core/executor/state.py`

- [x] **8.2 创建 param_builder.py** ✅
  - `ParameterBuilder` 类
  - `resolve_bindings_with_trace()`: 解析参数绑定
  - `build_arguments_with_llm()`: LLM 参数推理
  - `validate_parameters()`: 参数验证
  - `validate_and_fix_parameters()`: 验证并修正参数
  - 📍 实现位置: `auto_agent/core/executor/param_builder.py`

- [x] **8.3 创建 replan.py** ✅
  - `PatternType` 枚举
  - `ExecutionPattern` 数据类
  - `ReplanManager` 类
  - `detect_execution_patterns()`: 检测执行模式
  - `should_trigger_replan()`: 判断是否需要重规划
  - `evaluate_and_replan()`: 评估并重规划
  - `_incremental_replan()`: 增量重规划
  - `_generate_alternative_plan()`: 全量重规划
  - 📍 实现位置: `auto_agent/core/executor/replan.py`

- [x] **8.4 创建 consistency.py** ✅
  - `ConsistencyManager` 类
  - `register_consistency_checkpoint()`: 注册检查点
  - `check_consistency()`: 检查一致性
  - 📍 实现位置: `auto_agent/core/executor/consistency.py`

- [x] **8.5 创建 post_policy.py** ✅
  - `PostPolicyManager` 类
  - `apply_post_policy()`: 应用后处理策略
  - `extract_working_memory()`: 提取工作记忆
  - `get_validation_action()`: 获取验证失败动作
  - 📍 实现位置: `auto_agent/core/executor/post_policy.py`

- [x] **8.6 创建 base.py** ✅
  - `ExecutionEngine` 核心类
  - `execute_plan()`: 同步执行
  - `execute_plan_stream()`: 流式执行
  - `_execute_subtask()`: 执行子任务
  - `_build_tool_arguments()`: 构造参数
  - 兼容性方法委托给子模块
  - 📍 实现位置: `auto_agent/core/executor/base.py`

- [x] **8.7 更新 __init__.py** ✅
  - 导出所有公共类和函数
  - 📍 实现位置: `auto_agent/core/executor/__init__.py`

- [x] **8.8 更新原 executor.py** ✅
  - 改为从新模块导入并重新导出
  - 保持向后兼容
  - 📍 实现位置: `auto_agent/core/executor.py`

### 模块职责

| 模块 | 职责 | 行数 |
|------|------|------|
| base.py | 核心执行逻辑、子任务执行、参数构造入口 | ~500 |
| param_builder.py | 绑定解析、LLM 推理、参数验证 | ~350 |
| replan.py | 模式检测、增量/全量重规划 | ~400 |
| consistency.py | 检查点注册、一致性检查 | ~200 |
| post_policy.py | 后处理策略、工作记忆提取 | ~250 |
| state.py | 状态读取、更新、压缩 | ~100 |

### 预期收益

- 代码可读性提升：每个模块职责单一，易于理解
- 可维护性提升：修改某个功能只需关注对应模块
- 可测试性提升：可以单独测试每个模块
- 向后兼容：原有导入方式继续有效

---

## 相关文件

- `auto_agent/core/planner.py` - 任务规划器
- `auto_agent/core/binding_planner.py` - 参数绑定规划器
- `auto_agent/core/executor.py` - 执行引擎（重新导出）
- `auto_agent/core/executor/` - 执行引擎模块目录
  - `base.py` - 核心执行逻辑
  - `param_builder.py` - 参数构造
  - `replan.py` - 重规划
  - `consistency.py` - 一致性检查
  - `post_policy.py` - 后处理策略
  - `state.py` - 状态管理
- `auto_agent/core/context.py` - 执行上下文
- `auto_agent/core/agent.py` - AutoAgent 主类
- `auto_agent/models.py` - 数据模型
- `docs/BINDING_PLANNER.md` - Binding Planner 文档
