"""
完整功能演示

测试内容:
1. LLM 真实调用和问答效果
2. 自动上下文压缩
3. 会话管理和多轮对话
4. 意图路由
5. 分类记忆系统
6. 执行报告生成
"""

import asyncio
import os
from typing import Any, Dict

from auto_agent import (
    BaseTool,
    CategorizedMemory,
    ExecutionPlan,
    ExecutionReportGenerator,
    IntentRouter,
    OpenAIClient,
    PlanStep,
    SessionManager,
    ShortTermMemory,
    SubTaskResult,
    ToolDefinition,
    ToolParameter,
)

# ==================== 配置 ====================


def get_llm_client():
    """获取 LLM 客户端"""
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 未设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY")
        print("   请设置环境变量后重试")
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("OPENAI_MODEL", "deepseek-chat")

    return OpenAIClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=120.0,
    )


# ==================== 测试工具 ====================


class AnalyzeInputTool(BaseTool):
    """分析用户输入工具 - 使用 LLM"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze_input",
            description="分析用户输入，识别意图、主题和关键信息",
            parameters=[
                ToolParameter(
                    name="query", type="string", description="用户输入", required=True
                ),
            ],
            category="analysis",
        )

    async def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        if not self.llm_client:
            return {"success": False, "error": "LLM client not available"}

        prompt = f"""分析以下用户输入，提取关键信息。

用户输入: {query}

请返回 JSON 格式:
{{
    "intent": "用户意图（如：写作、查询、分析等）",
    "topic": "主题",
    "keywords": ["关键词1", "关键词2"],
    "document_type": "文档类型（如：报告、笔记、总结等）"
}}"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}], temperature=0.3
            )

            import json
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                result["success"] = True
                return result

            return {
                "success": True,
                "intent": "写作",
                "topic": query[:50],
                "keywords": [],
                "raw_response": response,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class SearchTool(BaseTool):
    """模拟搜索工具 - 返回大量数据用于测试压缩"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_documents",
            description="搜索相关文档",
            parameters=[
                ToolParameter(
                    name="query", type="string", description="搜索查询", required=True
                ),
                ToolParameter(
                    name="size", type="integer", description="返回数量", required=False
                ),
            ],
            category="retrieval",
        )

    async def execute(self, query: str, size: int = 10, **kwargs) -> Dict[str, Any]:
        # 模拟返回大量文档数据（用于测试压缩）
        documents = []
        for i in range(size):
            documents.append(
                {
                    "id": f"doc_{i}",
                    "title": f"文档{i}: 关于{query}的研究",
                    "content": f"这是一篇关于{query}的详细文档内容。" * 50,  # 大量内容
                    "author": f"作者{i}",
                    "date": "2024-01-01",
                    "score": 0.95 - i * 0.05,
                    "metadata": {
                        "category": "研究",
                        "tags": ["AI", "技术", query],
                        "word_count": 5000 + i * 100,
                    },
                }
            )

        return {
            "success": True,
            "document_ids": [d["id"] for d in documents],
            "documents": documents,
            "total_count": len(documents),
            "query": query,
        }


class GenerateOutlineTool(BaseTool):
    """大纲生成工具 - 使用 LLM"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate_outline",
            description="根据主题生成文档大纲",
            parameters=[
                ToolParameter(
                    name="topic", type="string", description="文档主题", required=True
                ),
                ToolParameter(
                    name="doc_type",
                    type="string",
                    description="文档类型",
                    required=False,
                ),
            ],
            category="document",
        )

    async def execute(
        self, topic: str, doc_type: str = "报告", **kwargs
    ) -> Dict[str, Any]:
        if not self.llm_client:
            return {"success": False, "error": "LLM client not available"}

        prompt = f"""为以下主题生成一个{doc_type}的大纲。

主题: {topic}

请返回 JSON 格式的大纲:
{{
    "title": "文档标题",
    "sections": [
        {{"title": "章节标题", "subsections": ["小节1", "小节2"]}}
    ]
}}"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}], temperature=0.5
            )

            import json
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                outline = json.loads(json_match.group())
                return {"success": True, "outline": outline}

            return {
                "success": True,
                "outline": {
                    "title": f"关于{topic}的{doc_type}",
                    "sections": [{"title": "概述", "subsections": []}],
                },
                "raw_response": response,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class ComposeDocumentTool(BaseTool):
    """文档撰写工具 - 使用 LLM"""

    def __init__(self, llm_client):
        self.llm_client = llm_client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="compose_document",
            description="根据大纲撰写文档",
            parameters=[
                ToolParameter(
                    name="outline", type="object", description="文档大纲", required=True
                ),
                ToolParameter(
                    name="context",
                    type="string",
                    description="参考上下文",
                    required=False,
                ),
            ],
            category="document",
        )

    async def execute(
        self, outline: Dict, context: str = "", **kwargs
    ) -> Dict[str, Any]:
        if not self.llm_client:
            return {"success": False, "error": "LLM client not available"}

        title = outline.get("title", "未命名文档")
        sections = outline.get("sections", [])

        prompt = f"""根据以下大纲撰写文档内容。

