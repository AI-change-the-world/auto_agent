"""
OpenAI 原生客户端版本 Deep Research Demo

与 auto_agent 版本对比，使用 OpenAI 原生 function calling 实现

使用方法:
    cd auto_agent
    python examples/langchain_compare/main.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

from openai import AsyncOpenAI

# ==================== Token 追踪 ====================


class TokenTracker:
    """Token 追踪器"""

    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        self.cumulative_tokens = 0
        self.llm_call_count = 0

    def add(self, tokens: int, step_name: str):
        self.llm_call_count += 1
        self.cumulative_tokens += tokens
        self.steps.append(
            {
                "step": step_name,
                "tokens": tokens,
                "cumulative": self.cumulative_tokens,
            }
        )
        print(f"   📊 Token: +{tokens:,} | 累计: {self.cumulative_tokens:,}")


# ==================== 工具定义 ====================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_materials",
            "description": "读取研究素材目录下的所有文件，返回文件内容。这是研究的第一步。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_types": {
                        "type": "string",
                        "description": "要读取的文件类型，用逗号分隔（如 .txt,.md）",
                        "default": ".txt,.md",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_content",
            "description": "分析研究素材内容，提取主题、论点、关键数据。这是深度研究的核心分析步骤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "研究重点/关注方向（可选）",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reflect",
            "description": "对分析结果进行批判性反思，发现逻辑问题、潜在偏见和缺失视角。",
            "parameters": {
                "type": "object",
                "properties": {
                    "depth": {
                        "type": "string",
                        "enum": ["shallow", "medium", "deep"],
                        "description": "反思深度",
                        "default": "medium",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "基于分析结果和反思意见，生成结构化的研究报告。",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "研究主题"},
                    "format": {
                        "type": "string",
                        "enum": ["brief", "standard", "detailed"],
                        "description": "报告格式",
                        "default": "standard",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "polish_text",
            "description": "对文本进行语言润色，提升表达的专业性和可读性。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "待润色的文本"},
                    "style": {
                        "type": "string",
                        "enum": ["academic", "professional", "casual"],
                        "description": "目标风格",
                        "default": "professional",
                    },
                },
                "required": ["text"],
            },
        },
    },
]


# ==================== 工具实现 ====================


class ToolExecutor:
    """工具执行器"""

    def __init__(self, client: AsyncOpenAI, materials_dir: str):
        self.client = client
        self.materials_dir = materials_dir
        self.state: Dict[str, Any] = {}  # 存储中间结果

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> str:
        """执行工具"""
        print(f"   ▶️ 执行工具: {tool_name}")

        if tool_name == "read_materials":
            return await self._read_materials(args.get("file_types", ".txt,.md"))
        elif tool_name == "analyze_content":
            return await self._analyze_content(args.get("focus", ""))
        elif tool_name == "reflect":
            return await self._reflect(args.get("depth", "medium"))
        elif tool_name == "generate_report":
            return await self._generate_report(
                args.get("topic", ""), args.get("format", "standard")
            )
        elif tool_name == "polish_text":
            return await self._polish_text(
                args.get("text", ""), args.get("style", "professional")
            )
        else:
            return json.dumps({"error": f"未知工具: {tool_name}"})

    async def _read_materials(self, file_types: str) -> str:
        """读取素材"""
        dir_path = Path(self.materials_dir)
        extensions = [ext.strip() for ext in file_types.split(",")]
        materials = []

        for file_path in dir_path.iterdir():
            if file_path.is_file() and file_path.suffix in extensions:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    materials.append(
                        {
                            "filename": file_path.name,
                            "content": content[:3000],
                            "word_count": len(content),
                        }
                    )
                except Exception as e:
                    materials.append({"filename": file_path.name, "error": str(e)})

        self.state["materials"] = materials
        result = {
            "success": True,
            "total_files": len(materials),
            "materials": materials,
        }
        print(f"   ✅ 读取了 {len(materials)} 个文件")
        return json.dumps(result, ensure_ascii=False)

    async def _analyze_content(self, focus: str) -> str:
        """分析内容"""
        materials = self.state.get("materials", [])
        if not materials:
            return json.dumps({"error": "没有可分析的素材，请先调用 read_materials"})

        # 构建素材文本
        materials_text = ""
        for m in materials:
            if "content" in m:
                materials_text += f"\n=== {m['filename']} ===\n{m['content'][:2000]}\n"

        prompt = f"""请分析以下研究素材，提取关键信息。{f"特别关注: {focus}" if focus else ""}

