# Binding Planner（参数绑定规划器）

## 概述

Binding Planner 是一个参数绑定规划器，用于在规划阶段分析参数依赖链路，生成静态绑定配置，从而减少运行时的 LLM 调用，显著降低 token 消耗。

### 核心思路

将参数构造从"运行时 LLM 推理"提前到"规划时静态绑定"：

```
原有流程:
Plan → Execute Step1 → [LLM构造参数] → Execute Step2 → [LLM构造参数] → ...
                          ↑ 每步都要调用 LLM，token 消耗大

新流程:
Plan → [Binding Planner 一次性推理所有参数链路] → Execute Step1 → Execute Step2 → ...
                          ↑ 只调用一次 LLM，后续执行时直接按绑定取值
```

## 数据结构

### ParameterBinding

单个参数的绑定配置：

```python
@dataclass
class ParameterBinding:
    source: str                    # 数据来源路径
    source_type: BindingSourceType # 来源类型
    confidence: float              # 置信度 0.0-1.0
    fallback: BindingFallbackPolicy # 回退策略
    default_value: Any = None      # 默认值
    transform: Optional[str] = None # 转换表达式（预留）
    reasoning: Optional[str] = None # 推理说明
```

### BindingSourceType

参数来源类型：

| 类型 | 说明 | source 格式示例 |
|------|------|----------------|
| `USER_INPUT` | 来自用户输入 | `"query"` → `state["inputs"]["query"]` |
| `STEP_OUTPUT` | 来自前序步骤输出 | `"step_1.output.entities"` |
| `STATE` | 来自状态字段 | `"documents"` → `state["documents"]` |
| `LITERAL` | 字面量值 | 使用 `default_value` |
| `GENERATED` | 需要运行时生成 | fallback 到 LLM |

### BindingFallbackPolicy

绑定失败时的回退策略：

| 策略 | 说明 |
|------|------|
| `LLM_INFER` | 使用 LLM 推理（当前默认实现） |
| `USE_DEFAULT` | 使用默认值 |
| `ERROR` | 抛出错误 |

### StepBindings

单个步骤的所有参数绑定：

```python
@dataclass
class StepBindings:
    step_id: str                           # 步骤 ID
    tool: str                              # 工具名称
    bindings: Dict[str, ParameterBinding]  # 参数名 -> 绑定配置
```

### BindingPlan

完整的参数绑定计划：

```python
@dataclass
class BindingPlan:
    steps: List[StepBindings]      # 每个步骤的绑定配置
    confidence_threshold: float    # 置信度阈值（默认 0.7）
    reasoning: str                 # LLM 的整体推理过程
    created_at: str                # 创建时间
```

## 使用方式

### 自动集成（推荐）

`AutoAgent` 默认启用参数绑定，无需额外配置：

```python
from auto_agent import AutoAgent, OpenAIClient, ToolRegistry

agent = AutoAgent(
    llm_client=OpenAIClient(...),
    tool_registry=registry,
)

# 自动使用 Binding Planner
async for event in agent.run_stream(query="...", user_id="user"):
    if event["event"] == "binding_plan":
        print(f"绑定规划完成: {event['data']['bindings_count']} 个参数")
```

### 禁用参数绑定

如果需要禁用参数绑定（回退到原有的每步 LLM 推理）：

```python
# 方式1: 实例级别禁用
agent._enable_binding = False

# 方式2: 单次调用禁用
async for event in agent.run_stream(
    query="...",
    user_id="user",
    enable_binding=False,
):
    ...
```

### 手动使用 BindingPlanner

```python
from auto_agent import BindingPlanner, TaskPlanner

# 1. 创建规划器
task_planner = TaskPlanner(llm_client, tool_registry)
binding_planner = BindingPlanner(llm_client, tool_registry)

# 2. 生成执行计划
plan = await task_planner.plan(query="...")

# 3. 生成参数绑定
binding_plan = await binding_planner.create_binding_plan(
    execution_plan=plan,
    user_input=query,
)

# 4. 查看绑定结果
for step in binding_plan.steps:
    print(f"Step {step.step_id} ({step.tool}):")
    for param, binding in step.bindings.items():
        print(f"  {param}: {binding.source} ({binding.source_type.value})")
```

