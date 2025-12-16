# 智能体记忆系统设计方案（正式版）

> 本方案用于设计一套**可介绍、可落地、可演进的智能体记忆系统**，面向具备长期运行能力的 Agent / 多 Agent 系统，重点解决：
>
> * 记忆可控注入（避免上下文爆炸）
> * 记忆可学习（用户反馈驱动优化）
> * 记忆可管理（分类、衰减、冲突处理）
> * 兼顾工程结构化与大模型语义理解

---

## 一、设计背景与问题定义

在长期运行的智能体系统中，**记忆不应等同于对话历史**。

若简单将所有历史信息拼接进上下文，将导致：

* Token 成本失控
* 关键信息被噪声淹没
* 模型行为不稳定、不可学习

因此，需要一套：

> **可分类、可筛选、可反馈更新的记忆交互机制**，
> 并将“是否使用记忆”的决策权前移到系统层，而非完全依赖大模型推理。

---

## 二、总体设计原则

1. **分层而非堆叠**：不同生命周期的记忆必须隔离管理
2. **结构化优先**：所有可被学习和优化的记忆必须结构化存储
3. **按需注入**：记忆只在“相关且必要”时进入上下文
4. **反馈闭环**：用户反馈直接作用于记忆权重与策略
5. **人机双友好**：既服务系统决策，也支持人类理解与调试

---

## 三、记忆分层设计（Memory Layers）

### 3.1 L1：短时记忆（Working / Episodic Memory）

**定位**：单次 Agent 执行过程中的上下文状态

* 内容包括：

  * 当前 Query
  * 子任务拆解结果
  * 中间决策与工具调用
* 生命周期：

  * 默认仅在一次任务内有效
  * 任务结束后被丢弃或提炼

**用途**：

* 保证 Agent 内部推理连续性
* 为长期记忆提炼提供原材料

---

### 3.2 L2：长期语义记忆（Semantic Memory，主存储）

**定位**：系统长期可复用、可学习的核心记忆层

* 存储形式：**JSON（强结构化）**
* 必须支持：

  * 分类与标签
  * 打分与权重
  * 时间衰减
  * 用户反馈更新

**推荐一级分类（示例）：**

* work：工作 / 技术 / 业务相关
* life：生活经验 / 日常事实
* preference：用户或 Agent 偏好
* emotion：态度、情感倾向
* strategy：方法论、成功/失败策略

---

### 3.3 L3：叙事与反思记忆（Narrative / Reflection Memory）

**定位**：对长期记忆的语义压缩与自我认知表达

* 存储形式：**Markdown（自然语言）**
* 来源：

  * L2 记忆的自动总结
  * 多次经验的抽象反思

**用途**：

* Prompt 注入（高语义密度）
* 人类理解与调试
* Agent 行为风格与长期一致性塑造

> 注：L3 记忆不独立决策，必须由 L2 记忆引用与约束。

---

## 四、JSON 与 Markdown 协作策略

### 4.1 JSON：记忆的“决策与索引层”

所有长期记忆必须有 JSON 主记录，用于系统层决策：

```json
{
  "memory_id": "mem_20251214_001",
  "layer": "L2",
  "category": "work",
  "subcategory": "agent_design",
  "tags": ["memory", "architecture"],
  "content": "用户倾向于使用分层记忆以控制 token 使用",
  "confidence": 0.9,
  "reward": 1,
  "source": "user_feedback",
  "created_at": "2025-12-14",
  "summary_md_ref": "reflections/mem_20251214_001.md"
}
```

JSON 负责：

* 是否命中
* 是否注入上下文
* 注入优先级判断
* 学习与权重更新

---

### 4.2 Markdown：记忆的“语义表达层”

Markdown 以自然语言形式表达记忆含义，用于模型理解与人工查看：

```markdown
# Reflection: Memory Routing Strategy

通过先判断 Query 的领域，再定向检索对应分类记忆，
可以在显著降低上下文长度的同时，保持回答稳定性与一致性。
```

Markdown 特点：

* 高语义密度
* 强可读性
* 不参与直接决策

