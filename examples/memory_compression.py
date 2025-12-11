"""
短期记忆压缩示例

展示：
1. 智能过滤历史步骤（基于工具依赖关系）
2. 工具级结果压缩
3. 状态摘要生成
"""

import json

from auto_agent.memory import ShortTermMemory


def demo_memory_compression():
    """演示短期记忆的智能压缩功能"""

    # 创建短期记忆实例
    stm = ShortTermMemory(
        max_history_messages=20,
        max_context_chars=51200,
    )

    # 模拟状态字典
    state = {
        "inputs": {
            "query": "帮我写一份关于AI的调研报告",
            "template_id": 1,
        },
        "control": {
            "iterations": 5,
            "max_iterations": 20,
            "failed_steps": [],
        },
        # 中间数据
        "outline": {
            "title": "AI调研报告",
            "sections": [
                {"title": "引言", "subsections": []},
                {"title": "AI发展历史", "subsections": []},
                {"title": "当前应用", "subsections": []},
                {"title": "未来展望", "subsections": []},
            ],
        },
        "document_ids": [f"doc_{i}" for i in range(50)],
        "documents": [
            {"id": f"doc_{i}", "title": f"文档{i}", "content": "x" * 1000}
            for i in range(50)
        ],
        "extracted_content": {
            "chapter_1": "第一章内容...",
            "chapter_2": "第二章内容...",
            "chapter_3": "第三章内容...",
        },
        "composed_document": {
            "title": "AI调研报告",
            "content": "x" * 5000,
            "word_count": 5000,
        },
    }

    # 模拟执行历史
    step_history = [
        {
            "step": 1,
            "name": "analyze_input",
            "description": "分析用户输入",
            "result": {"success": True, "case_type": ["调研报告"]},
        },
        {
            "step": 2,
            "name": "generate_outline",
            "description": "生成大纲",
            "result": {"success": True, "outline": state["outline"]},
        },
        {
            "step": 3,
            "name": "multi_query_search",
            "description": "多路检索",
            "result": {
                "success": True,
                "document_ids": state["document_ids"],
                "documents": state["documents"],
            },
        },
        {
            "step": 4,
            "name": "document_extraction",
            "description": "提取文档内容",
            "result": {"success": True, "extracted_content": state["extracted_content"]},
        },
        {
            "step": 5,
            "name": "document_compose",
            "description": "撰写文档",
            "result": {"success": True, "document": state["composed_document"]},
        },
    ]

    print("=" * 60)
    print("原始状态大小")
    print("=" * 60)
    print(f"state 字典大小: {len(json.dumps(state, ensure_ascii=False))} 字符")
    print(f"step_history 大小: {len(json.dumps(step_history, ensure_ascii=False))} 字符")

    print("\n" + "=" * 60)
    print("压缩后状态摘要（无目标工具过滤）")
    print("=" * 60)
    summary = stm.summarize_state(
        state=state,
        step_history=step_history,
        target_tool_name=None,
        max_steps=10,
    )
    print(f"压缩后大小: {len(summary)} 字符")
    print("\n摘要内容:")
    print(summary)

    print("\n" + "=" * 60)
    print("压缩后状态摘要（目标工具: document_compose）")
    print("=" * 60)
    summary_targeted = stm.summarize_state(
        state=state,
        step_history=step_history,
        target_tool_name="document_compose",
        max_steps=3,
    )
    print(f"压缩后大小: {len(summary_targeted)} 字符")
    print("\n摘要内容:")
    print(summary_targeted)

    print("\n" + "=" * 60)
    print("工具依赖关系（决定保留哪些历史步骤）")
    print("=" * 60)
    print("""
document_compose 依赖于:
- document_extraction
- generate_outline

所以压缩时会优先保留这两个步骤的历史记录，
而 analyze_input、multi_query_search 可能被过滤掉
    """)


if __name__ == "__main__":
    demo_memory_compression()
