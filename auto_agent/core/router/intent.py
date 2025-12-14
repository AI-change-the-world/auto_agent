"""
意图路由器

功能:
1. 识别用户意图
2. 选择合适的 Agent 或工具
3. 支持 Function Calling 模式
4. 支持规则匹配降级
"""

import json
import re
from typing import Any, Callable, Dict, List, Optional

from auto_agent.llm.client import LLMClient


class IntentHandler:
    """意图处理器"""

    def __init__(
        self,
        name: str,
        description: str,
        keywords: Optional[List[str]] = None,
        handler: Optional[Callable] = None,
        agent_config: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.description = description
        self.keywords = keywords or []
        self.handler = handler
        self.agent_config = agent_config or {}


class IntentResult:
    """意图识别结果"""

    def __init__(
        self,
        intent: str,
        handler_name: str,
        confidence: float,
        parameters: Optional[Dict[str, Any]] = None,
        reasoning: Optional[str] = None,
    ):
        self.intent = intent
        self.handler_name = handler_name
        self.confidence = confidence
        self.parameters = parameters or {}
        self.reasoning = reasoning

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "handler": self.handler_name,
            "confidence": self.confidence,
            "parameters": self.parameters,
            "reasoning": self.reasoning,
        }


class IntentRouter:
    """
    意图路由器

    支持两种模式:
    1. LLM 模式: 使用大模型理解意图
    2. 规则模式: 基于关键词匹配
    """

    INTENT_PROMPT = """分析用户输入，识别意图并选择合适的处理方式。

用户输入: {query}

可用的处理方式:
{handlers}

请分析用户意图，返回 JSON:
{{
    "intent": "意图描述",
    "handler": "处理方式名称",
    "confidence": 0.95,
    "parameters": {{}},
    "reasoning": "选择理由"
}}

注意:
1. handler 必须是上面列出的处理方式名称之一
2. confidence 是 0-1 之间的置信度
3. parameters 是从用户输入中提取的参数
"""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        default_handler: str = "default",
    ):
        self.llm_client = llm_client
        self.default_handler = default_handler
        self._handlers: Dict[str, IntentHandler] = {}

    def register_handler(self, handler: IntentHandler):
        """注册意图处理器"""
        self._handlers[handler.name] = handler

    def register(
        self,
        name: str,
        description: str,
        keywords: Optional[List[str]] = None,
        handler: Optional[Callable] = None,
        agent_config: Optional[Dict[str, Any]] = None,
    ):
        """便捷注册方法"""
        self._handlers[name] = IntentHandler(
            name=name,
            description=description,
            keywords=keywords,
            handler=handler,
            agent_config=agent_config,
        )

    def get_handler(self, name: str) -> Optional[IntentHandler]:
        """获取处理器"""
        return self._handlers.get(name)

    async def route(self, query: str) -> IntentResult:
        """路由用户请求"""
        if self.llm_client:
            return await self._route_with_llm(query)
        else:
            return self._route_with_rules(query)

    async def _route_with_llm(self, query: str) -> IntentResult:
        """使用 LLM 路由"""
        handlers_desc = "\n".join([
            f"- {name}: {h.description}"
            for name, h in self._handlers.items()
        ])

        prompt = self.INTENT_PROMPT.format(
            query=query,
            handlers=handlers_desc,
        )

        try:
            response = await self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )

            # 提取 JSON
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                handler_name = result.get("handler", self.default_handler)

                # 验证 handler 存在
                if handler_name not in self._handlers:
                    handler_name = self.default_handler

                return IntentResult(
                    intent=result.get("intent", "unknown"),
                    handler_name=handler_name,
                    confidence=result.get("confidence", 0.8),
                    parameters=result.get("parameters", {}),
                    reasoning=result.get("reasoning"),
                )
        except Exception:
            pass

        # 降级到规则匹配
        return self._route_with_rules(query)

    def _route_with_rules(self, query: str) -> IntentResult:
        """使用规则路由"""
        query_lower = query.lower()
        best_match = None
        best_score = 0

        for name, handler in self._handlers.items():
            score = 0
            matched_keywords = []

            for keyword in handler.keywords:
                if keyword.lower() in query_lower:
                    score += 1
                    matched_keywords.append(keyword)

            if score > best_score:
                best_score = score
                best_match = (name, handler, matched_keywords)

        if best_match and best_score > 0:
            name, handler, keywords = best_match
            confidence = min(0.9, 0.5 + best_score * 0.1)
            return IntentResult(
                intent=handler.description,
                handler_name=name,
                confidence=confidence,
                parameters={"matched_keywords": keywords},
                reasoning=f"关键词匹配: {keywords}",
            )

        return IntentResult(
            intent="unknown",
            handler_name=self.default_handler,
            confidence=0.3,
            reasoning="无匹配，使用默认处理器",
        )

    async def route_and_execute(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """路由并执行"""
        result = await self.route(query)
        handler = self._handlers.get(result.handler_name)

        if handler and handler.handler:
            try:
                output = await handler.handler(
                    query=query,
                    parameters=result.parameters,
                    context=context or {},
                )
                return {
                    "success": True,
                    "intent": result.to_dict(),
                    "output": output,
                }
            except Exception as e:
                return {
                    "success": False,
                    "intent": result.to_dict(),
                    "error": str(e),
                }

        return {
            "success": False,
            "intent": result.to_dict(),
            "error": f"Handler '{result.handler_name}' not found or has no executor",
        }
