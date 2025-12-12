# Auto-Agent 智能体框架
<p align="center">
  <img src="https://img.shields.io/badge/Version-1.0.0-blue.svg" alt="Version" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python Version" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" />
</p>

Auto-Agent 是一个基于大语言模型的自主智能体框架，提供自主规划、工具调用、记忆管理等核心能力。

## 🌟 核心特性

- 🤖 **自主规划**：基于 LLM 的任务分解和执行计划生成
- 🔧 **工具系统**：灵活的工具注册和调用机制
- 🔄 **重试机制**：智能错误处理和自动重试
- 🧠 **双层记忆**：长期记忆（用户级）+ 短期记忆（对话级）
- 📝 **结构化日志**：完整的执行过程追踪
- 🎯 **意图识别**：自动识别用户意图并路由到合适的处理流程

## 🚀 快速开始

### 环境要求

- Python 3.10+
- 支持的 LLM 提供商：OpenAI、DeepSeek、Anthropic

### 安装

```bash
pip install auto-agent
```

或者从源码安装：

```bash
git clone https://github.com/your-org/auto-agent.git
cd auto-agent
pip install -e .
```

### 基本使用

```python
from auto_agent import AutoAgent, LLMClient, ToolRegistry
from auto_agent.memory import LongTermMemory, ShortTermMemory
from auto_agent.tools.builtin import CalculatorTool, WebSearchTool

# 初始化
llm = LLMClient(provider="deepseek", api_key="sk-xxx")
tool_registry = ToolRegistry()
tool_registry.register(CalculatorTool())
tool_registry.register(WebSearchTool())

ltm = LongTermMemory(storage_path="./user_memories")
stm = ShortTermMemory(backend="sqlite", db_path="./conversations.db")

agent = AutoAgent(
    llm_client=llm,
    tool_registry=tool_registry,
    long_term_memory=ltm,
    short_term_memory=stm
)

# 执行任务
response = await agent.run(
    query="帮我计算 123 * 456，然后搜索相关的数学知识",
    user_id="user_001"
)

print(response.content)
```

## 🏗️ 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    User Input                               │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Agent Orchestrator                        │
│ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐          │
│ │ Intent      │ │ Task         │ │ Memory       │          │
│ │ Recognizer  │─▶│ Planner      │─▶│ Manager      │          │
│ └─────────────┘ └──────────────┘ └──────────────┘          │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Execution Engine                         │
│ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐          │
│ │ Tool        │ │ Retry        │ │ Result       │          │
│ │ Registry    │─▶│ Controller   │─▶│ Aggregator   │          │
│ └─────────────┘ └──────────────┘ └──────────────┘          │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     Memory System                         │
│ ┌─────────────────────┐ ┌─────────────────────┐           │
│ │ Long-term Memory    │ │ Short-term Memory   │           │
│ │ (User Profile)      │ │ (Conversation)      │           │
│ │ - Preferences       │ │ - Context           │           │
│ │ - History           │ │ - Working Memory    │           │
│ │ - Knowledge         │ │ - Temp State        │           │
│ └─────────────────────┘ └─────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

#### Agent Orchestrator（智能体编排器）
- **IntentRecognizer**：意图识别和分类
- **TaskPlanner**：任务分解和执行计划生成
- **MemoryManager**：记忆的读取和更新

#### Execution Engine（执行引擎）
- **ToolRegistry**：工具注册表和管理
- **RetryController**：重试策略和错误处理
- **ResultAggregator**：结果聚合和格式化

#### Memory System（记忆系统）
- **LongTermMemory**：持久化用户记忆
- **ShortTermMemory**：临时对话记忆

## 🧠 详细设计

### 记忆系统设计

#### 3.1.1 长期记忆（Long-term Memory）

**存储格式**：Markdown 文件（每个用户一个文件）

**文件结构**：
```markdown
# User Profile: {user_id}

## Basic Information
- User ID: {user_id}
- Created At: {timestamp}
- Last Updated: {timestamp}

## Preferences
- Language: zh-CN
- LLM Model: deepseek-v3
- Response Style: detailed/concise

## Knowledge Base
### Domain Knowledge
- [Domain 1]: {description}
- [Domain 2]: {description}

### Skills
- [Skill 1]: {proficiency}
- [Skill 2]: {proficiency}

## Interaction History
### Key Facts
- {fact_1}
- {fact_2}

### Important Decisions
- {decision_1}: {reasoning}
- {decision_2}: {reasoning}

## Custom Context
{user_defined_context}
API 设计：
class LongTermMemory:
    def load_user_memory(self, user_id: str) -> UserMemory
    def save_user_memory(self, user_id: str, memory: UserMemory)
    def update_user_memory(self, user_id: str, updates: dict)
    def search_memory(self, user_id: str, query: str) -> List[MemoryItem]
    def add_fact(self, user_id: str, fact: str, category: str)
    def get_relevant_context(self, user_id: str, task: str) -> str
```

