"""
工具基类

支持：
- 自定义验证函数 (validate_function)
- 自定义压缩函数 (compress_function)
- ValidationMode 枚举
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

from auto_agent.models import ToolDefinition, ValidationMode


class BaseTool(ABC):
    """
    工具基类

    子类需要实现：
    - definition 属性：返回 ToolDefinition
    - execute 方法：执行工具逻辑
    """

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回工具定义"""
        raise NotImplementedError

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        raise NotImplementedError

    async def validate_input(self, **kwargs) -> bool:
        """验证输入参数（可覆盖）"""
        return True

    def get_schema(self) -> Dict[str, Any]:
        """返回 JSON Schema"""
        return self.definition.to_dict()

    def get_openai_schema(self) -> Dict[str, Any]:
        """返回 OpenAI function calling 格式"""
        return self.definition.to_openai_schema()

    # ==================== 验证和压缩 ====================

    async def validate(
        self,
        result: Dict[str, Any],
        expectations: str,
        state: Any,
        mode: ValidationMode,
        llm_client: Any = None,
        db: Any = None,
    ) -> tuple:
        """
        验证执行结果是否满足期望

        Args:
            result: 工具执行结果
            expectations: 自然语言期望描述
            state: 当前执行状态
            mode: 验证模式 (NONE/LOOSE/STRICT)
            llm_client: LLM 客户端（可选）
            db: 数据库会话（可选）

        Returns:
            (passed: bool, reason: str)
        """
        validate_fn = self.definition.validate_function
        if validate_fn is None:
            # 没有定义验证函数，直接检查 success
            success = result.get("success", False)
            if success:
                return True, "无需验证，执行成功即通过"
            else:
                return False, f"执行失败: {result.get('error', '未知错误')}"

        # 调用自定义验证函数
        import asyncio

        if asyncio.iscoroutinefunction(validate_fn):
            return await validate_fn(result, expectations, state, mode, llm_client, db)
        else:
            return validate_fn(result, expectations, state, mode, llm_client, db)

    def compress_result(self, result: Dict[str, Any], state: Any) -> Optional[Dict[str, Any]]:
        """
        压缩执行结果（用于短期记忆）

        Args:
            result: 工具执行结果
            state: 当前执行状态

        Returns:
            压缩后的结果，返回 None 表示不压缩（保留完整结果）
        """
        compress_fn = self.definition.compress_function
        if compress_fn is None:
            return None  # 使用默认压缩策略
        return compress_fn(result, state)
