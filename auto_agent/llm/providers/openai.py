"""
OpenAI LLM 客户端实现

支持:
- 同步/流式聊天补全
- Function Calling
- 兼容 OpenAI API 的其他提供商 (DeepSeek, Azure 等)
"""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from auto_agent.llm.client import LLMClient


class OpenAIClient(LLMClient):
    """
    OpenAI API 客户端

    也可用于兼容 OpenAI API 的其他提供商，如 DeepSeek、Azure OpenAI 等
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
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """懒加载 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        trace_purpose: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        同步聊天补全

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            trace_purpose: 追踪目的（用于 tracing 系统）
            **kwargs: 其他参数 (如 top_p, presence_penalty 等)

        Returns:
            LLM 响应内容
        """
        import time
        start_time = time.time()
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        # 合并额外参数
        for key in ["top_p", "presence_penalty", "frequency_penalty", "stop"]:
            if key in kwargs:
                payload[key] = kwargs[key]

        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        
        # 提取 token 使用信息
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        
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

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天补全

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大 token 数

        Yields:
            流式响应片段
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with self.client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

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
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature or self.default_temperature,
        }

        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        message = data["choices"][0]["message"]
        if message.get("tool_calls"):
            return {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"]),
                    }
                    for tc in message["tool_calls"]
                ],
            }
        return {
            "type": "message",
            "content": message.get("content", ""),
        }

    async def close(self):
        """关闭客户端连接"""
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
