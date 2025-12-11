"""
基础使用示例
"""

import asyncio

from auto_agent import AutoAgent, LLMClient, ToolRegistry
from auto_agent.memory import LongTermMemory, ShortTermMemory
from auto_agent.tools.builtin.calculator import CalculatorTool
from auto_agent.tools.builtin.web_search import WebSearchTool


async def main():
    """基础使用示例"""

    # 1. 初始化 LLM 客户端（需要自己实现）
    # llm = OpenAIClient(api_key="sk-xxx")
    llm = None  # 占位

    # 2. 初始化工具注册表
    tool_registry = ToolRegistry()
    tool_registry.register(CalculatorTool())
    tool_registry.register(WebSearchTool())

    # 3. 初始化记忆系统
    ltm = LongTermMemory(storage_path="./data/memories")
    stm = ShortTermMemory(backend="memory")

    # 4. 创建 Agent
    agent = AutoAgent(
        llm_client=llm,
        tool_registry=tool_registry,
        long_term_memory=ltm,
        short_term_memory=stm,
    )

    # 5. 执行任务
    # response = await agent.run(
    #     query="帮我计算 123 * 456",
    #     user_id="user_001"
    # )
    #
    # print(response.content)


if __name__ == "__main__":
    asyncio.run(main())
