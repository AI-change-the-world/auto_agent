"""
ParameterBuilder 单元测试

聚焦：BindingFallbackPolicy.USE_DEFAULT 在低置信度/解析失败时应直接使用 default_value。
"""

import pytest

from auto_agent.core.executor.param_builder import ParameterBuilder
from auto_agent.models import (
    BindingFallbackPolicy,
    BindingPlan,
    BindingSourceType,
    ParameterBinding,
    StepBindings,
)


@pytest.mark.asyncio
async def test_resolve_bindings_use_default_on_low_confidence():
    builder = ParameterBuilder(
        llm_client=None,
        binding_plan=BindingPlan(steps=[], confidence_threshold=0.7),
    )

    step_bindings = StepBindings(
        step_id="1",
        tool="mock_tool",
        bindings={
            "limit": ParameterBinding(
                source="",
                source_type=BindingSourceType.GENERATED,
                confidence=0.1,  # 低置信度
                fallback=BindingFallbackPolicy.USE_DEFAULT,
                default_value=10,
                reasoning="使用工具默认值",
            )
        },
    )

    resolved, fallback_params, _details = await builder.resolve_bindings_with_trace(
        step_bindings=step_bindings,
        state={"inputs": {"query": "x"}},
        existing_args={},
    )

    assert resolved["limit"] == 10
    assert fallback_params == []
