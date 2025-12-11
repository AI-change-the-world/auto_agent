# Auto-Agent 框架核心上下文

此文件提供 Auto-Agent 框架的关键结构和工作流，用于辅助代码理解和生成。

## 1. 架构总览 (Data Flow)

**核心流程：** `User Input` → `Orchestrator` → `Execution` → `Memory Update`



## 2. 核心组件与职责

| 组件                      | 类/目录                | 核心职责 (Action)                                                                                 |
| :------------------------ | :--------------------- | :------------------------------------------------------------------------------------------------ |
| **AgentOrchestrator**     | `core/orchestrator.py` | **核心协调**：意图识别、任务分解 (TaskPlanner)、记忆管理。                                        |
| **ExecutionEngine**       | `core/executor.py`     | **执行控制**：工具调用 (ToolRegistry)、错误处理 (RetryController)、结果聚合。                     |
| **LongTermMemory** (LTM)  | `memory/long_term.py`  | **用户级持久记忆**：存储偏好、历史、知识库。格式：Markdown 文件。                                 |
| **ShortTermMemory** (STM) | `memory/short_term.py` | **对话级临时记忆**：存储当前对话消息、上下文、工作状态 (WorkingMemory)。存储：内存/SQLite/Redis。 |
| **TaskPlanner**           | `core/planner.py`      | **自主规划**：基于 Prompt 和上下文生成 JSON 格式的 `ExecutionPlan`。                              |
| **ToolRegistry**          | `tools/registry.py`    | **工具管理**：注册、查找、提供工具描述 (JSON Schema) 给 LLM。                                     |
| **RetryController**       | `retry/controller.py`  | **智能重试**：实现指数退避和 LLM 驱动的错误分析和重规划。                                         |

## 3. 关键数据结构 (Pydantic Models)

> **位置：** `memory/models.py`, `tools/models.py`, `retry/models.py`

| 模型名称               | 核心字段/目的                                                            |
| :--------------------- | :----------------------------------------------------------------------- |
| **ExecutionPlan**      | JSON 格式，定义 `intent` 和 `subtasks` 数组。驱动执行。                  |
| **Subtask**            | `description`, `tool`, `parameters`, `dependencies`。执行的基本单位。    |
| **ToolDefinition**     | `name`, `description`, `parameters` (JSON Schema)。工具的元数据。        |
| **ConversationMemory** | `messages`, `context`, `working_memory`。STM 容器。                      |
| **WorkingMemory**      | `current_task`, `tool_results`, `intermediate_steps`。任务进行中的状态。 |
| **RetryConfig**        | `max_retries`, `strategy` (EXPONENTIAL_BACKOFF)。控制重试行为。          |

## 4. 核心工作流程：任务执行 (AutoAgent.run)

这是最复杂的循环，LLM 经常需要理解它：

1.  **Prep:** Load LTM (context search) & STM (history).
2.  **Plan:** `TaskPlanner.plan()` 使用 LTM/STM/Tool Descriptions 生成 `ExecutionPlan` (JSON)。
3.  **Execute Loop:** 遍历 Subtasks。
    * 调用 `ToolRegistry.get_tool()`。
    * 使用 `RetryController.execute_with_retry()` 执行工具。
    * **Error:** 如果失败，LLM 进行错误分析 (`analyze_error`)，可能触发 `TaskPlanner.replan()`。
4.  **Finalize:** 聚合结果 (`ResultAggregator`)，生成最终响应。
5.  **Memory Update:** `STM.add_message()`，LTM 提取并存储关键事实 (`add_fact`)。

## 5. 关键实现约定

* **异步 (Async):** 框架主要依赖 `asyncio` 和 `httpx`，所有核心方法（如 `BaseTool.execute`, `TaskPlanner.plan`）都是异步 (`async def`)。
* **工具接口:** 所有工具必须继承 `BaseTool`，通过 `@property def definition` 返回其 JSON Schema。
* **Prompt 模板:** 关键提示词模板（如 `PLANNING_PROMPT`, `ERROR_ANALYSIS_PROMPT`）集中在 `llm/prompts.py`。
* **LLM 抽象:** `llm/client.py` 抽象了 LLM 客户端，支持多提供商 (OpenAI, DeepSeek, Anthropic)。