#### 短期记忆（Short-term Memory）

存储方式：内存 + 可选持久化（SQLite/Redis） 数据结构：
```python
@dataclass
class ConversationMemory:
    conversation_id: str
    user_id: str
    messages: List[Message]
    context: Dict[str, Any]  # 临时上下文
    working_memory: Dict[str, Any]  # 工作记忆
    created_at: int
    updated_at: int
    
@dataclass
class Message:
    role: str  # user/assistant/system/tool
    content: str
    timestamp: int
    metadata: Dict[str, Any]

@dataclass
class WorkingMemory:
    current_task: Optional[Task]
    task_history: List[Task]
    tool_results: Dict[str, Any]
    intermediate_steps: List[Step]
```

API 设计：
```python
class ShortTermMemory:
    def create_conversation(self, user_id: str) -> str
    def add_message(self, conversation_id: str, message: Message)
    def get_conversation_history(self, conversation_id: str, limit: int = 10) -> List[Message]
    def get_context(self, conversation_id: str) -> Dict[str, Any]
    def update_context(self, conversation_id: str, context: dict)
    def get_working_memory(self, conversation_id: str) -> WorkingMemory
    def clear_working_memory(self, conversation_id: str)
    def summarize_conversation(self, conversation_id: str) -> str
```
### 自主规划系统

#### 任务规划流程

User Query → Intent Recognition → Task Decomposition → Tool Selection → Execution Plan

规划提示词模板：

```python
PLANNING_PROMPT = """
You are an intelligent task planner. Given a user query, you need to:
1. Understand the user's intent
2. Break down the task into subtasks
3. Select appropriate tools for each subtask
4. Generate an execution plan

User Query: {query}

Available Tools:
{tool_descriptions}

User Context (Long-term Memory):
{user_context}

Conversation Context (Short-term Memory):
{conversation_context}

Please generate a detailed execution plan in JSON format:
{{
  "intent": "...",
  "subtasks": [
    {{
      "id": 1,
      "description": "...",
      "tool": "tool_name",
      "parameters": {{}},
      "dependencies": []
    }}
  ],
  "expected_outcome": "..."
}}
"""
```

#### TaskPlanner 实现

```python
class TaskPlanner:
    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
    
    async def plan(
        self,
        query: str,
        user_context: str,
        conversation_context: str
    ) -> ExecutionPlan:
        """生成执行计划"""
        
    async def replan(
        self,
        original_plan: ExecutionPlan,
        error: Exception,
        execution_history: List[StepResult]
    ) -> ExecutionPlan:
        """根据错误重新规划"""
```
### 工具系统设计

#### 工具定义标准

```python
from typing import Any, Dict, List, Optional, Callable
from pydantic import BaseModel, Field

class ToolParameter(BaseModel):
    name: str
    type: str  # string, number, boolean, object, array
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[Any]] = None

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: List[ToolParameter]
    returns: Dict[str, Any]
    category: str  # retrieval, analysis, action, etc.
    examples: List[Dict[str, Any]] = []

class BaseTool:
    """工具基类"""
    
    @property
    def definition(self) -> ToolDefinition:
        """返回工具定义"""
        raise NotImplementedError
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具"""
        raise NotImplementedError
    
    async def validate_input(self, **kwargs) -> bool:
        """验证输入参数"""
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """返回 JSON Schema"""
        return self.definition.dict()
```
#### 工具注册表

```python
class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[str, List[str]] = {}
    
    def register(self, tool: BaseTool):
        """注册工具"""
        
    def unregister(self, tool_name: str):
        """注销工具"""
        
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取工具"""
        
    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """按类别获取工具"""
        
    def get_all_tools(self) -> List[BaseTool]:
        """获取所有工具"""
        
    def get_tool_descriptions(self) -> str:
        """获取所有工具的描述（用于提示词）"""
```
### 重试机制设计

#### 重试策略

