"""
OpenAI 提供商（占位实现）
"""

from typing import Dict, List, Optional

from auto_agent.llm.client import LLMClient


class OpenAIClient(LLMClient):
    """OpenAI 客户端（占位）"""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """聊天补全（占位）"""
        # TODO: 实现 OpenAI API 调用
        return "OpenAI 响应（占位）"

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        """流式聊天（占位）"""
        # TODO: 实现流式响应
        yield "OpenAI 流式响应（占位）"
