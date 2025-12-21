"""
对比基准测试

同时运行 auto_agent 和 LangChain 版本，比较执行效果

使用方法:
    cd auto_agent
    python examples/langchain_compare/benchmark.py
"""

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 添加项目根目录到 path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


@dataclass
class TokenTracker:
    """Token 追踪器"""

    steps: List[Dict[str, Any]] = field(default_factory=list)
    cumulative_tokens: int = 0

    def add_step(self, step_name: str, tokens: int):
        self.cumulative_tokens += tokens
        self.steps.append(
            {
                "step": step_name,
                "tokens": tokens,
                "cumulative": self.cumulative_tokens,
            }
        )
        print(f"   📊 Token: +{tokens:,} | 累计: {self.cumulative_tokens:,}")


# ==================== auto_agent 版本 ====================


async def run_auto_agent_version(user_query: str, materials_dir: str) -> Dict[str, Any]:
    """运行 auto_agent 版本"""
    from auto_agent import AutoAgent, OpenAIClient, ToolRegistry

    # 导入工具（从 deep_research_demo）
    from examples.deep_research_demo import (
        AnalyzeContentTool,
        GenerateReportTool,
        PolishTextTool,
        ReadMaterialsTool,
        ReflectTool,
    )

    print("\n" + "=" * 70)
    print("🔬 [auto_agent] Deep Research Agent")
    print("=" * 70)

    start_time = time.time()
    tracker = TokenTracker()

    # 初始化 LLM
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    llm_client = OpenAIClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=120.0,
    )

    # 注册工具
    registry = ToolRegistry()
    registry.register(ReadMaterialsTool(llm_client, materials_dir))
    registry.register(AnalyzeContentTool(llm_client))
    registry.register(ReflectTool(llm_client))
    registry.register(PolishTextTool(llm_client))
    registry.register(GenerateReportTool(llm_client))

    # 创建 Agent
    agent = AutoAgent(
        llm_client=llm_client,
        tool_registry=registry,
        agent_name="Deep Research Agent",
        agent_description="深度研究智能体",
    )

    # 执行
    final_report = ""
    trace_data = None
    iterations = 0
    last_cumulative = 0

    try:
        async for event in agent.run_stream(
            query=user_query,
            user_id="benchmark",
        ):
            event_type = event.get("event")
            data = event.get("data", {})

            if event_type == "stage_start":
                print(f"   ▶️ Step {data.get('step')}: {data.get('name')}")

            elif event_type == "stage_complete":
                status = "✅" if data.get("success") else "❌"
                # 从 trace 中获取当前累计 token
                step_trace = data.get("trace", {})
                step_tokens = step_trace.get("total_tokens", 0)
                if step_tokens > 0:
                    tracker.add_step(data.get("name", "unknown"), step_tokens)
                print(f"   {status} 完成")

            elif event_type == "answer":
                final_report = data.get("answer", "")

            elif event_type == "done":
                iterations = data.get("iterations", 0)
                trace_data = data.get("trace")

        end_time = time.time()

        # 提取统计
        llm_calls = 0
        total_tokens = 0
        token_steps = []
        if trace_data:
            summary = trace_data.get("summary", {})
            llm_calls = summary.get("llm_calls", {}).get("count", 0)
            total_tokens = summary.get("llm_calls", {}).get("total_tokens", 0)

            # 从 spans 提取每步 token
            spans = trace_data.get("spans", [])
            cumulative = 0
            for span in spans:
                span_tokens = span.get("total_tokens", 0)
                if span_tokens > 0:
                    cumulative += span_tokens
                    token_steps.append(
                        {
                            "step": span.get("name", "unknown"),
                            "tokens": span_tokens,
                            "cumulative": cumulative,
                        }
                    )

        # 打印 token 统计
        print(f"\n   📊 Token 消耗明细:")
        for step in token_steps:
            print(
                f"      {step['step']}: +{step['tokens']:,} (累计: {step['cumulative']:,})"
            )
        print(f"   📊 总计: {total_tokens:,} tokens")

        return {
            "success": True,
            "framework": "auto_agent",
            "output": final_report,
            "duration_ms": (end_time - start_time) * 1000,
            "iterations": iterations,
            "llm_calls": llm_calls,
            "total_tokens": total_tokens,
            "token_steps": token_steps,
        }

    except Exception as e:
        end_time = time.time()
        import traceback

        traceback.print_exc()
        return {
            "success": False,
            "framework": "auto_agent",
            "error": str(e),
            "duration_ms": (end_time - start_time) * 1000,
        }
    finally:
        await llm_client.close()


# ==================== LangChain 版本 ====================


class LangChainTokenCallback:
    """LangChain Token 回调追踪器"""

    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        self.cumulative_tokens = 0
        self.current_step = "init"

    def on_llm_end(self, tokens: int, step_name: str = None):
        step = step_name or self.current_step
        self.cumulative_tokens += tokens
        self.steps.append(
            {
                "step": step,
                "tokens": tokens,
                "cumulative": self.cumulative_tokens,
            }
        )
        print(f"   📊 Token: +{tokens:,} | 累计: {self.cumulative_tokens:,}")


