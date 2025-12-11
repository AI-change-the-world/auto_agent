"""
Anthropic 提供商（占位实现）
"""

from typing import Dict, List, Optional

from auto_agent.llm.client import LLMClient


class AnthropicClient(LLMClient):
    """Anthropic 客户端（占位）"""

    def __init__(self, api_key: str, model: str = "claude-3-opus"):
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
        # TODO: 实现 Anthropic API 调用
        return "Anthropic 响应（占位）"

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        """流式聊天（占位）"""
        # TODO: 实现流式响应
        yield "Anthropic 流式响应（占位）"