标题: {title}
大纲: {sections}

参考信息: {context[:500] if context else "无"}

请直接输出 Markdown 格式的文档内容，包含标题和各章节。"""

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}], temperature=0.7, max_tokens=2000
            )

            return {
                "success": True,
                "document": {
                    "title": title,
                    "content": response,
                    "word_count": len(response),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# ==================== 测试函数 ====================


async def test_llm_basic(llm_client):
    """测试 1: LLM 基础问答"""
    print("\n" + "=" * 60)
    print("🧪 测试 1: LLM 基础问答")
    print("=" * 60)

    questions = [
        "什么是人工智能？用一句话回答。",
        "Python 和 Java 的主要区别是什么？简要回答。",
    ]

    for q in questions:
        print(f"\n❓ 问题: {q}")
        try:
            response = await llm_client.chat(
                [{"role": "user", "content": q}], temperature=0.7, max_tokens=200
            )
            print(f"✅ 回答: {response[:300]}...")
        except Exception as e:
            print(f"❌ 错误: {e}")


async def test_context_compression(llm_client):
    """测试 2: 上下文压缩"""
    print("\n" + "=" * 60)
    print("🧪 测试 2: 上下文压缩")
    print("=" * 60)

    # 初始化短期记忆
    stm = ShortTermMemory(max_context_chars=5000)

    # 模拟执行历史（包含大量数据）
    step_history = []

    # 搜索工具返回大量文档
    search_tool = SearchTool()
    search_result = await search_tool.execute(query="人工智能", size=20)

    step_history.append(
        {
            "step": 1,
            "name": "search_documents",
            "description": "搜索相关文档",
            "result": search_result,
        }
    )

    # 模拟分析结果
    step_history.append(
        {
            "step": 2,
            "name": "analyze_input",
            "description": "分析用户输入",
            "result": {
                "success": True,
                "intent": "写作",
                "topic": "人工智能在医疗领域的应用",
                "keywords": ["AI", "医疗", "诊断", "治疗"],
            },
        }
    )

    # 原始数据大小
    import json

    original_size = len(json.dumps(step_history, ensure_ascii=False))
    print(f"\n📊 原始数据大小: {original_size} 字符")

    # 压缩状态
    state = {
        "inputs": {"query": "写一篇AI医疗报告"},
        "documents": search_result["documents"],
        "document_ids": search_result["document_ids"],
    }

    compressed = stm.summarize_state(
        state=state,
        step_history=step_history,
        target_tool_name="compose_document",
        max_steps=5,
    )

    compressed_size = len(compressed)
    compression_ratio = (1 - compressed_size / original_size) * 100

    print(f"📊 压缩后大小: {compressed_size} 字符")
    print(f"📊 压缩率: {compression_ratio:.1f}%")
    print("\n📄 压缩后内容预览:")
    print("-" * 40)
    print(compressed[:1000])

    # 验证压缩后仍可用于 LLM
    if llm_client:
        print("\n🔄 使用压缩上下文调用 LLM...")
        prompt = f"""基于以下执行上下文，总结已完成的工作：

{compressed[:2000]}

