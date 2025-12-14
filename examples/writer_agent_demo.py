"""
文档写作智能体示例

演示如何:
1. 使用 Markdown 定义智能体
2. 自定义工具
3. 自动编排执行流程
4. 生成执行报告
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from auto_agent import (
    AgentDefinition,
    AgentMarkdownParser,
    AutoAgent,
    BaseTool,
    ExecutionReportGenerator,
    LongTermMemory,
    OpenAIClient,
    ShortTermMemory,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    tool,
)


# ==================== 自定义工具 ====================


@tool(
    name="analyze_input",
    description="分析用户输入，识别意图和关键信息",
    category="analysis",
    parameters=[
        {"name": "query", "type": "string", "description": "用户输入", "required": True},
    ],
    output_schema={
        "intent": {"type": "string", "description": "用户意图"},
        "topic": {"type": "string", "description": "主题"},
        "keywords": {"type": "array", "description": "关键词列表"},
    },
)
class AnalyzeInputTool(BaseTool):
    """分析用户输入工具"""

    async def execute(self, query: str, **kwargs) -> Dict[str, Any]:
        # 模拟分析结果
        return {
            "success": True,
            "intent": "写作",
            "topic": query[:50],
            "keywords": ["学习", "笔记", "总结"],
            "case_type": ["调研报告"],
        }


@tool(
    name="es_fulltext_search",
    description="全文检索，搜索相关文档",
    category="retrieval",
    parameters=[
        {"name": "query", "type": "string", "description": "搜索查询", "required": True},
        {"name": "size", "type": "integer", "description": "返回数量", "default": 10},
    ],
    output_schema={
        "document_ids": {"type": "array", "description": "文档ID列表"},
        "documents": {"type": "array", "description": "文档列表"},
    },
)
class ESFulltextSearchTool(BaseTool):
    """全文检索工具"""

    async def execute(
        self, query: str, size: int = 10, **kwargs
    ) -> Dict[str, Any]:
        # 模拟检索结果
        mock_docs = [
            {
                "id": f"doc_{i}",
                "title": f"相关文档 {i}: {query[:20]}",
                "content": f"这是关于 {query[:30]} 的详细内容...",
                "score": 0.9 - i * 0.1,
            }
            for i in range(min(size, 5))
        ]
        return {
            "success": True,
            "document_ids": [d["id"] for d in mock_docs],
            "documents": mock_docs,
            "count": len(mock_docs),
        }


@tool(
    name="generate_outline",
    description="根据主题和检索结果生成文档大纲",
    category="document",
    parameters=[
        {"name": "topic", "type": "string", "description": "文档主题", "required": True},
        {"name": "document_ids", "type": "array", "description": "参考文档ID列表"},
    ],
    output_schema={
        "outline": {"type": "object", "description": "大纲结构"},
    },
)
class GenerateOutlineTool(BaseTool):
    """大纲生成工具"""

    async def execute(
        self, topic: str, document_ids: List[str] = None, **kwargs
    ) -> Dict[str, Any]:
        # 模拟大纲生成
        outline = {
            "title": f"关于{topic}的研究报告",
            "sections": [
                {"title": "一、背景介绍", "subsections": ["1.1 研究背景", "1.2 研究意义"]},
                {"title": "二、现状分析", "subsections": ["2.1 国内现状", "2.2 国外现状"]},
                {"title": "三、主要内容", "subsections": ["3.1 核心概念", "3.2 关键技术"]},
                {"title": "四、总结与展望", "subsections": ["4.1 主要结论", "4.2 未来方向"]},
            ],
        }
        return {
            "success": True,
            "outline": outline,
        }


@tool(
    name="document_compose",
    description="根据大纲和参考资料撰写文档",
    category="document",
    parameters=[
        {"name": "outline", "type": "object", "description": "文档大纲", "required": True},
        {"name": "documents", "type": "array", "description": "参考文档列表"},
        {"name": "style", "type": "string", "description": "写作风格", "default": "formal"},
    ],
    output_schema={
        "document": {"type": "object", "description": "生成的文档"},
    },
)
class DocumentComposeTool(BaseTool):
    """文档撰写工具"""

    async def execute(
        self,
        outline: Dict[str, Any],
        documents: List[Dict] = None,
        style: str = "formal",
        **kwargs,
    ) -> Dict[str, Any]:
        # 模拟文档生成
        title = outline.get("title", "未命名文档")
        sections = outline.get("sections", [])
        
        content_parts = [f"# {title}\n"]
        for section in sections:
            content_parts.append(f"\n## {section['title']}\n")
            for sub in section.get("subsections", []):
                content_parts.append(f"\n### {sub}\n")
                content_parts.append("这里是详细内容...\n")
        
        content = "".join(content_parts)
        
        return {
            "success": True,
            "document": {
                "title": title,
                "content": content,
                "word_count": len(content),
                "style": style,
            },
        }


# ==================== Agent 定义 (Markdown) ====================

WRITER_AGENT_MD = """
## 你是一个文档写作智能体

你需要按以下步骤完成用户的需求：

1. 调用 [analyze_input] 工具，对用户的意图进行分析
2. 调用 [es_fulltext_search] 工具，检索相关文档
3. 调用 [generate_outline] 工具，生成文档大纲
4. 调用 [document_compose] 工具，撰写完整文档
5. 返回结果

### 目标
- 理解用户的写作需求
- 检索相关参考资料
- 生成结构清晰的文档