{materials_text}

请返回 JSON 格式的分析结果，包含: main_themes, key_arguments, knowledge_gaps, overall_insight"""

        response = await self.client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        analysis_text = response.choices[0].message.content
        self.state["analysis"] = analysis_text
        print(f"   ✅ 分析完成")
        return analysis_text

    async def _reflect(self, depth: str) -> str:
        """批判性反思"""
        analysis = self.state.get("analysis", "")
        if not analysis:
            return json.dumps({"error": "没有分析结果，请先调用 analyze_content"})

        depth_map = {
            "shallow": "快速检查",
            "medium": "中等深度批判性分析",
            "deep": "深入哲学层面反思",
        }

        prompt = f"""请对以下分析结果进行{depth_map.get(depth, "中等深度")}反思。

{analysis[:3000]}

请指出: 逻辑问题、潜在偏见、缺失视角、改进建议。返回 JSON 格式。"""

        response = await self.client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        reflection = response.choices[0].message.content
        self.state["reflection"] = reflection
        print(f"   ✅ 反思完成")
        return reflection

    async def _generate_report(self, topic: str, format: str) -> str:
        """生成报告"""
        analysis = self.state.get("analysis", "")
        reflection = self.state.get("reflection", "")

        format_map = {
            "brief": "500-800字简报",
            "standard": "1000-1500字标准报告",
            "detailed": "2000字以上详细报告",
        }

        prompt = f"""请基于以下内容生成一份{format_map.get(format, "标准")}。

主题: {topic}

分析结果:
{analysis[:2500]}

反思意见:
{reflection[:1500]}

请生成 Markdown 格式的研究报告，包含: 摘要、背景、核心发现、讨论、结论。"""

        response = await self.client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        report = response.choices[0].message.content
        self.state["report"] = report
        print(f"   ✅ 报告生成完成")
        return report

    async def _polish_text(self, text: str, style: str) -> str:
        """润色文本"""
        # 如果没传 text，用 state 中的 report
        if not text:
            text = self.state.get("report", "")
        if not text:
            return json.dumps({"error": "没有待润色的文本"})

        style_map = {
            "academic": "学术论文风格",
            "professional": "专业报告风格",
            "casual": "通俗易懂风格",
        }

        prompt = f"""请对以下文本进行语言润色，使用{style_map.get(style, "专业")}。

{text}

请直接输出润色后的完整文本。"""

        response = await self.client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        polished = response.choices[0].message.content
        self.state["polished_report"] = polished
        print(f"   ✅ 润色完成")
        return polished


# ==================== Agent 主循环 ====================


async def run_openai_agent(user_query: str, materials_dir: str) -> Dict[str, Any]:
    """运行 OpenAI Function Calling Agent"""

    print("=" * 70)
    print("🔬 OpenAI Function Calling Agent")
    print("=" * 70)

    # 初始化
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    tool_executor = ToolExecutor(client, materials_dir)
    tracker = TokenTracker()

    print(f"\n✅ 客户端初始化成功 (model: {model})")

    # 系统提示
    system_prompt = """你是一个专业的深度研究智能体。

你可以使用以下工具完成研究任务：
1. read_materials - 读取研究素材
2. analyze_content - 分析内容
3. reflect - 批判性反思
4. generate_report - 生成报告
5. polish_text - 语言润色