## State 结构设计

为了与 BindingPlanner 的绑定路径对齐，state 采用以下结构：

```python
state = {
    # 用户输入
    "inputs": {
        "query": "创建一个用户管理 API",
        "template_id": None,
    },
    
    # 控制信息
    "control": {
        "iterations": 0,
        "max_iterations": 20,
    },
    
    # 步骤输出（核心！与 BindingPlanner 对齐）
    "steps": {
        "1": {
            "tool": "analyze_requirements",
            "output": {
                "entities": [...],
                "relationships": [...],
            },
        },
        "2": {
            "tool": "design_api",
            "output": {
                "endpoints": [...],
                "schemas": {...},
            },
        },
    },
    
    # 兼容旧逻辑：顶层字段（后续可废弃）
    "entities": [...],
    "endpoints": [...],
}
```

### 绑定路径映射

| BindingPlanner source | State 路径 |
|----------------------|-----------|
| `step_1.output.entities` | `state["steps"]["1"]["output"]["entities"]` |
| `step_2.output.endpoints` | `state["steps"]["2"]["output"]["endpoints"]` |
| `query` (user_input) | `state["inputs"]["query"]` |
| `documents` (state) | `state["documents"]` |

## 执行流程

1. **规划阶段**
   - TaskPlanner 生成执行计划
   - BindingPlanner 分析参数依赖，生成 BindingPlan

2. **执行阶段**
   - 对于每个步骤，先尝试使用 BindingPlan 解析参数
   - 高置信度绑定直接取值，无需 LLM
   - 低置信度或未绑定的参数 fallback 到 LLM 推理
   - 步骤完成后，输出存储到 `state["steps"][step_id]["output"]`

3. **Fallback 机制**
   - 置信度低于阈值（默认 0.7）时触发 fallback
   - 绑定解析失败时触发 fallback
   - Fallback 使用原有的 LLM 参数构造逻辑

## 示例

### 三步流程的绑定计划

用户输入: "创建一个用户管理 API"

执行计划:
1. `analyze` - 分析需求
2. `design` - 设计 API
3. `generate` - 生成代码

生成的绑定计划:

```json
{
  "bindings": [
    {
      "step_id": "1",
      "tool": "analyze",
      "bindings": {
        "requirements": {
          "source": "query",
          "source_type": "user_input",
          "confidence": 1.0,
          "reasoning": "用户输入直接作为需求"
        }
      }
    },
    {
      "step_id": "2",
      "tool": "design",
      "bindings": {
        "entities": {
          "source": "step_1.output.entities",
          "source_type": "step_output",
          "confidence": 0.95,
          "reasoning": "来自分析步骤的实体输出"
        }
      }
    },
    {
      "step_id": "3",
      "tool": "generate",
      "bindings": {
        "endpoints": {
          "source": "step_2.output.endpoints",
          "source_type": "step_output",
          "confidence": 0.95,
          "reasoning": "来自设计步骤的端点输出"
        }
      }
    }
  ],
  "reasoning": "三步流程：分析需求 -> 设计API -> 生成代码"
}
```

## Token 消耗对比

假设一个 5 步任务，每步参数构造需要 ~500 tokens：

| 方式 | LLM 调用次数 | Token 消耗 |
|------|-------------|-----------|
| 原有方式 | 5 次 | ~2500 tokens |
| Binding Planner | 1 次 | ~800 tokens |

**节省约 68% 的参数构造 token 消耗**

## 注意事项

1. **单步任务不启用绑定**：只有 1 个步骤时不会调用 BindingPlanner
2. **绑定失败不影响执行**：BindingPlanner 失败时会 fallback 到原有逻辑
3. **置信度阈值可调**：默认 0.7，可根据需要调整
4. **步骤输出需要保存**：执行引擎会自动保存每步输出供后续绑定使用