### 约束
- 文档长度适中，不超过5000字
- 引用的参考资料不超过10篇
"""


# ==================== 主函数 ====================


async def main():
    """运行文档写作智能体示例"""
    
    print("=" * 60)
    print("📝 文档写作智能体示例")
    print("=" * 60)
    
    # 1. 初始化 LLM 客户端
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    if not api_key:
        print("⚠️  未设置 API Key，将使用模拟模式")
        llm_client = None
    else:
        print(f"✅ 使用 LLM: {model}")
        llm_client = OpenAIClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    
    # 2. 初始化工具注册表
    tool_registry = ToolRegistry()
    tool_registry.register(AnalyzeInputTool())
    tool_registry.register(ESFulltextSearchTool())
    tool_registry.register(GenerateOutlineTool())
    tool_registry.register(DocumentComposeTool())
    
    print(f"✅ 已注册 {len(tool_registry.get_all_tools())} 个工具")
    
    # 3. 解析 Agent 定义
    parser = AgentMarkdownParser(llm_client=llm_client)
    parse_result = await parser.parse(
        content=WRITER_AGENT_MD,
        tools_catalog=tool_registry.get_tools_catalog(),
    )
    
    if not parse_result["success"]:
        print(f"❌ Agent 解析失败: {parse_result['errors']}")
        return
    
    agent_def: AgentDefinition = parse_result["agent"]
    print(f"✅ Agent 解析成功: {agent_def.name}")
    print(f"   目标: {agent_def.goals}")
    print(f"   约束: {agent_def.constraints}")
    print(f"   步骤数: {len(agent_def.initial_plan)}")
    
    # 4. 初始化记忆系统
    ltm = LongTermMemory(storage_path="./data/memories")
    stm = ShortTermMemory(backend="memory")
    
    # 5. 创建 Agent
    agent_config = parser.to_agent_config(agent_def)
    
    agent = AutoAgent(
        llm_client=llm_client,
        tool_registry=tool_registry,
        long_term_memory=ltm,
        short_term_memory=stm,
        agent_goals=agent_config.get("agent_goals"),
        agent_constraints=agent_config.get("agent_constraints"),
    )
    
    print("✅ Agent 初始化完成")
    
    # 6. 执行任务
    query = "帮我写一篇关于人工智能在医疗领域应用的调研报告"
    print(f"\n📋 用户查询: {query}")
    print("-" * 60)
    
    from datetime import datetime
    start_time = datetime.now()
    
    try:
        response = await agent.run(
            query=query,
            user_id="demo_user",
            initial_plan=agent_config.get("initial_plan"),
        )
        
        end_time = datetime.now()
        
        print(f"\n✅ 执行完成!")
        print(f"   会话ID: {response.conversation_id}")
        print(f"   耗时: {(end_time - start_time).total_seconds():.2f} 秒")
        
        # 7. 生成执行报告
        if response.plan and response.execution_results:
            report_data = ExecutionReportGenerator.generate_report_data(
                agent_name=agent_def.name,
                query=query,
                plan=response.plan,
                results=response.execution_results,
                state={},
                start_time=start_time,
                end_time=end_time,
            )
            
            # 输出 Markdown 报告
            markdown_report = ExecutionReportGenerator.generate_markdown_report(report_data)
            
            print("\n" + "=" * 60)
            print("📊 执行报告")
            print("=" * 60)
            print(markdown_report)
            
            # 保存报告
            report_path = "./data/reports/writer_agent_report.md"
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(markdown_report)
            print(f"\n📁 报告已保存到: {report_path}")
        
        # 8. 输出结果
        print("\n" + "=" * 60)
        print("📄 生成的文档")
        print("=" * 60)
        print(response.content[:1000] if response.content else "无内容")
        
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if llm_client:
            await llm_client.close()


# ==================== 简化版本 (无 LLM) ====================


async def demo_without_llm():
    """无 LLM 的简化演示"""
    
    print("=" * 60)
    print("📝 简化演示 (无 LLM)")
    print("=" * 60)
    
    # 1. 初始化工具
    tool_registry = ToolRegistry()
    tool_registry.register(AnalyzeInputTool())
    tool_registry.register(ESFulltextSearchTool())
    tool_registry.register(GenerateOutlineTool())
    tool_registry.register(DocumentComposeTool())
    
    # 2. 解析 Agent (使用规则解析)
    parser = AgentMarkdownParser(llm_client=None)
    parse_result = await parser.parse(WRITER_AGENT_MD)
    
    agent_def = parse_result["agent"]
    print(f"✅ Agent: {agent_def.name}")
    print(f"   步骤: {[s.tool for s in agent_def.initial_plan]}")
    
    # 3. 手动执行工具链
    print("\n🔧 手动执行工具链:")
    
    # Step 1: 分析输入
    analyze_tool = tool_registry.get_tool("analyze_input")
    result1 = await analyze_tool.execute(query="写一篇AI医疗报告")
    print(f"   1. analyze_input: {result1['intent']}, {result1['topic']}")
    
    # Step 2: 检索
    search_tool = tool_registry.get_tool("es_fulltext_search")
    result2 = await search_tool.execute(query=result1["topic"], size=5)
    print(f"   2. es_fulltext_search: 找到 {result2['count']} 篇文档")
    
    # Step 3: 生成大纲
    outline_tool = tool_registry.get_tool("generate_outline")
    result3 = await outline_tool.execute(
        topic=result1["topic"],
        document_ids=result2["document_ids"],
    )
    print(f"   3. generate_outline: {result3['outline']['title']}")
    
    # Step 4: 撰写文档
    compose_tool = tool_registry.get_tool("document_compose")
    result4 = await compose_tool.execute(
        outline=result3["outline"],
        documents=result2["documents"],
    )
    print(f"   4. document_compose: {result4['document']['word_count']} 字")
    
    print("\n✅ 执行完成!")
    print("\n📄 生成的文档预览:")
    print("-" * 40)
    print(result4["document"]["content"][:500])


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--simple":
        asyncio.run(demo_without_llm())
    else:
        asyncio.run(main())