```python
from enum import Enum
from typing import Optional, Callable

class RetryStrategy(Enum):
    IMMEDIATE = "immediate"  # 立即重试
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 指数退避
    LINEAR_BACKOFF = "linear_backoff"  # 线性退避
    ADAPTIVE = "adaptive"  # 自适应（基于 LLM）

class RetryConfig(BaseModel):
    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0  # 秒
    max_delay: float = 60.0
    backoff_factor: float = 2.0
    retry_on_exceptions: List[type] = []
    should_retry_callback: Optional[Callable] = None

class RetryController:
    def __init__(self, config: RetryConfig, llm_client: Optional[LLMClient] = None):
        self.config = config
        self.llm_client = llm_client
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """带重试的执行"""
        
    async def should_retry(
        self,
        exception: Exception,
        attempt: int,
        context: Dict[str, Any]
    ) -> bool:
        """判断是否应该重试"""
        
    async def analyze_error(
        self,
        exception: Exception,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用 LLM 分析错误"""
        
    def get_delay(self, attempt: int) -> float:
        """计算延迟时间"""
```
#### 智能重试（基于 LLM）

```python
ERROR_ANALYSIS_PROMPT = """
An error occurred during task execution. Please analyze the error and provide suggestions.

Error Type: {error_type}
Error Message: {error_message}
Stack Trace: {stack_trace}

Task Context:
- Task: {task_description}
- Tool: {tool_name}
- Parameters: {parameters}
- Attempt: {attempt}/{max_retries}

Execution History:
{execution_history}

Please analyze:
1. Is this error recoverable?
2. What might be the root cause?
3. Should we retry? If yes, any parameter adjustments needed?
4. Alternative approaches?

Respond in JSON format:
{{
  "is_recoverable": true/false,
  "root_cause": "...",
  "should_retry": true/false,
  "suggested_changes": {{
    "parameters": {{}},
    "alternative_tool": "..."
  }},
  "reasoning": "..."
}}
"""
```
### Agent 执行流程

```python
class AutoAgent:
    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        long_term_memory: LongTermMemory,
        short_term_memory: ShortTermMemory,
        retry_config: Optional[RetryConfig] = None
    ):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.ltm = long_term_memory
        self.stm = short_term_memory
        self.planner = TaskPlanner(llm_client, tool_registry)
        self.retry_controller = RetryController(retry_config or RetryConfig())
    
    async def run(
        self,
        query: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        stream: bool = False
    ) -> AgentResponse:
        """
        执行流程：
        1. 加载用户长期记忆
        2. 加载或创建对话短期记忆
        3. 意图识别
        4. 任务规划
        5. 执行计划（带重试）
        6. 结果聚合
        7. 更新记忆
        8. 返回响应
        """
        
        # Step 1: Load memories
        user_context = self.ltm.get_relevant_context(user_id, query)
        
        if not conversation_id:
            conversation_id = self.stm.create_conversation(user_id)
        
        conversation_context = self.stm.get_context(conversation_id)
        
        # Step 2: Add user message
        self.stm.add_message(conversation_id, Message(
            role="user",
            content=query,
            timestamp=int(time.time()),
            metadata={}
        ))
        
        # Step 3: Plan
        plan = await self.planner.plan(
            query=query,
            user_context=user_context,
            conversation_context=conversation_context
        )
        
        # Step 4: Execute with retry
        results = []
        for subtask in plan.subtasks:
            try:
                result = await self.retry_controller.execute_with_retry(
                    self._execute_subtask,
                    subtask=subtask,
                    conversation_id=conversation_id
                )
                results.append(result)
            except Exception as e:
                # Replan if needed
                plan = await self.planner.replan(plan, e, results)
                # Continue or abort based on replan
        
        # Step 5: Aggregate results
        final_response = await self._aggregate_results(results, plan)
        
        # Step 6: Update memories
        self.stm.add_message(conversation_id, Message(
            role="assistant",
            content=final_response,
            timestamp=int(time.time()),
            metadata={"plan": plan.dict(), "results": results}
        ))
        
        # Step 7: Extract and save important facts to LTM
        await self._update_long_term_memory(user_id, conversation_id, plan, results)
        
        return AgentResponse(
            content=final_response,
            conversation_id=conversation_id,
            plan=plan,
            execution_results=results
        )
```
## 📁 目录结构