async def run_langchain_version(user_query: str, materials_dir: str) -> Dict[str, Any]:
    """运行 LangChain 版本"""
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_openai import ChatOpenAI

    from examples.langchain_compare.tools import (
        analyze_content,
        init_tools,
        read_materials,
    )
    from examples.langchain_compare.tools_part2 import (
        generate_report,
        polish_text,
        reflect,
    )

    print("\n" + "=" * 70)
    print("🔬 [LangChain] Deep Research Agent")
    print("=" * 70)

    start_time = time.time()
    token_tracker = LangChainTokenCallback()

    # 自定义回调处理器
    class TokenTrackingHandler(BaseCallbackHandler):
        def __init__(self, tracker: LangChainTokenCallback):
            self.tracker = tracker
            self.step_count = 0

        def on_llm_end(self, response, **kwargs):
            # 尝试从 response 获取 token 使用量
            token_usage = getattr(response, "llm_output", {})
            if token_usage and isinstance(token_usage, dict):
                usage = token_usage.get("token_usage", {})
                total = usage.get("total_tokens", 0)
                if total > 0:
                    self.tracker.on_llm_end(total, f"llm_call_{self.step_count}")
                    self.step_count += 1

            # 备用：从 generations 获取
            if hasattr(response, "generations") and response.generations:
                for gen_list in response.generations:
                    for gen in gen_list:
                        if hasattr(gen, "generation_info") and gen.generation_info:
                            usage = gen.generation_info.get("token_usage", {})
                            total = usage.get("total_tokens", 0)
                            if total > 0:
                                self.tracker.on_llm_end(
                                    total, f"llm_call_{self.step_count}"
                                )
                                self.step_count += 1

        def on_tool_start(self, serialized, input_str, **kwargs):
            tool_name = serialized.get("name", "unknown")
            print(f"   ▶️ 调用工具: {tool_name}")

        def on_tool_end(self, output, **kwargs):
            print(f"   ✅ 工具完成")

    callback_handler = TokenTrackingHandler(token_tracker)

    # 初始化 LLM
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.7,
        timeout=120,
        callbacks=[callback_handler],
    )

    # 初始化工具
    init_tools(llm, materials_dir)
    tools = [read_materials, analyze_content, reflect, polish_text, generate_report]

    # 创建 Agent
    system_prompt = """你是一个专业的深度研究智能体。

你可以使用以下工具：
1. read_materials - 读取研究素材
2. analyze_content - 分析内容
3. reflect - 批判性反思
4. generate_report - 生成报告
5. polish_text - 语言润色

请按顺序执行研究任务，确保每一步的输出传递给下一步。"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        max_iterations=15,
        return_intermediate_steps=True,
        callbacks=[callback_handler],
    )

    try:
        result = await agent_executor.ainvoke(
            {"input": user_query},
            config={"callbacks": [callback_handler]},
        )

        end_time = time.time()

        intermediate_steps = result.get("intermediate_steps", [])

        # 打印 token 统计
        print(f"\n   📊 Token 消耗明细:")
        for step in token_tracker.steps:
            print(
                f"      {step['step']}: +{step['tokens']:,} (累计: {step['cumulative']:,})"
            )
        print(f"   📊 总计: {token_tracker.cumulative_tokens:,} tokens")

        return {
            "success": True,
            "framework": "langchain",
            "output": result.get("output", ""),
            "duration_ms": (end_time - start_time) * 1000,
            "iterations": len(intermediate_steps),
            "llm_calls": len(intermediate_steps) + 1,
            "total_tokens": token_tracker.cumulative_tokens,
            "token_steps": token_tracker.steps,
        }

    except Exception as e:
        end_time = time.time()
        import traceback

        traceback.print_exc()
        return {
            "success": False,
            "framework": "langchain",
            "error": str(e),
            "duration_ms": (end_time - start_time) * 1000,
            "total_tokens": token_tracker.cumulative_tokens,
        }


# ==================== 对比报告 ====================


def generate_comparison_report(
    auto_agent_result: Dict[str, Any],
    langchain_result: Dict[str, Any],
    output_dir: Path,
):
    """生成对比报告"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 生成 token 明细表格
    def format_token_steps(steps: List[Dict]) -> str:
        if not steps:
            return "无数据"
        lines = ["| 步骤 | Token | 累计 |", "|------|-------|------|"]
        for s in steps:
            lines.append(f"| {s['step']} | {s['tokens']:,} | {s['cumulative']:,} |")
        return "\n".join(lines)

    auto_token_table = format_token_steps(auto_agent_result.get("token_steps", []))
    lc_token_table = format_token_steps(langchain_result.get("token_steps", []))

    report = f"""# 框架对比报告

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 执行统计对比

| 指标 | auto_agent | LangChain |
|------|------------|-----------|
| 执行状态 | {"✅ 成功" if auto_agent_result.get("success") else "❌ 失败"} | {"✅ 成功" if langchain_result.get("success") else "❌ 失败"} |
| 总耗时 | {auto_agent_result.get("duration_ms", 0):.1f}ms | {langchain_result.get("duration_ms", 0):.1f}ms |
| 执行步骤 | {auto_agent_result.get("iterations", 0)} | {langchain_result.get("iterations", 0)} |
| LLM 调用次数 | {auto_agent_result.get("llm_calls", 0)} | {langchain_result.get("llm_calls", 0)} |
| Token 消耗 | {auto_agent_result.get("total_tokens", 0):,} | {langchain_result.get("total_tokens", 0):,} |

## Token 消耗明细

### auto_agent Token 明细

{auto_token_table}

### LangChain Token 明细

{lc_token_table}

## 分析

### 耗时对比
- auto_agent: {auto_agent_result.get("duration_ms", 0):.1f}ms
- LangChain: {langchain_result.get("duration_ms", 0):.1f}ms
- 差异: {abs(auto_agent_result.get("duration_ms", 0) - langchain_result.get("duration_ms", 0)):.1f}ms

### Token 对比
- auto_agent: {auto_agent_result.get("total_tokens", 0):,} tokens
- LangChain: {langchain_result.get("total_tokens", 0):,} tokens
- 差异: {abs(auto_agent_result.get("total_tokens", 0) - langchain_result.get("total_tokens", 0)):,} tokens

### 特点对比

| 特性 | auto_agent | LangChain |
|------|------------|-----------|
| 规划方式 | LLM 动态规划 | Agent 自主决策 |
| 参数传递 | 语义驱动 + state 管理 | 工具返回值传递 |
| 追踪能力 | 内置细粒度追踪 | 需额外配置 |
| Token 统计 | 自动统计 | 需手动配置 |
| 重试机制 | 内置智能重试 | 需自定义 |

---

## auto_agent 输出

```
{auto_agent_result.get("output", auto_agent_result.get("error", "无输出"))[:2000]}
```

---

## LangChain 输出

```
{langchain_result.get("output", langchain_result.get("error", "无输出"))[:2000]}
```
"""

    output_file = output_dir / f"comparison_report_{timestamp}.md"
    output_file.write_text(report, encoding="utf-8")

    print(f"\n📄 对比报告已保存: {output_file}")
    return output_file


