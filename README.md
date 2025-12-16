# Auto-Agent 智能体框架

<p align="center">
  <img src="https://img.shields.io/badge/Version-0.1.0-blue.svg" alt="Version" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python Version" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" />
</p>

Auto-Agent 是一个基于大语言模型的自主智能体框架，提供自主规划、工具调用、记忆管理等核心能力。

*本项目最初在 [DocHive](https://github.com/AI-change-the-world/DocHive) 中进行设计和验证，用于智能体的自动化构建，现已独立拆分为一个 Python package。由于仍处于早期发展阶段，部分功能可能尚未完全稳定，相关 API 在后续版本中可能会有所变动。*

## 🌟 核心特性

- 🤖 **自主规划**：基于 LLM 的任务分解和执行计划生成
- 🔧 **工具系统**：灵活的工具注册机制，支持装饰器快速定义
- 🔄 **智能重试**：LLM 驱动的错误分析、参数修正和策略学习
- 🧠 **三层记忆**：L1 短时记忆 + L2 语义记忆 + L3 叙事记忆
- 📊 **分类记忆**：用户反馈、行为模式、偏好、知识等分类存储
- 🎯 **意图路由**：自动识别用户意图并路由到合适的处理流程
- 📝 **执行报告**：Mermaid 流程图 + Markdown 报告生成
- 💬 **会话管理**：多轮对话、用户干预、会话持久化

## 🚀 快速开始

### 安装

从源码安装：

```bash
git clone https://github.com/AI-change-the-world/auto_agent.git
cd auto_agent
pip install -e .
```

### Example

[deep_research_demo](./examples/deep_research_demo.py)

```bash
# 配置 OpenAI
export OPENAI_API_KEY=your-api-key
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini
```

```bash
python examples/deep_research_demo.py
```

## 🔧 工具定义

Auto-Agent 提供三种工具定义方式，从简单到复杂：

### 方式 1: 函数装饰器（最简洁）✨

```python
from auto_agent import func_tool

@func_tool(name="calculator", description="简单计算器", category="math")
async def calculator(expression: str, precision: int = 2) -> dict:
    """
    计算数学表达式
    
    Args:
        expression: 数学表达式，如 "1 + 2 * 3"
        precision: 小数精度
    """
    result = eval(expression)
    return {"success": True, "result": round(result, precision)}

@func_tool(name="search_docs", description="搜索文档")
async def search_docs(query: str, limit: int = 10) -> dict:
    # 搜索逻辑...
    return {"success": True, "documents": [...], "count": 5}
```

### 方式 2: 类装饰器（带验证/压缩）

```python
from auto_agent import tool, BaseTool, ToolDefinition, ToolParameter

# 自定义压缩函数（避免上下文溢出）
def compress_search(result, state):
    return {
        "success": result.get("success"),
        "document_ids": result.get("document_ids", [])[:20],
        "count": len(result.get("document_ids", [])),
    }

@tool(
    name="es_search",
    description="全文检索",
    category="retrieval",
    compress_function=compress_search,
)
class ESSearchTool(BaseTool):
    async def execute(self, query: str, size: int = 10, **kwargs) -> dict:
        # 检索逻辑...
        return {"success": True, "document_ids": [...], "documents": [...]}
```

### 方式 3: 继承 BaseTool（完全控制）

```python
from auto_agent import BaseTool, ToolDefinition, ToolParameter

class AnalyzeInputTool(BaseTool):
    def __init__(self, llm_client):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_input",
            description="分析用户输入，识别意图和关键信息",
            parameters=[
                ToolParameter(name="query", type="string", description="用户输入", required=True),
            ],
            category="analysis",
        )

    async def execute(self, query: str, **kwargs) -> dict:
        # 使用 LLM 分析...
        return {"success": True, "intent": "写作", "topic": "AI"}
```

### 工具注册

```python
from auto_agent import ToolRegistry, get_global_registry

# 方式 1: 使用全局注册表（装饰器自动注册）
registry = get_global_registry()

# 方式 2: 手动注册到自定义注册表
registry = ToolRegistry()
registry.register(AnalyzeInputTool(llm_client))
registry.register(ESSearchTool())
```


## 🎯 IntentRouter vs TaskPlanner

Auto-Agent 提供两个核心组件用于处理用户请求：

| 组件     | IntentRouter (意图路由器)                 | TaskPlanner (任务规划器)           |
| -------- | ----------------------------------------- | ---------------------------------- |
| **职责** | 识别用户意图，选择哪个 Agent/Handler 处理 | 规划具体执行步骤，决定调用哪些工具 |
| **输出** | 单一结果：handler_name + confidence       | 多步骤计划：steps[] + state_schema |
| **粒度** | 粗粒度（选择处理器）                      | 细粒度（编排工具链）               |
| **时机** | 请求入口，第一步                          | 确定 Agent 后，规划执行流程        |

### 典型流程

```
用户输入: "帮我写一篇AI报告"
         ↓
    IntentRouter
         ↓ 路由到 "writer" Agent
    TaskPlanner
         ↓ 规划步骤
    [analyze_input → search → outline → compose]
         ↓
    执行工具链
```

### IntentRouter 使用示例

```python
from auto_agent import IntentRouter, OpenAIClient

# 初始化
llm = OpenAIClient(api_key="sk-xxx")
router = IntentRouter(llm_client=llm, default_handler="chat")

# 注册处理器
router.register(
    name="writer",
    description="文档写作，包括报告、文章、笔记等",
    keywords=["写", "撰写", "文档", "报告", "文章"],
)
router.register(
    name="search",
    description="信息检索和搜索",
    keywords=["搜索", "查找", "检索"],
)
router.register(
    name="qa",
    description="问答和知识查询",
    keywords=["什么是", "如何", "为什么"],
)

# 路由
result = await router.route("帮我写一篇关于AI的调研报告")
print(f"路由到: {result.handler_name}, 置信度: {result.confidence}")
# 输出: 路由到: writer, 置信度: 0.70
```

### TaskPlanner 使用示例

```python
from auto_agent.core.planner import TaskPlanner

planner = TaskPlanner(
    llm_client=llm,
    tool_registry=registry,
    agent_goals=["理解用户需求", "生成高质量文档"],
    agent_constraints=["文档不超过5000字"],
)

plan = await planner.plan(
    query="写一篇AI医疗报告",
    user_context="用户是技术人员",
    conversation_context="",
)

for step in plan.subtasks:
    print(f"Step {step.id}: {step.tool} - {step.description}")
```

## 🧠 记忆系统

Auto-Agent 提供先进的 L1/L2/L3 三层记忆架构，支持反馈学习、智能注入和错误恢复策略记忆化。

### 三层记忆架构 ✨

| 层级 | 名称 | 存储格式 | 生命周期 | 用途 |
|------|------|----------|----------|------|
| **L1** | 短时记忆 (WorkingMemory) | 内存 | 单次任务 | 执行上下文、中间决策、工具调用记录 |
| **L2** | 语义记忆 (SemanticMemory) | JSON | 长期持久化 | 用户偏好、知识、策略、错误恢复经验 |
| **L3** | 叙事记忆 (NarrativeMemory) | Markdown | 长期持久化 | 高语义密度总结、Prompt 注入 |

```python
from auto_agent import MemorySystem, MemoryCategory, MemorySource

# 初始化统一记忆系统
memory = MemorySystem(storage_path="./data/memory", token_budget=2000)

user_id = "user_001"

# === L1 短时记忆 (WorkingMemory) ===
# 单次任务执行上下文，任务结束后可提炼到长期记忆
task_id = memory.start_task(user_id, "帮我写一篇AI报告")
wm = memory.get_working_memory(task_id)
wm.add_decision("使用分层结构", "更易阅读")
wm.add_tool_call("search", {"query": "AI"}, {"success": True, "count": 10}, step_id="s1")
# 任务结束，提炼到长期记忆
memory.end_task(user_id, task_id, promote_to_long_term=True)

# === L2 长期语义记忆 (SemanticMemory) ===
# JSON 结构化，支持分类、标签、打分、时间衰减

# 添加记忆
memory.add_memory(
    user_id=user_id,
    content="用户偏好简洁的代码风格",
    category=MemoryCategory.PREFERENCE,
    tags=["code", "style"],
    confidence=0.8,
)

# 便捷方法
memory.set_preference(user_id, "language", "Python")
memory.add_knowledge(user_id, "用户熟悉 FastAPI 框架")
memory.add_strategy(user_id, "先写测试再写代码", is_successful=True)

# 搜索记忆
results = memory.search_memory(user_id, "Python")

# === 用户反馈驱动学习 ===
item = memory.add_memory(user_id, "建议使用 async/await")

# 👍 正反馈：提升 confidence 和 reward
memory.thumbs_up(user_id, item.memory_id)

# 👎 负反馈：降低权重，标记需要修订
memory.thumbs_down(user_id, item.memory_id, reason="不适用于同步场景")

# === 智能记忆注入 ===
# 根据查询自动路由和注入相关记忆
result = memory.get_context_for_query(user_id, "帮我写一个 Python API")
print(result["context"])  # 注入到 Prompt 的文本
print(result["token_estimate"])  # 估计 token 数
print(result["analysis"])  # 查询分析结果

# === L3 叙事记忆 (NarrativeMemory) ===
# Markdown 格式，高语义密度，用于 Prompt 注入
reflection = memory.generate_reflection(
    user_id=user_id,
    title="编码经验总结",
    category=MemoryCategory.STRATEGY,
)
```

#### 记忆路由器 (MemoryRouter)

自动分析查询，决定注入哪些记忆：

```python
from auto_agent import MemoryRouter, SemanticMemory, QueryIntent

sm = SemanticMemory()
router = MemoryRouter(sm, default_token_budget=2000)

# 分析查询意图和领域
analysis = router.analyze_query("帮我总结一下之前的学习经验")
print(analysis["intent"])  # QueryIntent.REFLECTION
print(analysis["categories"])  # [MemoryCategory.STRATEGY, ...]

# 判断是否需要记忆
should_use, reason = router.should_use_memory("你好")  # False, "简单问候"
should_use, reason = router.should_use_memory("帮我写代码")  # True, "领域相关"

# 获取注入配置
config = router.get_memory_injection_config("总结经验")
# {"use_l3_narrative": True, "token_budget": 3000, "priority": "recency"}
```

## 🔄 智能重试机制

Auto-Agent 提供 LLM 驱动的智能重试机制，能够分析错误原因、自动修正参数，并从成功的恢复策略中学习。

### 核心能力

| 能力 | 说明 |
|------|------|
| **智能错误分析** | 使用 LLM 分析错误类型、根因和可恢复性 |
| **参数自动修正** | 当检测到参数错误时，自动推断正确参数值 |
| **策略学习** | 将成功的恢复策略记录到 L2 记忆，供后续复用 |
| **历史策略优先** | 遇到类似错误时，优先使用历史成功策略 |

### 错误类型与恢复策略

| 错误类型 | 可恢复性 | 默认策略 |
|---------|---------|---------|
| `PARAMETER_ERROR` | 高 | LLM 修正参数后重试 |
| `NETWORK_ERROR` | 高 | 指数退避重试 |
| `TIMEOUT_ERROR` | 中 | 增加超时后重试 |
| `RESOURCE_ERROR` | 中 | 等待或切换资源 |
| `LOGIC_ERROR` | 低 | 触发重规划 |
| `PERMISSION_ERROR` | 低 | 中止并报告 |

### 使用示例

```python
from auto_agent.retry import RetryController, RetryConfig, ErrorType

# 创建带 LLM 的重试控制器
retry_controller = RetryController(
    config=RetryConfig(max_retries=3),
    llm_client=llm_client,
)

# 智能错误分析
error_analysis = await retry_controller.analyze_error(
    exception=e,
    context={"state": state, "arguments": args},
    tool_definition=tool.definition,
    memory_system=memory,  # 可选：启用历史策略查询
)

# 参数修正建议
if error_analysis.error_type == ErrorType.PARAMETER_ERROR:
    fixed_params = await retry_controller.suggest_parameter_fixes(
        failed_params=args,
        error_analysis=error_analysis,
        context={"state": state},
    )

# 记录成功的恢复策略（自动学习）
await retry_controller.record_successful_recovery(
    original_error=e,
    tool_name="search_documents",
    original_params=original_args,
    fixed_params=fixed_params,
    memory_system=memory,
)
```

### 错误恢复流程

```
执行失败
    │
    ▼
┌─────────────────┐
│ 查询历史策略    │ ← 优先使用 L2 记忆中的成功策略
└────────┬────────┘
         │
    ┌────┴────┐
    │ 有匹配？ │
    └────┬────┘
         │
    ┌────┴────┐
   是        否
    │         │
    ▼         ▼
使用历史   LLM 分析
策略重试   错误原因
    │         │
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │ 成功？  │
    └────┬────┘
         │
    ┌────┴────┐
   是        否
    │         │
    ▼         ▼
记录策略   继续重试
到 L2     或重规划
```

### 旧接口：分类记忆 (CategorizedMemory)

基于 KV 存储的分类记忆系统，支持全文检索：

```python
from auto_agent import CategorizedMemory, MemoryCategory

memory = CategorizedMemory(storage_path="./data/memories")

user_id = "user_001"

# 设置用户偏好
memory.set_preference(user_id, "language", "中文")
memory.set_preference(user_id, "style", "专业")

# 记录用户反馈
memory.add_feedback(user_id, "响应速度很快", rating=5)

# 记录用户行为
memory.add_behavior(user_id, "write_document", {"topic": "AI"})

# 添加知识
memory.add_knowledge(user_id, "用户熟悉 Python 编程", tags=["技能", "Python"])

# 搜索记忆
results = memory.search(user_id, "Python")
for item in results:
    print(f"[{item.category.value}] {item.key}: {item.value}")

# 获取上下文摘要（用于 LLM）
context = memory.get_context_summary(user_id)
print(context)
```

### 短期记忆 (ShortTermMemory)

对话级记忆，支持智能压缩：

```python
from auto_agent import ShortTermMemory

stm = ShortTermMemory(max_context_chars=5000)

# 压缩执行状态（避免上下文溢出）
compressed = stm.summarize_state(
    state={"documents": large_doc_list},
    step_history=execution_history,
    target_tool_name="compose_document",
    max_steps=5,
)
# 原始 22690 字符 → 压缩后 1504 字符 (93.4% 压缩率)
```

## 💬 会话管理

```python
from auto_agent import SessionManager, SessionStatus

session_mgr = SessionManager(default_ttl=1800)  # 30分钟过期

# 创建会话
session = session_mgr.create_session(
    user_id="user_001",
    initial_query="帮我写一篇技术文档",
)

# 添加消息
session_mgr.add_message(session.session_id, "assistant", "好的，请问主题是什么？")

# 等待用户输入
session_mgr.wait_for_input(session.session_id, "请提供文档主题")
# session.status == SessionStatus.WAITING_INPUT

# 用户回复后恢复
session_mgr.resume_session(session.session_id, "关于 Python 异步编程")
# session.status == SessionStatus.ACTIVE

# 获取对话历史
history = session_mgr.get_conversation_history(session.session_id)

# 完成会话
session_mgr.complete_session(session.session_id, "文档生成完成！")
```

## 📊 执行报告

```python
from auto_agent import ExecutionReportGenerator, ExecutionPlan, PlanStep, SubTaskResult

# 生成报告数据
report_data = ExecutionReportGenerator.generate_report_data(
    agent_name="文档写作智能体",
    query="写一篇AI报告",
    plan=plan,
    results=results,
    state=final_state,
)

# 获取 Mermaid 流程图
print(report_data["mermaid_diagram"])
# graph TD
#     Start([开始]) --> Step1
#     Step1[analyze_input] --> Step2
#     Step2[search_documents] --> Step3
#     ...

# 生成 Markdown 报告
markdown = ExecutionReportGenerator.generate_markdown_report(report_data)
```

## 📝 Agent Markdown 定义

支持使用 Markdown 定义 Agent：

```python
from auto_agent import AgentMarkdownParser, OpenAIClient

agent_md = """
## 文档写作智能体

你需要按以下步骤完成用户的需求：

1. 调用 [analyze_input] 工具，分析用户意图
2. 调用 [es_fulltext_search] 工具，检索相关文档
3. 调用 [generate_outline] 工具，生成大纲
4. 调用 [document_compose] 工具，撰写文档

### 目标
- 理解用户的写作需求
- 生成结构清晰的文档

### 约束
- 文档长度不超过5000字
"""

llm = OpenAIClient(api_key="sk-xxx")
parser = AgentMarkdownParser(llm_client=llm)
result = await parser.parse(agent_md)

if result["success"]:
    agent_def = result["agent"]
    print(f"Agent: {agent_def.name}")
    print(f"Goals: {agent_def.goals}")
    print(f"Steps: {[s.tool for s in agent_def.initial_plan]}")
```


## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      User Input                             │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    IntentRouter                             │
│         识别意图，选择 Agent/Handler                         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    TaskPlanner                              │
│         规划执行步骤，编排工具链                              │
│                  ↑ 记忆注入 (MemoryRouter)                   │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Execution Engine                           │
│ ┌─────────────┐ ┌──────────────────┐ ┌──────────────┐      │
│ │ Tool        │ │ Smart Retry      │ │ Result       │      │
│ │ Registry    │→│ Controller       │→│ Compressor   │      │
│ └─────────────┘ │ + LLM 错误分析   │ └──────────────┘      │
│                 │ + 参数自动修正   │                        │
│                 │ + 动态重规划     │                        │
│                 └────────┬─────────┘                        │
└──────────────────────────┼──────────────────────────────────┘
                           │ 策略学习
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Memory System (L1/L2/L3)                 │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐      │
│ │ L1 Working    │ │ L2 Semantic   │ │ L3 Narrative  │      │
│ │ (任务上下文)  │ │ (长期记忆)    │ │ (叙事总结)    │      │
│ │               │ │ + 错误恢复策略│ │               │      │
│ └───────────────┘ └───────────────┘ └───────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## 📁 目录结构

```
auto_agent/
├── auto_agent/
│   ├── __init__.py           # 主入口，导出所有公共 API
│   ├── models.py             # 公共数据模型
│   ├── core/
│   │   ├── agent.py          # AutoAgent 主类
│   │   ├── planner.py        # TaskPlanner 任务规划器
│   │   ├── editor/           # Agent Markdown 解析
│   │   ├── report/           # 执行报告生成
│   │   └── router/           # IntentRouter 意图路由
│   ├── llm/
│   │   ├── client.py         # LLM 客户端抽象基类
│   │   ├── prompts.py        # 提示词模板
│   │   └── providers/
│   │       └── openai.py     # OpenAI/DeepSeek 客户端
│   ├── memory/
│   │   ├── system.py         # 统一记忆系统 (新架构)
│   │   ├── working.py        # L1 短时记忆
│   │   ├── semantic.py       # L2 长期语义记忆
│   │   ├── narrative.py      # L3 叙事记忆
│   │   ├── router.py         # 记忆路由器
│   │   ├── models.py         # 记忆数据模型
│   │   ├── categorized.py    # 分类记忆 (旧接口)
│   │   ├── long_term.py      # 长期记忆 (旧接口)
│   │   └── short_term.py     # 短期记忆 (旧接口)
│   ├── session/
│   │   ├── manager.py        # 会话管理器
│   │   └── models.py         # 会话数据模型
│   ├── tools/
│   │   ├── base.py           # 工具基类
│   │   └── registry.py       # 工具注册表 + 装饰器
│   ├── retry/
│   │   └── models.py         # 重试配置
│   └── utils/
├── examples/
│   ├── full_demo.py          # 完整功能演示
│   └── writer_agent_demo.py  # 文档写作智能体示例
├── tests/
│   ├── test_session.py       # 会话管理测试
│   ├── test_router.py        # 意图路由测试
│   ├── test_memory.py        # 分类记忆测试
│   ├── test_memory_system.py # 新记忆系统测试 (L1/L2/L3)
│   └── test_integration.py   # 集成测试
├── pyproject.toml
└── README.md
```

## 🧪 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_memory.py -v

# 查看覆盖率
pytest tests/ --cov=auto_agent --cov-report=html
```

当前测试覆盖：79 个测试用例全部通过。

## 📦 API 参考

### 核心类

| 类名                       | 描述                       |
| -------------------------- | -------------------------- |
| `AutoAgent`                | 智能体主类                 |
| `OpenAIClient`             | OpenAI/DeepSeek LLM 客户端 |
| `ToolRegistry`             | 工具注册表                 |
| `BaseTool`                 | 工具基类                   |
| `IntentRouter`             | 意图路由器                 |
| `TaskPlanner`              | 任务规划器                 |
| `SessionManager`           | 会话管理器                 |
| `MemorySystem`             | 统一记忆系统 (L1/L2/L3)    |
| `WorkingMemory`            | L1 短时记忆                |
| `SemanticMemory`           | L2 长期语义记忆            |
| `NarrativeMemoryManager`   | L3 叙事记忆                |
| `MemoryRouter`             | 记忆路由器                 |
| `RetryController`          | 智能重试控制器             |
| `CategorizedMemory`        | 分类记忆系统 (旧接口)      |
| `ShortTermMemory`          | 短期记忆 (旧接口)          |
| `ExecutionReportGenerator` | 执行报告生成器             |
| `AgentMarkdownParser`      | Agent Markdown 解析器      |

### 装饰器

| 装饰器       | 描述                          |
| ------------ | ----------------------------- |
| `@func_tool` | 函数工具装饰器（最简洁）      |
| `@tool`      | 类工具装饰器（支持验证/压缩） |

### 数据模型

| 模型                    | 描述                |
| ----------------------- | ------------------- |
| `ToolDefinition`        | 工具定义 (含错误恢复配置) |
| `ToolParameter`         | 工具参数            |
| `ErrorRecoveryStrategy` | 错误恢复策略配置    |
| `ParameterValidator`    | 参数验证器          |
| `ExecutionPlan`         | 执行计划            |
| `PlanStep`              | 计划步骤            |
| `SubTaskResult`         | 子任务结果          |
| `Session`               | 会话                |
| `MemoryItem`            | 记忆条目            |
| `MemoryCategory`        | 记忆分类枚举        |
| `SemanticMemoryItem`    | L2 语义记忆条目     |
| `UserFeedback`          | 用户反馈            |
| `QueryIntent`           | 查询意图枚举        |
| `ErrorType`             | 错误类型枚举        |
| `ErrorAnalysis`         | LLM 错误分析结果    |
| `ErrorRecoveryRecord`   | 错误恢复记录        |

## 🤝 贡献指南

1. Fork 项目仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

MIT License - 查看 [LICENSE](LICENSE) 文件了解详情。

---

<div align="center">
  <strong>🚀 使用 Auto-Agent 构建下一代智能应用!</strong>
</div>