```
auto-agent/
├── auto_agent/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py              # AutoAgent 主类
│   │   ├── orchestrator.py       # 编排器
│   │   ├── planner.py            # 任务规划器
│   │   └── executor.py           # 执行引擎
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── base.py               # 记忆基类
│   │   ├── long_term.py          # 长期记忆
│   │   ├── short_term.py         # 短期记忆
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── markdown.py       # Markdown 存储
│   │   │   ├── sqlite.py         # SQLite 存储
│   │   │   └── redis.py          # Redis 存储
│   │   └── models.py             # 记忆数据模型
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py               # 工具基类
│   │   ├── registry.py           # 工具注册表
│   │   ├── builtin/              # 内置工具
│   │   │   ├── __init__.py
│   │   │   ├── calculator.py
│   │   │   ├── web_search.py
│   │   │   └── code_executor.py
│   │   └── models.py             # 工具数据模型
│   ├── retry/
│   │   ├── __init__.py
│   │   ├── controller.py         # 重试控制器
│   │   ├── strategies.py         # 重试策略
│   │   └── models.py             # 重试配置模型
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py             # LLM 客户端抽象
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   ├── openai.py
│   │   │   ├── deepseek.py
│   │   │   └── anthropic.py
│   │   └── prompts.py            # 提示词模板
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py             # 日志工具
│   │   ├── serialization.py      # 序列化工具
│   │   └── validators.py         # 验证工具
│   └── models.py                 # 公共数据模型
├── tests/
│   ├── __init__.py
│   ├── test_agent.py
│   ├── test_memory.py
│   ├── test_tools.py
│   └── test_retry.py
├── examples/
│   ├── basic_usage.py
│   ├── custom_tool.py
│   ├── memory_demo.py
│   └── advanced_planning.py
├── docs/
│   ├── index.md
│   ├── quickstart.md
│   ├── concepts.md
│   ├── api_reference.md
│   └── examples.md
├── pyproject.toml
├── setup.py
├── README.md
├── LICENSE
└── .gitignore
```
## 🛠️ 技术栈

- **Python**: 3.10+
- **核心依赖**:
  - `pydantic`: 数据验证
  - `asyncio`: 异步编程
  - `httpx`: HTTP 客户端
  - `tenacity`: 重试库（可选，也可自己实现）
- **存储**:
  - `aiosqlite`: SQLite 异步支持
  - `redis`: Redis 客户端
  - 文件系统（Markdown）
- **LLM**:
  - `openai`: OpenAI SDK
  - 支持兼容 OpenAI API 的其他提供商
- **日志**:
  - `loguru`: 强大的日志库
## 📖 使用示例

### 基础使用

```python
from auto_agent import AutoAgent, LLMClient, ToolRegistry
from auto_agent.memory import LongTermMemory, ShortTermMemory
from auto_agent.tools.builtin import CalculatorTool, WebSearchTool

# 初始化
llm = LLMClient(provider="deepseek", api_key="sk-xxx")
tool_registry = ToolRegistry()
tool_registry.register(CalculatorTool())
tool_registry.register(WebSearchTool())

ltm = LongTermMemory(storage_path="./user_memories")
stm = ShortTermMemory(backend="sqlite", db_path="./conversations.db")

agent = AutoAgent(
    llm_client=llm,
    tool_registry=tool_registry,
    long_term_memory=ltm,
    short_term_memory=stm
)

# 执行任务
response = await agent.run(
    query="帮我计算 123 * 456，然后搜索相关的数学知识",
    user_id="user_001"
)

print(response.content)
```
### 自定义工具

```python
from auto_agent.tools import BaseTool, ToolDefinition, ToolParameter

class CustomTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="custom_tool",
            description="My custom tool",
            parameters=[
                ToolParameter(
                    name="input",
                    type="string",
                    description="Input data",
                    required=True
                )
            ],
            returns={"type": "object"},
            category="custom"
        )
    
    async def execute(self, input: str) -> dict:
        # Your implementation
        return {"result": f"Processed: {input}"}

# 注册
tool_registry.register(CustomTool())
```
### 长期记忆管理

```python
# 更新用户偏好
ltm.update_user_memory("user_001", {
    "preferences": {
        "language": "zh-CN",
        "response_style": "detailed"
    }
})

# 添加知识
ltm.add_fact(
    user_id="user_001",
    fact="用户是一名 Python 开发者，擅长 FastAPI 和异步编程",
    category="skills"
)

# 获取相关上下文
context = ltm.get_relevant_context(
    user_id="user_001",
    task="帮我写一个 FastAPI 接口"
)
```

## 🤝 贡献指南

我们欢迎社区贡献！如果您想为 Auto-Agent 做出贡献，请遵循以下步骤：

1. Fork 项目仓库
2. 创建您的功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交您的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 开发环境设置

```bash
git clone https://github.com/your-org/auto-agent.git
cd auto-agent
pip install -e ".[dev]"
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_agent.py
```

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 联系我们

- 项目维护者: Auto-Agent Team
- GitHub Issues: [https://github.com/your-org/auto-agent/issues](https://github.com/your-org/auto-agent/issues)
- 邮箱: team@example.com

---

<div align="center">
  <strong>🚀 使用 Auto-Agent 构建下一代智能应用!</strong>
</div>