"""
OpenAI LLM 客户端实现

支持:
- 同步/流式聊天补全
- Function Calling
- 兼容 OpenAI API 的其他提供商 (DeepSeek, Azure 等)
"""

import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from auto_agent.llm.client import LLMClient


class OpenAIClient(LLMClient):
    """
    OpenAI API 客户端

    使用官方 openai 库，也可用于兼容 OpenAI API 的其他提供商
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
        default_temperature: float = 0.7,
    ):
        """
        初始化 OpenAI 客户端

        Args:
            api_key: API 密钥
            model: 模型名称
            base_url: API 基础 URL (可用于其他兼容提供商)
            timeout: 请求超时时间
            default_temperature: 默认温度参数
        """
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_temperature = default_temperature
        
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        trace_purpose: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        聊天补全（内部使用 stream 避免超时）

        Args:
            messages: 消息列表
            temperature: 温度参数
            trace_purpose: 追踪目的（用于 tracing 系统）
            **kwargs: 其他参数 (如 top_p, presence_penalty 等)

        Returns:
            LLM 响应内容
        """
        start_time = time.time()
        
        # 构建参数
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "stream": True,
            "stream_options": {"include_usage": True},  # 获取 token 统计
        }
        
        # 合并额外参数
        for key in ["top_p", "presence_penalty", "frequency_penalty", "stop"]:
            if key in kwargs:
                params[key] = kwargs[key]

        # 使用 stream 模式，收集完整响应
        chunks = []
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        
        stream = await self._client.chat.completions.create(**params)
        async for chunk in stream:
            # 收集内容
            if chunk.choices and chunk.choices[0].delta.content:
                chunks.append(chunk.choices[0].delta.content)
            
            # 最后一个 chunk 包含 usage 信息
            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens
                total_tokens = chunk.usage.total_tokens
        
        content = "".join(chunks)
        
        # 记录追踪事件
        duration_ms = (time.time() - start_time) * 1000
        self._trace_llm_call(
            purpose=trace_purpose or "other",
            prompt=self._format_messages_for_trace(messages),
            response=content,
            prompt_tokens=prompt_tokens,
            response_tokens=completion_tokens,
            total_tokens=total_tokens,
            temperature=temperature or self.default_temperature,
            duration_ms=duration_ms,
        )
        
        return content

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天补全

        Args:
            messages: 消息列表
            temperature: 温度参数

        Yields:
            流式响应片段
        """
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "stream": True,
        }

        stream = await self._client.chat.completions.create(**params)
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def function_call(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Function Calling 支持

        Args:
            messages: 消息列表
            tools: 工具定义列表 (OpenAI function calling 格式)
            tool_choice: 工具选择策略 ("auto", "none", 或指定工具)
            temperature: 温度参数

        Returns:
            包含 tool_calls 或 message 的响应
        """
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature or self.default_temperature,
        )

        message = response.choices[0].message
        
        if message.tool_calls:
            return {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in message.tool_calls
                ],
            }
        
        return {
            "type": "message",
            "content": message.content or "",
        }

    def _format_messages_for_trace(self, messages: List[Dict[str, str]]) -> str:
        """格式化消息用于追踪"""
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"[{role}]: {content}")
        return "\n".join(parts)

    def _trace_llm_call(
        self,
        purpose: str,
        prompt: str,
        response: str,
        prompt_tokens: int,
        response_tokens: int,
        total_tokens: int,
        temperature: float,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
    ):
        """记录 LLM 调用到追踪系统"""
        try:
            from auto_agent.tracing import trace_llm_call
            trace_llm_call(
                purpose=purpose,
                model=self.model,
                provider=self._get_provider_name(),
                prompt=prompt,
                response=response,
                prompt_tokens=prompt_tokens,
                response_tokens=response_tokens,
                total_tokens=total_tokens,
                temperature=temperature,
                duration_ms=duration_ms,
                success=success,
                error=error,
            )
        except Exception:
            # 追踪失败不影响主流程
            pass

    def _get_provider_name(self) -> str:
        """根据 base_url 推断提供商名称"""
        if "openai.com" in self.base_url:
            return "openai"
        if "deepseek" in self.base_url:
            return "deepseek"
        if "azure" in self.base_url:
            return "azure"
        return "openai_compatible"

    async def close(self):
        """关闭客户端连接"""
        if self._client:
            await self._client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