请按顺序执行任务，确保每一步完成后再进行下一步。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]

    print(f"\n📋 用户需求:\n{user_query.strip()}")
    print("\n" + "=" * 70)
    print("🚀 开始执行...")
    print("=" * 70)

    start_time = time.time()
    max_iterations = 15
    iteration = 0
    final_output = ""

    try:
        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- 迭代 {iteration} ---")

            # 调用 LLM
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.7,
            )

            # 记录 token
            if response.usage:
                tracker.add(response.usage.total_tokens, f"iteration_{iteration}")

            message = response.choices[0].message

            # 检查是否有工具调用
            if message.tool_calls:
                messages.append(message)

                # 执行所有工具调用
                for tool_call in message.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)

                    # 执行工具
                    result = await tool_executor.execute(func_name, func_args)

                    # 添加工具结果到消息
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result[:5000],  # 限制长度
                        }
                    )
            else:
                # 没有工具调用，说明完成了
                final_output = message.content or ""
                print(f"\n✅ Agent 完成推理")
                break

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        print("\n" + "=" * 70)
        print("✅ 执行完成!")
        print("=" * 70)

        # 统计
        print(f"\n📊 执行统计:")
        print(f"   - 迭代次数: {iteration}")
        print(f"   - LLM 调用: {tracker.llm_call_count}")
        print(f"   - Token 消耗: {tracker.cumulative_tokens:,}")
        print(f"   - 耗时: {duration_ms:.1f}ms")

        print(f"\n📊 Token 消耗明细:")
        for step in tracker.steps:
            print(
                f"      {step['step']}: +{step['tokens']:,} (累计: {step['cumulative']:,})"
            )

        return {
            "success": True,
            "output": final_output or tool_executor.state.get("polished_report", ""),
            "iterations": iteration,
            "llm_calls": tracker.llm_call_count,
            "total_tokens": tracker.cumulative_tokens,
            "token_steps": tracker.steps,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        end_time = time.time()
        print(f"\n❌ 执行失败: {e}")
        import traceback

        traceback.print_exc()

        return {
            "success": False,
            "error": str(e),
            "duration_ms": (end_time - start_time) * 1000,
            "total_tokens": tracker.cumulative_tokens,
        }


async def main():
    """主函数"""
    print("🚀 启动 OpenAI Function Calling Demo...")

    # 检查 API Key
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 未设置 API Key")
        return

    # 素材目录
    script_dir = Path(__file__).parent.parent
    materials_dir = script_dir / "research_materials"

    if not materials_dir.exists():
        print(f"❌ 素材目录不存在: {materials_dir}")
        return

    user_query = """
    请帮我做一个关于"人工智能在医疗领域的应用与伦理挑战"的深度研究。

    要求：
    1. 首先读取研究素材
    2. 分析素材内容，提取关键信息
    3. 对分析结果进行批判性反思
    4. 生成一份研究报告
    5. 最后对报告进行语言润色
    """

    result = await run_openai_agent(user_query, str(materials_dir))

    # 保存结果
    if result.get("success"):
        output_dir = script_dir / "output"
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"openai_fc_report_{timestamp}.md"

        # Token 明细
        token_detail = (
            "\n### Token 消耗明细\n\n| 步骤 | Token | 累计 |\n|------|-------|------|\n"
        )
        for step in result.get("token_steps", []):
            token_detail += (
                f"| {step['step']} | {step['tokens']:,} | {step['cumulative']:,} |\n"
            )

        output_file.write_text(
            f"""# OpenAI Function Calling 研究报告

> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> 框架: OpenAI Native Function Calling

---

{result["output"]}

---

## 执行统计

- 迭代次数: {result["iterations"]}
- LLM 调用次数: {result["llm_calls"]}
- Token 消耗: {result["total_tokens"]:,}
- 耗时: {result["duration_ms"]:.1f}ms
{token_detail}
""",
            encoding="utf-8",
        )

        print(f"\n📄 报告已保存: {output_file}")


if __name__ == "__main__":
    print("=" * 70)
    print("OpenAI Function Calling Demo")
    print("=" * 70)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
