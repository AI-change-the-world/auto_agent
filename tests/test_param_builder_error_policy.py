"""
BindingFallbackPolicy.ERROR 行为测试

ERROR 的语义：当参数无法解析时直接报错（不允许走 LLM fallback），但“能解析出来”时应正常通过。
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
async def test_error_policy_does_not_raise_when_resolved():
    builder = ParameterBuilder(
        llm_client=None,
        binding_plan=BindingPlan(steps=[], confidence_threshold=0.7),
    )

    step_bindings = StepBindings(
        step_id="1",
        tool="mock_tool",
        bindings={
            "focus": ParameterBinding(
                source="inputs.query",
                source_type=BindingSourceType.STATE,
                confidence=1.0,
                fallback=BindingFallbackPolicy.ERROR,
            )
        },
    )

    resolved, fallback_params, _details = await builder.resolve_bindings_with_trace(
        step_bindings=step_bindings,
        state={"inputs": {"query": "hello"}},
        existing_args={},
    )

    assert resolved["focus"] == "hello"
    assert fallback_params == []


@pytest.mark.asyncio
async def test_error_policy_raises_when_unresolvable():
    builder = ParameterBuilder(
        llm_client=None,
        binding_plan=BindingPlan(steps=[], confidence_threshold=0.7),
    )

    step_bindings = StepBindings(
        step_id="1",
        tool="mock_tool",
        bindings={
            "focus": ParameterBinding(
                source="inputs.missing",
                source_type=BindingSourceType.STATE,
                confidence=1.0,
                fallback=BindingFallbackPolicy.ERROR,
            )
        },
    )

    with pytest.raises(ValueError):
        await builder.resolve_bindings_with_trace(
            step_bindings=step_bindings,
            state={"inputs": {"query": "hello"}},
            existing_args={},
        )

