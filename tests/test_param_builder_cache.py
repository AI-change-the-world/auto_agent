"""
ParameterBuilder 缓存行为测试

目标：同一步骤+同缺失参数+同状态摘要时，build_arguments_with_llm 应复用缓存，避免重复 LLM 调用。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from auto_agent.core.executor.param_builder import ParameterBuilder
from auto_agent.models import PlanStep, ToolDefinition, ToolParameter
from auto_agent.tools.base import BaseTool


class MockTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mock_tool",
            description="mock",
            parameters=[
                ToolParameter(
                    name="requirements",
                    type="string",
                    description="需求",
                    required=True,
                )
            ],
            output_schema={},
        )

    async def execute(self, **kwargs):
        return {"success": True}


@pytest.mark.asyncio
async def test_build_arguments_with_llm_cache_hit():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value='```json\n{"requirements": "X"}\n```')

    builder = ParameterBuilder(llm_client=llm, binding_plan=None)
    tool = MockTool()

    step = PlanStep(id="1", tool="mock_tool", description="d")
    state = {"inputs": {"query": "hello"}}

    r1 = await builder.build_arguments_with_llm(step, state, tool, existing_args={})
    r2 = await builder.build_arguments_with_llm(step, state, tool, existing_args={})

    assert r1["requirements"] == "X"
    assert r2["requirements"] == "X"
    assert llm.chat.call_count == 1