请简要总结。"""

        try:
            response = await llm_client.chat(
                [{"role": "user", "content": prompt}], max_tokens=300
            )
            print(f"✅ LLM 响应: {response[:500]}")
        except Exception as e:
            print(f"❌ 错误: {e}")


async def test_tool_chain_with_llm(llm_client):
    """测试 3: 工具链执行（真实 LLM 调用）"""
    print("\n" + "=" * 60)
    print("🧪 测试 3: 工具链执行（真实 LLM 调用）")
    print("=" * 60)

    # 初始化工具
    analyze_tool = AnalyzeInputTool(llm_client)
    search_tool = SearchTool()
    outline_tool = GenerateOutlineTool(llm_client)
    compose_tool = ComposeDocumentTool(llm_client)

    query = "帮我写一篇关于大语言模型在代码生成领域应用的调研报告"
    print(f"\n📋 用户查询: {query}")

    results = []
    state = {}

    # Step 1: 分析输入
    print("\n🔧 Step 1: 分析用户输入...")
    result1 = await analyze_tool.execute(query=query)
    results.append(
        SubTaskResult(
            step_id="1", success=result1.get("success", False), output=result1
        )
    )
    if result1.get("success"):
        state["topic"] = result1.get("topic", query)
        state["intent"] = result1.get("intent", "写作")
        state["doc_type"] = result1.get("document_type", "报告")
        print(f"   ✅ 意图: {state['intent']}, 主题: {state['topic']}")
    else:
        print(f"   ❌ 失败: {result1.get('error')}")

    # Step 2: 搜索文档
    print("\n🔧 Step 2: 搜索相关文档...")
    result2 = await search_tool.execute(query=state.get("topic", query), size=5)
    results.append(
        SubTaskResult(
            step_id="2", success=result2.get("success", False), output=result2
        )
    )
    if result2.get("success"):
        state["documents"] = result2.get("documents", [])
        state["document_ids"] = result2.get("document_ids", [])
        print(f"   ✅ 找到 {result2.get('total_count', 0)} 篇文档")

    # Step 3: 生成大纲
    print("\n🔧 Step 3: 生成文档大纲...")
    result3 = await outline_tool.execute(
        topic=state.get("topic", query),
        doc_type=state.get("doc_type", "报告"),
    )
    results.append(
        SubTaskResult(
            step_id="3", success=result3.get("success", False), output=result3
        )
    )
    if result3.get("success"):
        state["outline"] = result3.get("outline", {})
        outline = state["outline"]
        print(f"   ✅ 大纲标题: {outline.get('title', 'N/A')}")
        sections = outline.get("sections", [])
        for s in sections[:3]:
            print(f"      - {s.get('title', 'N/A')}")
        if len(sections) > 3:
            print(f"      ... 共 {len(sections)} 个章节")
    else:
        print(f"   ❌ 失败: {result3.get('error')}")

    # Step 4: 撰写文档
    print("\n🔧 Step 4: 撰写文档...")
    if state.get("outline"):
        # 准备上下文（使用压缩）
        stm = ShortTermMemory()
        context = stm.summarize_state(
            state=state,
            step_history=[],
            max_steps=3,
        )

        result4 = await compose_tool.execute(
            outline=state["outline"],
            context=context,
        )
        results.append(
            SubTaskResult(
                step_id="4", success=result4.get("success", False), output=result4
            )
        )
        if result4.get("success"):
            doc = result4.get("document", {})
            state["document"] = doc
            print(f"   ✅ 文档生成完成，字数: {doc.get('word_count', 0)}")
            print("\n📄 文档预览:")
            print("-" * 40)
            content = doc.get("content", "")
            print(content[:1500] if content else "无内容")
            if len(content) > 1500:
                print(f"\n... (共 {len(content)} 字符)")
        else:
            print(f"   ❌ 失败: {result4.get('error')}")

    # 生成执行报告
    print("\n" + "=" * 60)
    print("📊 执行报告")
    print("=" * 60)

    plan = ExecutionPlan(
        intent=state.get("intent", "写作"),
        subtasks=[
            PlanStep(id="1", tool="analyze_input", description="分析用户输入"),
            PlanStep(id="2", tool="search_documents", description="搜索相关文档"),
            PlanStep(id="3", tool="generate_outline", description="生成文档大纲"),
            PlanStep(id="4", tool="compose_document", description="撰写文档"),
        ],
    )

    report_data = ExecutionReportGenerator.generate_report_data(
        agent_name="文档写作智能体",
        query=query,
        plan=plan,
        results=results,
        state=state,
    )

    stats = report_data["statistics"]
    print("\n📈 统计:")
    print(f"   总步骤: {stats['total_steps']}")
    print(f"   成功: {stats['successful_steps']}")
    print(f"   失败: {stats['failed_steps']}")
    print(f"   成功率: {stats['success_rate']}%")

    print("\n📊 Mermaid 流程图:")
    print(report_data["mermaid_diagram"])

    return results, state


async def test_session_and_memory(llm_client):
    """测试 4: 会话管理和记忆系统"""
    print("\n" + "=" * 60)
    print("🧪 测试 4: 会话管理和记忆系统")
    print("=" * 60)

    # 初始化
    session_manager = SessionManager(default_ttl=300)
    memory = CategorizedMemory(storage_path=None)

    user_id = "test_user_001"

    # 创建会话
    print("\n📝 创建会话...")
    session = session_manager.create_session(
        user_id=user_id,
        initial_query="帮我写一篇技术文档",
    )
    print(f"   会话ID: {session.session_id}")
    print(f"   状态: {session.status.value}")

    # 记录用户偏好
    print("\n💾 记录用户偏好...")
    memory.set_preference(user_id, "language", "中文")
    memory.set_preference(user_id, "style", "专业")
    memory.set_preference(user_id, "doc_format", "markdown")

    # 记录用户行为
    memory.add_behavior(user_id, "start_task", {"query": "写技术文档"})

    # 模拟多轮对话
    print("\n💬 模拟多轮对话...")

    # 第一轮
    session_manager.add_message(
        session.session_id, "assistant", "好的，请问您想写什么主题的技术文档？"
    )

    # 等待用户输入
    session_manager.wait_for_input(session.session_id, "请提供文档主题")
    print(f"   状态: {session_manager.get_session(session.session_id).status.value}")

    # 用户回复
    session_manager.resume_session(session.session_id, "关于 Python 异步编程的教程")
    print(f"   状态: {session_manager.get_session(session.session_id).status.value}")

    # 继续对话
    session_manager.add_message(
        session.session_id, "assistant", "好的，我来为您生成 Python 异步编程教程..."
    )

    # 记录反馈
    memory.add_feedback(user_id, "响应速度很快", rating=5)

    # 添加知识
    memory.add_knowledge(user_id, "用户熟悉 Python 编程", tags=["技能", "Python"])

    # 获取对话历史
    print("\n📜 对话历史:")
    history = session_manager.get_conversation_history(session.session_id)
    for msg in history:
        print(f"   [{msg['role']}]: {msg['content'][:50]}...")

    # 获取用户上下文
    print("\n🧠 用户上下文摘要:")
    context = memory.get_context_summary(user_id)
    print(context)

    # 搜索记忆
    print("\n🔍 搜索记忆 'Python':")
    results = memory.search(user_id, "Python")
    for item in results:
        print(f"   - [{item.category.value}] {item.key}: {item.value}")

    # 完成会话
    session_manager.complete_session(session.session_id, "文档生成完成！")
    final_session = session_manager.get_session(session.session_id)
    print(f"\n✅ 会话完成，状态: {final_session.status.value}")
    print(f"   消息数: {len(final_session.messages)}")


async def test_intent_routing(llm_client):
    """测试 5: 意图路由"""
    print("\n" + "=" * 60)
    print("🧪 测试 5: 意图路由")
    print("=" * 60)

    # 初始化路由器
    router = IntentRouter(llm_client=llm_client, default_handler="chat")

    # 注册处理器
    router.register(
        name="writer",
        description="文档写作，包括报告、文章、笔记等",
        keywords=["写", "撰写", "文档", "报告", "文章", "笔记", "总结"],
    )
    router.register(
        name="search",
        description="信息检索和搜索",
        keywords=["搜索", "查找", "检索", "查询", "找"],
    )
    router.register(
        name="analysis",
        description="数据分析和统计",
        keywords=["分析", "统计", "数据", "趋势", "对比"],
    )
    router.register(
        name="qa",
        description="问答和知识查询",
        keywords=["什么是", "如何", "为什么", "怎么", "解释"],
    )
    router.register(
        name="chat",
        description="日常对话和闲聊",
        keywords=[],
    )

    # 测试用例
    test_queries = [
        "帮我写一篇关于AI的调研报告",
        "搜索最新的机器学习论文",
        "分析这些销售数据的趋势",
        "什么是深度学习？",
        "今天天气怎么样？",
        "帮我总结一下这篇文章的要点",
    ]

    print("\n🔀 路由测试:")
    for query in test_queries:
        result = await router.route(query)
        print(f"\n   📋 查询: {query}")
        print(f"   🎯 路由: {result.handler_name} (置信度: {result.confidence:.2f})")
        print(f"   💡 意图: {result.intent}")
        if result.reasoning:
            print(f"   📝 理由: {result.reasoning}")


async def main():
    """主函数"""
    print("=" * 60)
    print("🚀 Auto-Agent 完整功能演示")
    print("=" * 60)

    # 获取 LLM 客户端
    llm_client = get_llm_client()
    has_llm = llm_client is not None

    if has_llm:
        print("\n✅ LLM 客户端初始化成功")
    else:
        print("\n⚠️  无法获取 LLM 客户端，将运行不需要 LLM 的测试")

    try:
        if has_llm:
            # 测试 1: LLM 基础问答
            await test_llm_basic(llm_client)

        # 测试 2: 上下文压缩（不需要 LLM 也可以测试压缩逻辑）
        await test_context_compression(llm_client)

        if has_llm:
            # 测试 3: 工具链执行
            await test_tool_chain_with_llm(llm_client)

        # 测试 4: 会话管理和记忆（不需要 LLM）
        await test_session_and_memory(llm_client)

        # 测试 5: 意图路由（关键词匹配不需要 LLM）
        await test_intent_routing(llm_client)

        print("\n" + "=" * 60)
        if has_llm:
            print("✅ 所有测试完成!")
        else:
            print("✅ 非 LLM 测试完成! 设置 API Key 后可运行完整测试")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()

    finally:
        if has_llm:
            await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
