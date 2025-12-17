## Auto-Agent 优化方案（聚焦：记忆闭环 + 可观测性）

## 📌 范围与原则

本方案只覆盖 **当前代码已具备的能力链路**，并把“能一步步落地、能验收”放在第一位。

- **目标**：让记忆“更准、更可控、更可解释”；让系统“从失败中学习形成复用”；让执行过程“可调试、可定位”。
- **非目标（当前不做）**：多智能体编队、工具市场、复杂知识图谱/多模态（除非出现明确需求与验收标准）。

## ✅ 当前实现概览（基于现有代码）

- **L2 语义记忆**：`auto_agent/memory/semantic.py`
  - JSON 索引 + Markdown 详情（可选）
  - 支持 `category/subcategory/tags`、`reward/confidence`、时间衰减、关键词检索、L1→L2 提炼
- **记忆路由与注入**：`auto_agent/memory/router.py` + `auto_agent/memory/system.py`
  - 可选 LLM 分析 query、token_budget 控制、可选总结（summarize）
  - 输出 `context + memories + analysis + token_estimate`
- **智能重试**：`auto_agent/retry/controller.py`
  - 错误分析、参数修复建议、（可选）记录成功恢复策略
- **追踪与报告**：`auto_agent/tracing/*` + `auto_agent/core/report/*`
  - 已有 tracing 事件模型与示例输出（`examples/deep_research_demo.py`）

## 🔍 当前主要痛点（能力层）

1. **记忆命中/排序/解释不足**
   - L2 检索以关键词为主，中文场景下召回/排序可提升
   - 注入“为什么是这些记忆”不透明，调参困难
   - token_budget 有了，但缺少统一的“裁剪/优先级策略”

2. **学习闭环还不够“可复用”**
   - 有 `thumbs_up/down` 与 reward/confidence，但缺少对“策略”（尤其是错误恢复）的标准化沉淀与复用评估

3. **可观测性偏“记录”，缺少“解释”**
   - 有 tracing，但报告/输出缺少面向调试的关键解释：为何注入、为何重试、修参差异、为何重规划

## 🧭 任务分类与执行策略（新增）

目的：对用户任务做**复杂度/不确定性分类**，从而决定执行策略（是否需要更强的反思/重规划），避免“一刀切”导致成本过高或效果不稳定。

### 分类维度（建议先做轻量规则，后续可引入 LLM 辅助）

- **复杂度（Complexity）**
  - 低：单步可回答；或 1～2 个工具调用即可完成
  - 中：需要多步工具链，但依赖关系简单
  - 高：需要长链路、多轮推理、或多个可替代路径（例如写代码、写长文、深度研究）
- **工具完备度（Tool readiness）**
  - 完备：所需工具存在且参数明确
  - 不完备：工具缺失/不确定/参数映射困难
- **结果可验证性（Verifiability）**
  - 强：可用结构化校验/单元测试/确定性指标验证
  - 弱：主观质量为主（写作风格、观点组织等）
- **风险与成本（Risk/Cost）**
  - 低：失败代价小，可快速重试
  - 高：失败会导致大面积返工（代码/长文/长链路研究）

### 策略矩阵（最小可落地版本）

| 任务类型 | 推荐策略 | 重规划（replan） | 反思（reflection） | 备注 |
|---|---|---:|---:|---|
| 简单问题（低复杂度、工具完备、强可验证） | **顺序执行** | 关闭/极少 | 关闭 | 例如：简单问答、单工具查询 |
| 工具链任务（中复杂度、工具完备） | **顺序执行 + 失败重试** | 低 | 可选（失败后） | 主要依赖 RetryController |
| 复杂任务（高复杂度 或 工具不完备 或 弱可验证） | **分阶段执行 + 关键点检查 + 允许重规划** | 高 | 开启（阶段结束/失败后） | 例如：写代码、长文、深度研究 |

### 具体落地点（建议）

- **新增 TaskProfile（任务画像）**
  - 输出字段：`complexity/tool_readiness/verifiability/risk` + `recommended_strategy`
  - 存放位置建议：`ExecutionPlan` 的 metadata，或 `ExecutionContext` 的 analysis
- **执行策略开关**
  - `allow_replan`: bool（是否允许重规划）
  - `reflection_mode`: none / on_fail / per_stage（反思频率）
  - `max_replans`: int（防止无限循环）
- **可观测性要求**
  - tracing/report 中必须记录：任务分类结果 + 采用的策略开关（方便调参）

## 🗺️ 里程碑

### M0：基线与一致性

- **做什么**
  - 建一个最小 benchmark：10～20 条 query + 期望命中的 category/tag/关键记忆
  - **文档/示例一致性**：README/示例只引用“当前架构能跑通”的入口（避免旧接口混入）
- **验收**
  - benchmark 可一键运行并输出当前命中结果与 token_estimate

### M1：记忆检索与注入质量

- **做什么**
  - **检索打分改进**（仍保持轻量）：对 `content/tags/subcategory` 分字段加权；改善中文 tokenization（至少做更合理的分词/切分）
  - **注入解释输出**：在 `MemorySystem.get_context_for_query` / `MemoryRouter.route` 返回 `debug` 字段：
    - top-k 命中列表、每条得分、命中词、时间衰减贡献、裁剪原因
  - **预算裁剪策略**：定义优先级（如 preference > strategy > knowledge），超预算时有确定性裁剪规则
- **验收**
  - benchmark 上 top-1/top-3 命中率提升（你可以设一个目标，比如 +20%）
  - 每次注入都能输出“为什么选这些记忆”的解释（可读、可定位）

### M1.5：任务分类 → 执行策略选择（新增）

- **做什么**
  - 先实现“轻量规则版”的任务分类（基于关键词/长度/工具可用性/可验证性信号）
  - 为执行引擎引入策略开关：`allow_replan/reflection_mode/max_replans`
  - 在 tracing/report 中输出：TaskProfile + 策略选择结果
- **验收**
  - 简单任务不再触发 replan（除非明确失败）
  - 复杂任务在关键失败/阶段结束时能触发 replan，并且有上限防止循环
  - 同一批样例任务中：总 LLM 调用数下降或稳定，复杂任务成功率提升

### M2：策略学习闭环

- **做什么**
  - 标准化“策略记忆”结构（建议方向）：
    - `category=strategy`
    - `subcategory=error_recovery`
    - `metadata` 包含 `tool_name/error_type/fix_pattern/conditions`
  - 重试时优先查询历史策略（命中则减少 LLM 试错）
  - 增加策略效果统计：复用次数、成功率；低效策略标记 `needs_revision`
- **验收**
  - 同类错误复现时：平均重试次数下降、LLM 调用次数下降、成功率不降低

### M3：面向调试的可观测性

- **做什么**
  - 定义“调试必需事件”输出规范：plan、tool_call、retry、memory_injection（字段稳定）
  - 报告增强（Markdown/HTML）：新增三个小节
    - 记忆注入：top-k + 解释（来自 debug）
    - 重试修参：参数 diff + 采用理由
    - 重规划：触发原因 + 新旧计划差异（如有）
- **验收**
  - 一次运行不看源码也能从报告定位：注入了什么/为什么、哪里失败、如何修复、为何重规划

## 📎 备注：关于“图谱/多模态”

这类能力很容易把项目带入“设计重、落地慢”的状态。建议先把 **文本场景的检索质量、学习闭环、可观测性**做扎实；只有当出现明确需求与可量化验收时，再引入更重的表示（比如向量检索/图结构/多模态）。