---

## 五、记忆交互流程设计

### 5.1 Query → 记忆命中流程

**步骤说明：**

1. Query 进入系统
2. 轻量分析 Query：

   * 意图类型（询问 / 决策 / 反思）
   * 领域分类（work / life / preference / emotion）
3. 确定所需记忆层级与分类
4. 仅在相关 L2 记忆子集中检索
5. 按权重、时间衰减排序
6. Top-K 命中记忆转为文本或 Markdown 注入上下文

> 该流程避免“全量记忆注入”，从源头控制 Token 使用。

---

### 5.2 Agent 执行阶段的短时记忆管理

* 记录关键中间决策（L1）
* 标记：

  * 复用的历史记忆
  * 新产生的潜在知识

---

## 六、用户反馈与记忆更新机制

### 6.1 用户反馈设计

* 支持简单反馈形式：

  * 👍 / 👎
  * 或 1～5 分
* 可选文本说明原因

---

### 6.2 反馈驱动的记忆更新策略

* 正反馈：

  * 提升相关 L2 记忆的 reward / confidence
* 负反馈：

  * 降低权重
  * 标记为 `needs_revision`

该机制可直接作为：

* 偏好学习
* DPO 正负样本来源

---

### 6.3 短时记忆向长期记忆的提炼

* 从 L1 中抽取：

  * 成功策略
  * 失败原因
* 生成新的 L2 JSON 记忆
* 自动生成或更新对应的 Markdown 反思（L3）

---

## 七、上下文与 Token 控制策略

* 每次调用前计算可用 Token 预算
* 记忆注入优先级：

  1. 明确命中的偏好与约束
  2. 高 reward 的策略记忆
  3. 最近且相关的经验
* 超预算时：

  * 丢弃低权重记忆
  * 使用 Markdown Summary 替代原始内容

---

## 八、错误恢复记忆集成

### 8.1 错误恢复策略记忆化

智能重试系统与记忆系统深度集成，将成功的错误恢复策略记录到 L2 语义记忆中，实现从失败中学习。

错误恢复策略作为 `SemanticMemoryItem` 存储，遵循现有的记忆系统架构：

**存储结构：**

```
{storage_path}/
└── {user_id}/
    ├── memory.json                           # 索引文件（包含错误恢复策略的元数据）
    └── reflections/
        └── mem_20251216_abc12345.md          # 错误恢复策略的详细内容
```

**JSON 索引层（memory.json 中的一条记录）：**

```json
{
  "memory_id": "mem_20251216_abc12345",
  "layer": "L2",
  "category": "strategy",
  "subcategory": "error_recovery",
  "tags": ["error_recovery", "tool:search_documents", "error:ValueError"],
  "content": "工具 search_documents 遇到 ValueError 错误时，通过修正 query 成功恢复",
  "confidence": 0.7,
  "reward": 0.0,
  "source": "task_result",
  "created_at": 1734345600,
  "updated_at": 1734345600,
  "access_count": 0,
  "summary_md_ref": "reflections/mem_20251216_abc12345.md",
  "metadata": {
    "category": "error_recovery",
    "error_type": "ValueError",
    "tool_name": "search_documents",
    "fix_pattern": {
      "original": {"query": ""},
      "fixed": {"query": "用户输入的搜索词"}
    },
    "success": true
  },
  "needs_revision": false
}
```

**Markdown 内容层（reflections/mem_20251216_abc12345.md）：**

```markdown
---
memory_id: mem_20251216_abc12345
category: strategy
tags: ["error_recovery", "tool:search_documents", "error:ValueError"]
created_at: 2025-12-16 10:00:00
---

# 错误恢复策略: search_documents

## 错误信息
- **错误类型**: ValueError
- **错误消息**: 参数 'query' 不能为空

## 原始参数
\`\`\`json
{
  "query": "",
  "limit": 10
}
\`\`\`

## 修正后参数
\`\`\`json
{
  "query": "用户输入的搜索词",
  "limit": 10
}
\`\`\`

## 修正说明
- \`query\`: \`\` → \`用户输入的搜索词\`
```