# ==================== 主函数 ====================


async def main():
    """运行对比基准测试"""

    print("=" * 70)
    print("🏁 框架对比基准测试")
    print("=" * 70)

    # 检查环境
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("\n❌ 未设置 API Key")
        return

    # 素材目录
    script_dir = Path(__file__).parent.parent
    materials_dir = str(script_dir / "research_materials")

    if not Path(materials_dir).exists():
        print(f"\n❌ 素材目录不存在: {materials_dir}")
        print("请先运行 deep_research_demo.py 创建示例素材")
        return

    # 用户查询
    user_query = """
    请帮我做一个关于"人工智能在医疗领域的应用与伦理挑战"的深度研究。
    
    要求：
    1. 读取研究素材
    2. 分析内容，提取关键信息
    3. 进行批判性反思
    4. 生成研究报告
    5. 对报告进行润色
    """

    # 运行 auto_agent 版本
    print("\n" + "=" * 70)
    print("📌 第一轮: 运行 auto_agent 版本")
    print("=" * 70)
    auto_agent_result = await run_auto_agent_version(user_query, materials_dir)

    # 运行 LangChain 版本
    print("\n" + "=" * 70)
    print("📌 第二轮: 运行 LangChain 版本")
    print("=" * 70)
    langchain_result = await run_langchain_version(user_query, materials_dir)

    # 生成对比报告
    output_dir = script_dir / "output"
    output_dir.mkdir(exist_ok=True)

    generate_comparison_report(auto_agent_result, langchain_result, output_dir)

    # 打印摘要
    print("\n" + "=" * 70)
    print("📊 对比摘要")
    print("=" * 70)
    print(f"\n{'指标':<20} {'auto_agent':<20} {'LangChain':<20}")
    print("-" * 60)
    print(
        f"{'执行状态':<20} {'✅ 成功' if auto_agent_result.get('success') else '❌ 失败':<20} {'✅ 成功' if langchain_result.get('success') else '❌ 失败':<20}"
    )
    print(
        f"{'耗时(ms)':<20} {auto_agent_result.get('duration_ms', 0):<20.1f} {langchain_result.get('duration_ms', 0):<20.1f}"
    )
    print(
        f"{'执行步骤':<20} {auto_agent_result.get('iterations', 0):<20} {langchain_result.get('iterations', 0):<20}"
    )
    print(
        f"{'LLM调用':<20} {auto_agent_result.get('llm_calls', 0):<20} {langchain_result.get('llm_calls', 0):<20}"
    )
    print(
        f"{'Token消耗':<20} {auto_agent_result.get('total_tokens', 0):<20,} {langchain_result.get('total_tokens', 0):<20,}"
    )


if __name__ == "__main__":
    asyncio.run(main())
