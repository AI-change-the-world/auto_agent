# 🤖 Auto-Agent 智能体框架

<div align="center">

**让AI自主规划、执行和学习**

[![Version](https://img.shields.io/badge/Version-0.1.0-blue.svg)](https://github.com/AI-change-the-world/auto_agent/releases)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-79%20passed-brightgreen.svg)](tests/)
[![Documentation](https://img.shields.io/badge/Docs-中文-blue.svg)](docs/)

*🚀 基于LLM的自主智能体框架，让AI像人类一样规划任务、调用工具、管理记忆*

[快速开始](#-快速开始) • [核心特性](#-核心特性) • [文档](docs/) • [示例](examples/) • [优化方案](OPTIMIZATION_PLAN.md)

</div>

---

## 📖 项目简介

Auto-Agent 是一个**自主智能体框架**，让大语言模型不仅仅是聊天工具，而是能够自主规划任务、执行复杂工作流、管理长期记忆的智能代理。

### 🎯 核心价值

- **🤖 自主执行**：自然语言描述需求，AI自主规划并执行
- **🧠 持续学习**：三层记忆系统，支持从经验中学习和改进
- **🔧 工具生态**：灵活的工具系统，支持自定义扩展
- **📊 可观测性**：完整的执行追踪和报告生成

### 📚 起源与发展

本项目最初在 [DocHive](https://github.com/AI-change-the-world/DocHive) 中进行设计和验证，现已独立为专门的智能体框架。

> ⚠️ **开发状态**：项目处于早期发展阶段，API可能在后续版本中调整。建议在生产环境中谨慎使用。

---

## 🌟 核心特性

### 🤖 智能体核心能力

| 特性 | 描述 | 亮点 |
|------|------|------|
| **自主规划** | 基于LLM的任务分解和执行计划生成 | 自然语言描述需求，AI自主规划执行路径 |
| **工具系统** | 灵活的工具注册机制，支持装饰器快速定义 | 3种定义方式，从简单到完全自定义 |
| **智能重试** | LLM驱动的错误分析、参数修正和策略学习 | 从失败中学习，自动优化执行策略 |
| **意图路由** | 自动识别用户意图并路由到合适的处理流程 | 支持多Agent协作和专业化分工 |

### 🧠 先进记忆系统

| 层级 | 名称 | 存储格式 | 生命周期 | 核心能力 |
|------|------|----------|----------|----------|
| **L1** | 短时记忆 | 内存 | 单任务 | 执行上下文、中间决策记录 |
| **L2** | 语义记忆 | JSON | 长期 | 用户偏好、知识、策略、错误恢复经验 |
| **L3** | 叙事记忆 | Markdown | 长期 | 高语义密度总结、Prompt注入 |

**✨ todo**
- 📊 **分类存储**：用户反馈、行为模式、偏好、知识等分类管理(部分实现)
- 🔄 **反馈学习**：用户反馈直接驱动记忆权重调整(暂未实现)
- 🎯 **智能注入**：按需注入相关记忆，避免上下文爆炸(部分实现)
- 📈 **持续优化**：从成功/失败经验中学习改进(暂未实现)

### 📊 可观测性与报告

- **📈 执行追踪**：完整的LLM调用记录和Token使用统计
- **📋 流程可视化**：Mermaid流程图自动生成
- **📝 智能报告**：Markdown + HTML双格式报告输出

## 🚀 快速开始

### 📦 安装

#### 从源码安装
```bash
git clone https://github.com/AI-change-the-world/auto_agent.git
cd auto_agent
pip install -e .
```

### ⚡ 五分钟上手

#### 1. 配置环境变量
```bash
# OpenAI
export OPENAI_API_KEY=your-api-key
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini
```

#### 2. 运行深度研究示例
```bash
python examples/deep_research_demo.py
```

这个示例会演示：
- 🤖 AI自主规划研究任务
- 🔧 自动调用多个工具
- 📊 生成完整的研究报告
- 📈 执行过程可视化

#### 3. 查看结果
运行后会在 `examples/output/` 目录生成：
- 📄 Markdown研究报告
- 🌐 HTML可视化报告
- 📋 详细的执行追踪日志

> 💡 **提示**：如果没有API Key，可以查看[离线示例](examples/basic_usage.py)了解基本用法。

## 🔧 工具系统

Auto-Agent提供灵活的工具系统，支持3种定义方式，从简单函数到复杂工具应有尽有。

### 🎯 三种定义方式对比

| 方式 | 难度 | 功能 | 适用场景 |
|------|------|------|----------|
| **函数装饰器** | ⭐ | 基础功能 | 简单同步/异步函数包装 |
| **类装饰器** | ⭐⭐ | 验证/压缩 | 需要参数验证或结果压缩 |
| **继承BaseTool** | ⭐⭐⭐ | 完全控制 | 复杂逻辑、依赖注入、状态管理 |

### 方式一：函数装饰器（最方便）✨

最简单的工具定义方式，适合包装现有函数：

```python
from auto_agent import func_tool

@func_tool(name="calculator", description="数学计算器", category="math")
async def calculator(expression: str, precision: int = 2) -> dict:
    """计算数学表达式，支持加减乘除和函数"""
    try:
        result = eval(expression)
        return {"success": True, "result": round(result, precision)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@func_tool(name="web_search", description="网络搜索", category="search")
async def web_search(query: str, limit: int = 5) -> dict:
    """使用搜索引擎获取信息"""
    # 实现搜索逻辑...
    return {"success": True, "results": [...], "count": limit}
```

### 方式二：类装饰器

适合需要参数验证或结果压缩的场景：

```python
from auto_agent import tool, BaseTool
from typing import Dict, Any

# 自定义压缩函数（控制上下文长度）
def compress_search_result(result: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """压缩搜索结果，避免上下文溢出"""
    return {
        "success": result.get("success"),
        "count": len(result.get("documents", [])),
        "top_docs": result.get("documents", [])[:3],  # 只保留前3个
    }

@tool(
    name="document_search",
    description="文档全文检索",
    category="retrieval",
    compress_function=compress_search_result,  # 结果压缩
)
class DocumentSearchTool(BaseTool):
    def __init__(self, index_path: str):
        self.index_path = index_path

    async def execute(self, query: str, limit: int = 10, **kwargs) -> Dict[str, Any]:
        # 实现文档搜索逻辑...
        return {
            "success": True,
            "documents": [...],
            "total_found": 25
        }
```

### 方式三：继承BaseTool

适合复杂工具，需要完全控制生命周期：

```python
from auto_agent import BaseTool, ToolDefinition, ToolParameter

class LLMReasoningTool(BaseTool):
    """使用LLM进行推理分析的工具"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="llm_reasoning",
            description="使用大语言模型进行推理分析",
            parameters=[
                ToolParameter(
                    name="question",
                    type="string",
                    description="需要推理的问题",
                    required=True
                ),
                ToolParameter(
                    name="context",
                    type="string",
                    description="相关上下文信息",
                    required=False
                ),
            ],
            category="reasoning",
            # 错误恢复配置
            error_recovery={
                "max_retries": 2,
                "retry_on": ["TIMEOUT_ERROR", "NETWORK_ERROR"]
            }
        )

    async def execute(self, question: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """执行LLM推理"""
        prompt = f"基于以下上下文回答问题：\n\n上下文：{context}\n问题：{question}"

        try:
            response = await self.llm_client.chat([
                {"role": "user", "content": prompt}
            ])
            return {
                "success": True,
                "answer": response,
                "confidence": 0.8
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
```

### 📋 工具注册

```python
from auto_agent import ToolRegistry, get_global_registry

# 方法1：使用全局注册表（装饰器会自动注册）
registry = get_global_registry()
print(f"已注册工具数量: {len(registry.get_all_tools())}")

# 方法2：手动注册到自定义注册表
custom_registry = ToolRegistry()
custom_registry.register(LLMReasoningTool(llm_client))
custom_registry.register(DocumentSearchTool("./index"))

# 方法3：在Agent中指定工具注册表
agent = AutoAgent(
    llm_client=llm_client,
    tool_registry=custom_registry,
    # ... 其他配置
)
```

> 💡 **提示**：查看 [examples/custom_tool.py](examples/custom_tool.py) 获取完整示例。

## 🌟 应用场景

Auto-Agent 适用于多种复杂的AI应用场景：

### 📊 研究与分析
- **深度研究**：自动规划研究流程，收集多源信息，生成综合报告
- **市场分析**：竞争对手分析、趋势预测、投资建议生成
- **技术调研**：新技术评估、架构方案设计、实现路径规划

### ✍️ 内容创作
- **文档写作**：技术文档、博客文章、研究报告自动生成
- **代码生成**：根据需求自动编写和优化代码
- **创意写作**：故事创作、营销文案、个性化内容

### 🤖 智能助手
- **任务自动化**：复杂工作流程的自动化执行
- **问题解决**：多步骤问题分析和解决方案生成
- **学习辅导**：个性化学习计划制定和进度跟踪

### 🔧 企业应用
- **数据处理**：自动数据清洗、分析和报告生成
- **客户服务**：智能客服、问题诊断、解决方案推荐
- **运营优化**：业务流程优化、效率分析、改进建议

### 📈 示例项目

| 示例 | 功能 | 复杂度 | 文件 |
|------|------|--------|------|
| **深度研究** | 自主规划研究任务，生成完整报告 | ⭐⭐⭐ | [deep_research_demo.py](examples/deep_research_demo.py) |
| **文档写作** | 智能写作助手，生成技术文档 | ⭐⭐⭐ | [writer_agent_demo.py](examples/writer_agent_demo.py) |
| **自定义工具** | 工具定义和注册示例 | ⭐ | [custom_tool.py](examples/custom_tool.py) |
| **记忆系统** | 记忆管理功能演示 | ⭐⭐ | [memory_demo.py](examples/memory_demo.py) |

### 🚀 运行示例

```bash
# 1. 配置环境变量
export OPENAI_API_KEY=your-api-key
export OPENAI_MODEL=gpt-4o-mini

# 2. 运行深度研究示例
python examples/deep_research_demo.py

# 3. 查看生成的结果
ls examples/output/
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

Auto-Agent 提供业界领先的三层记忆架构，支持反馈学习、智能注入和错误恢复策略记忆化。

### 🏗️ 三层记忆架构

| 层级 | 名称 | 存储格式 | 生命周期 | 核心用途 | 更新频率 |
|------|------|----------|----------|----------|----------|
| **L1** | 短时记忆 | 内存 | 单任务执行 | 执行上下文、中间决策、工具调用记录 | 实时 |
| **L2** | 语义记忆 | JSON | 长期持久化 | 用户偏好、知识库、成功策略、错误恢复经验 | 定期提炼 |
| **L3** | 叙事记忆 | Markdown | 长期持久化 | 高语义密度总结、行为模式分析、Prompt注入 | 周期性生成 |

**🎯 架构优势**
- **分层隔离**：不同生命周期记忆分离管理，避免相互干扰
- **智能注入**：基于查询意图按需注入相关记忆，控制Token成本
- **反馈闭环**：用户反馈直接影响记忆权重，形成持续学习能力
- **多格式存储**：JSON用于决策，Markdown用于语义理解

### 🚀 快速开始

```python
from auto_agent import MemorySystem, MemoryCategory

# 初始化统一记忆系统
memory = MemorySystem(storage_path="./data/memory", token_budget=2000)

user_id = "user_001"

# === L1 短时记忆 ===
task_id = memory.start_task(user_id, "帮我写一篇AI报告")
wm = memory.get_working_memory(task_id)

# 记录执行过程
wm.add_decision("使用分层结构组织内容", "提升可读性")
wm.add_tool_call("web_search", {"query": "AI最新进展"}, {"success": True, "count": 15})

# 任务结束时提炼到长期记忆
memory.end_task(user_id, task_id, promote_to_long_term=True)

# === L2 语义记忆 ===
# 便捷方法记录各类记忆
memory.set_preference(user_id, "language", "中文")
memory.add_knowledge(user_id, "用户精通Python和FastAPI框架")
memory.add_strategy(user_id, "复杂任务先分解为子任务", is_successful=True)

# 分类管理
memory.add_memory(
    user_id=user_id,
    content="用户偏好使用异步代码模式",
    category=MemoryCategory.PREFERENCE,
    tags=["coding", "async"],
    confidence=0.9,
)

# === 用户反馈驱动学习 ===
item = memory.add_memory(user_id, "建议使用类型注解")
memory.thumbs_up(user_id, item.memory_id)  # 👍 正反馈
memory.thumbs_down(user_id, item.memory_id, "某些场景下过于繁琐")  # 👎 负反馈

# === L3 叙事记忆 ===
reflection = memory.generate_reflection(
    user_id=user_id,
    title="编程习惯总结",
    category=MemoryCategory.STRATEGY,
)
```

> 📖 **详细文档**：[记忆系统设计](docs/MEMORY.md) | [迁移指南](docs/MIGRATION_GUIDE.md)

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

## 🏗️ 项目架构

### 📂 核心模块

```
auto_agent/
├── core/                    # 🧠 核心智能体功能
│   ├── agent.py            # AutoAgent 主类 - 智能体核心
│   ├── planner.py          # TaskPlanner - 任务规划器
│   ├── executor.py         # 执行引擎
│   ├── context.py          # 执行上下文管理
│   ├── editor/             # Agent Markdown 解析器
│   ├── report/             # 执行报告生成器
│   └── router/             # IntentRouter - 意图路由器
├── llm/                    # 🤖 大语言模型支持
│   ├── client.py           # LLM 客户端抽象基类
│   ├── providers/          # 模型提供商
│   │   ├── openai.py       # OpenAI GPT 系列
│   │   ├── anthropic.py    # Claude 系列
│   │   └── deepseek.py     # DeepSeek 模型
├── memory/                 # 🧠 三层记忆系统
│   ├── system.py           # 统一记忆系统 (L1/L2/L3)
│   ├── working.py          # L1 短时记忆
│   ├── semantic.py         # L2 长期语义记忆
│   ├── narrative.py        # L3 叙事记忆
│   ├── router.py           # 记忆路由器
│   ├── manager.py          # 记忆管理器
│   ├── models.py           # 记忆数据模型
│   └── storage/            # 存储后端
│       ├── sqlite.py       # SQLite 存储
│       ├── redis.py        # Redis 缓存
│       └── markdown.py     # Markdown 文件存储
├── tools/                  # 🔧 工具生态系统
│   ├── base.py             # 工具基类
│   ├── registry.py         # 工具注册表
│   ├── models.py           # 工具数据模型
│   └── builtin/            # 内置工具
│       ├── calculator.py   # 计算器工具
│       ├── code_executor.py # 代码执行器
│       └── web_search.py   # 网络搜索工具
├── retry/                  # 🔄 智能重试机制
│   ├── controller.py       # 重试控制器
│   ├── models.py           # 重试配置模型
│   └── strategies.py       # 重试策略
├── session/                # 💬 会话管理
│   ├── manager.py          # 会话管理器
│   └── models.py           # 会话数据模型
├── tracing/                # 📊 执行追踪
│   ├── context.py          # 追踪上下文
│   └── models.py           # 追踪数据模型
└── utils/                  # 🛠️ 工具函数
    ├── logger.py           # 日志工具
    ├── serialization.py    # 序列化工具
    └── validators.py       # 数据验证器
```

### 📚 示例与文档

```
examples/                   # 💡 使用示例
├── deep_research_demo.py   # 深度研究智能体
├── writer_agent_demo.py    # 文档写作助手
├── memory_demo.py          # 记忆系统演示
├── custom_tool.py          # 自定义工具示例
└── basic_usage.py          # 基础使用方法

docs/                       # 📖 项目文档
├── MEMORY.md              # 记忆系统设计详解
├── TOOLS.md               # 工具开发指南
├── OPTIMIZE.md            # 性能优化建议
└── MIGRATION_GUIDE.md     # 版本迁移指南

tests/                      # 🧪 测试套件
├── test_memory_system.py  # 记忆系统测试
├── test_router.py         # 路由器测试
└── test_integration.py    # 集成测试
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

## 🌍 社区与支持

### 🤝 贡献指南

我们欢迎各种形式的贡献！无论是代码、文档、测试，还是问题反馈和功能建议。

#### 开发贡献

1. **Fork 项目仓库**
2. **创建功能分支**
   ```bash
   git checkout -b feature/amazing-feature
   # 或修复bug
   git checkout -b fix/bug-description
   ```
3. **提交更改**
   ```bash
   git commit -m "feat: add amazing new feature"
   # 遵循 Conventional Commits 规范
   ```
4. **推送并创建 PR**
   ```bash
   git push origin feature/amazing-feature
   # 在 GitHub 上创建 Pull Request
   ```

#### 开发环境设置

```bash
# 1. 克隆仓库
git clone https://github.com/AI-change-the-world/auto_agent.git
cd auto_agent

# 2. 安装开发依赖
pip install -e ".[dev,storage,llm]"

# 3. 运行测试
pytest tests/ -v

# 4. 代码格式化
black auto_agent/
ruff auto_agent/ --fix
```

#### 贡献类型

- 🐛 **Bug 修复**：修复现有问题
- ✨ **新功能**：添加新特性
- 📚 **文档**：改进文档和示例
- 🧪 **测试**：添加或改进测试
- 🔧 **工具**：开发新工具或改进现有工具
- 🎨 **重构**：代码结构优化

### 📞 获取帮助

- 📖 **[文档中心](docs/)** - 详细使用指南和技术文档
- 💬 **[Issues](https://github.com/AI-change-the-world/auto_agent/issues)** - 报告问题或提出建议
- 💡 **[Discussions](https://github.com/AI-change-the-world/auto_agent/discussions)** - 讨论功能和最佳实践
- 📧 **邮箱** - guchengxi1994@qq.com

### 🙏 致谢

感谢所有贡献者的支持！特别感谢：

- **DocHive** 项目，为 Auto-Agent 的核心思想提供了验证
- **开源社区**，提供了优秀的工具和灵感
- **早期用户**，通过反馈帮助我们改进产品

## 📄 许可证

**MIT License** - 自由使用，保留署名

完整许可证文本请查看 [LICENSE](LICENSE) 文件。

---

<div align="center">

**🚀 使用 Auto-Agent 构建下一代智能应用！**

[![Star History Chart](https://api.star-history.com/svg?repos=AI-change-the-world/auto_agent&type=Date)](https://star-history.com/#AI-change-the-world/auto_agent&Date)

**如果这个项目对你有帮助，请给我们一个 ⭐ Star！**

</div>