**设计说明：**

- **content**：简短摘要，用于检索和决策（存入 JSON 索引）
- **detail_content**：详细的 Markdown 内容，供模型理解和人工查看
- **metadata**：结构化的恢复策略数据，用于后续查询匹配
- **tags**：包含 `error_recovery`、`tool:{name}`、`error:{type}` 便于精确检索

### 8.2 历史策略优先查询

当工具执行失败时，系统会优先查询记忆中的历史恢复策略：

1. **构建搜索查询**：基于错误类型和工具名称
2. **匹配分数计算**：
   - 错误类型匹配：+0.5
   - 工具名称匹配：+0.3
   - 错误消息相似度：+0.2
3. **排序优先级**：匹配分数 > 置信度 > 使用次数
4. **策略应用**：直接使用历史成功的参数修正方案

**查询流程：**

```
执行失败
    │
    ▼
┌─────────────────────────┐
│ 搜索 L2 记忆            │
│ category: strategy      │
│ subcategory: error_recovery │
│ tags: error:{type}, tool:{name} │
└───────────┬─────────────┘
            │
            ▼
    ┌───────────────┐
    │ 计算匹配分数  │
    └───────┬───────┘
            │
            ▼
    ┌───────────────┐
    │ 有高分匹配？  │
    └───────┬───────┘
            │
      ┌─────┴─────┐
     是          否
      │           │
      ▼           ▼
  使用历史    LLM 分析
  策略重试    生成新策略
```

### 8.3 策略学习闭环

成功的错误恢复会触发策略学习：

1. **记录恢复策略**：将成功的参数修正记录到 L2
2. **更新置信度**：重复成功使用会提升策略置信度
3. **反馈驱动**：用户反馈可调整策略权重
4. **自动清理**：长期未使用的低置信度策略会被清理

**代码示例：**

```python
from auto_agent.retry import RetryController
from auto_agent import MemorySystem

memory = MemorySystem(storage_path="./data/memory")
retry_controller = RetryController(config=config, llm_client=llm)

# 执行失败时，优先查询历史策略
error_analysis = await retry_controller.analyze_error(
    exception=e,
    context={"state": state, "arguments": args},
    tool_definition=tool.definition,
    memory_system=memory,  # 启用历史策略查询
    user_id="user_001",
)

# 如果有历史策略，error_analysis.reasoning 会包含 "使用历史恢复策略"
# 如果没有，则使用 LLM 分析

# 成功恢复后，记录策略
if recovery_successful:
    await retry_controller.record_successful_recovery(
        original_error=e,
        tool_name="search_documents",
        original_params=original_args,
        fixed_params=fixed_params,
        memory_system=memory,
        user_id="user_001",
    )
```

### 8.4 与 L3 叙事记忆的关联

当错误恢复策略积累足够时，可以生成 L3 叙事总结：

```python
# 生成错误恢复经验总结
reflection = memory.generate_reflection(
    user_id="user_001",
    title="工具执行错误恢复经验",
    category=MemoryCategory.STRATEGY,
)
```

生成的 Markdown 总结示例：

```markdown
# 工具执行错误恢复经验

## 常见错误模式

1. **参数缺失错误**：通常可以从执行状态中提取正确值
2. **网络超时错误**：使用指数退避重试通常有效
3. **权限错误**：需要检查配置，通常不可自动恢复

## 成功策略

- search_documents 工具的 query 参数错误：从 state['inputs']['query'] 获取
- api_call 工具的超时错误：增加 timeout 参数到 30 秒
```

---

## 九、可扩展与演进方向

* 记忆冲突检测与合并
* 时间衰减与自动清理
* 多 Agent 记忆共享 / 隔离策略
* 更高级的策略学习（DPO / RL）
* 跨工具的错误恢复模式学习
* 基于记忆的预测性错误预防

---

## 九、总结

> **本记忆系统的核心思想是：**
>
> * 用结构化记忆支撑系统决策与学习
> * 用自然语言记忆服务模型理解与人类协作
> * 通过反馈形成持续演进的智能体行为闭环
