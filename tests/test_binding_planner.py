"""
Binding Planner 单元测试

测试参数绑定规划器的核心功能
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from auto_agent.core.binding_planner import BindingPlanner
from auto_agent.models import (
    BindingFallbackPolicy,
    BindingPlan,
    BindingSourceType,
    ExecutionPlan,
    ParameterBinding,
    PlanStep,
    StepBindings,
    ToolDefinition,
    ToolParameter,
)
from auto_agent.tools.base import BaseTool
from auto_agent.tools.registry import ToolRegistry

# ==================== Mock 工具 ====================


class MockAnalyzeTool(BaseTool):
    """模拟分析工具"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="analyze",
            description="分析用户需求",
            parameters=[
                ToolParameter(
                    name="requirements",
                    type="string",
                    description="需求描述",
                    required=True,
                ),
            ],
            output_schema={
                "entities": {"type": "array"},
                "relationships": {"type": "array"},
            },
        )

    async def execute(self, **kwargs):
        return {"success": True, "entities": [], "relationships": []}


class MockDesignTool(BaseTool):
    """模拟设计工具"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="design",
            description="设计 API",
            parameters=[
                ToolParameter(
                    name="entities",
                    type="array",
                    description="实体列表",
                    required=True,
                ),
                ToolParameter(
                    name="relationships",
                    type="array",
                    description="关系列表",
                    required=False,
                    default=[],
                ),
                ToolParameter(
                    name="max_results",
                    type="number",
                    description="返回结果数量上限（可选）",
                    required=False,
                    default=10,
                ),
            ],
            output_schema={
                "endpoints": {"type": "array"},
            },
        )

    async def execute(self, **kwargs):
        return {"success": True, "endpoints": []}


class MockGenerateTool(BaseTool):
    """模拟生成工具"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="generate",
            description="生成代码",
            parameters=[
                ToolParameter(
                    name="endpoints",
                    type="array",
                    description="API 端点列表",
                    required=True,
                ),
            ],
            output_schema={
                "code": {"type": "string"},
            },
        )

    async def execute(self, **kwargs):
        return {"success": True, "code": ""}


# ==================== 测试用例 ====================


class TestParameterBinding:
    """测试 ParameterBinding 数据结构"""

    def test_to_dict(self):
        """测试序列化"""
        binding = ParameterBinding(
            source="query",
            source_type=BindingSourceType.USER_INPUT,
            confidence=0.9,
            fallback=BindingFallbackPolicy.LLM_INFER,
            reasoning="来自用户输入",
        )

        data = binding.to_dict()

        assert data["source"] == "query"
        assert data["source_type"] == "user_input"
        assert data["confidence"] == 0.9
        assert data["fallback"] == "llm_infer"
        assert data["reasoning"] == "来自用户输入"

    def test_from_dict(self):
        """测试反序列化"""
        data = {
            "source": "step_1.output.entities",
            "source_type": "step_output",
            "confidence": 0.85,
            "fallback": "llm_infer",
            "reasoning": "来自步骤1的输出",
        }

        binding = ParameterBinding.from_dict(data)

        assert binding.source == "step_1.output.entities"
        assert binding.source_type == BindingSourceType.STEP_OUTPUT
        assert binding.confidence == 0.85
        assert binding.fallback == BindingFallbackPolicy.LLM_INFER


class TestStepBindings:
    """测试 StepBindings 数据结构"""

    def test_to_dict(self):
        """测试序列化"""
        step_bindings = StepBindings(
            step_id="1",
            tool="analyze",
            bindings={
                "requirements": ParameterBinding(
                    source="query",
                    source_type=BindingSourceType.USER_INPUT,
                    confidence=1.0,
                ),
            },
        )

        data = step_bindings.to_dict()

        assert data["step_id"] == "1"
        assert data["tool"] == "analyze"
        assert "requirements" in data["bindings"]
        assert data["bindings"]["requirements"]["source"] == "query"

    def test_from_dict(self):
        """测试反序列化"""
        data = {
            "step_id": "2",
            "tool": "design",
            "bindings": {
                "entities": {
                    "source": "step_1.output.entities",
                    "source_type": "step_output",
                    "confidence": 0.9,
                },
            },
        }

        step_bindings = StepBindings.from_dict(data)

        assert step_bindings.step_id == "2"
        assert step_bindings.tool == "design"
        assert "entities" in step_bindings.bindings
        assert (
            step_bindings.bindings["entities"].source_type
            == BindingSourceType.STEP_OUTPUT
        )


class TestBindingPlan:
    """测试 BindingPlan 数据结构"""

    def test_get_step_bindings(self):
        """测试获取步骤绑定"""
        plan = BindingPlan(
            steps=[
                StepBindings(step_id="1", tool="analyze", bindings={}),
                StepBindings(step_id="2", tool="design", bindings={}),
            ],
        )

        step1 = plan.get_step_bindings("1")
        step2 = plan.get_step_bindings("2")
        step3 = plan.get_step_bindings("3")

        assert step1 is not None
        assert step1.tool == "analyze"
        assert step2 is not None
        assert step2.tool == "design"
        assert step3 is None

    def test_to_dict_and_from_dict(self):
        """测试序列化和反序列化"""
        original = BindingPlan(
            steps=[
                StepBindings(
                    step_id="1",
                    tool="analyze",
                    bindings={
                        "requirements": ParameterBinding(
                            source="query",
                            source_type=BindingSourceType.USER_INPUT,
                            confidence=1.0,
                        ),
                    },
                ),
            ],
            confidence_threshold=0.8,
            reasoning="测试推理",
        )

        data = original.to_dict()
        restored = BindingPlan.from_dict(data)

        assert len(restored.steps) == 1
        assert restored.steps[0].step_id == "1"
        assert restored.confidence_threshold == 0.8
        assert restored.reasoning == "测试推理"


class TestBindingPlanner:
    """测试 BindingPlanner"""

    @pytest.fixture
    def registry(self):
        """创建工具注册表"""
        registry = ToolRegistry()
        registry.register(MockAnalyzeTool())
        registry.register(MockDesignTool())
        registry.register(MockGenerateTool())
        return registry

    @pytest.fixture
    def mock_llm_client(self):
        """创建 Mock LLM 客户端"""
        client = MagicMock()
        client.chat = AsyncMock(
            return_value="""```json
{
    "bindings": [
        {
            "step_id": "1",
            "tool": "analyze",
            "bindings": {
                "requirements": {
                    "source": "query",
                    "source_type": "user_input",
                    "confidence": 1.0,
                    "reasoning": "用户输入直接作为需求"
                }
            }
        },
        {
            "step_id": "2",
            "tool": "design",
            "bindings": {
                "entities": {
                    "source": "step_1.output.entities",
                    "source_type": "step_output",
                    "confidence": 0.95,
                    "reasoning": "来自分析步骤的实体输出"
                },
                "relationships": {
                    "source": "step_1.output.relationships",
                    "source_type": "step_output",
                    "confidence": 0.9,
                    "reasoning": "来自分析步骤的关系输出"
                },
                "max_results": {
                    "source": "",
                    "source_type": "generated",
                    "confidence": 0.2,
                    "reasoning": "用户未明确指定，使用默认值即可"
                }
            }
        },
        {
            "step_id": "3",
            "tool": "generate",
            "bindings": {
                "endpoints": {
                    "source": "step_2.output.endpoints",
                    "source_type": "step_output",
                    "confidence": 0.95,
                    "reasoning": "来自设计步骤的端点输出"
                }
            }
        }
    ],
    "reasoning": "三步流程：分析需求 -> 设计API -> 生成代码"
}
```"""
        )
        return client

    @pytest.fixture
    def execution_plan(self):
        """创建执行计划"""
        return ExecutionPlan(
            intent="生成 API 项目",
            subtasks=[
                PlanStep(id="1", tool="analyze", description="分析需求"),
                PlanStep(id="2", tool="design", description="设计 API"),
                PlanStep(id="3", tool="generate", description="生成代码"),
            ],
        )

    @pytest.mark.asyncio
    async def test_create_binding_plan(self, registry, mock_llm_client, execution_plan):
        """测试创建绑定计划"""
        planner = BindingPlanner(
            llm_client=mock_llm_client,
            tool_registry=registry,
        )

        binding_plan = await planner.create_binding_plan(
            execution_plan=execution_plan,
            user_input="创建一个用户管理 API",
        )

        # 验证绑定计划
        assert binding_plan is not None
        assert len(binding_plan.steps) == 3

        # 验证步骤1绑定
        step1 = binding_plan.get_step_bindings("1")
        assert step1 is not None
        assert "requirements" in step1.bindings
        assert (
            step1.bindings["requirements"].source_type == BindingSourceType.USER_INPUT
        )

        # 验证步骤2绑定
        step2 = binding_plan.get_step_bindings("2")
        assert step2 is not None
        assert "entities" in step2.bindings
        assert step2.bindings["entities"].source_type == BindingSourceType.STEP_OUTPUT
        assert step2.bindings["entities"].source == "step_1.output.entities"
        # 工具 schema 默认值应注入到 default_value（即便 LLM 未显式返回）
        assert step2.bindings["relationships"].default_value == []
        # GENERATED + 工具默认值 => fallback 自动切换为 USE_DEFAULT
        assert step2.bindings["max_results"].default_value == 10
        assert (
            step2.bindings["max_results"].fallback == BindingFallbackPolicy.USE_DEFAULT
        )

        # 验证步骤3绑定
        step3 = binding_plan.get_step_bindings("3")
        assert step3 is not None
        assert "endpoints" in step3.bindings
        assert step3.bindings["endpoints"].source == "step_2.output.endpoints"

    @pytest.mark.asyncio
    async def test_create_binding_plan_empty(self, registry, mock_llm_client):
        """测试空执行计划"""
        planner = BindingPlanner(
            llm_client=mock_llm_client,
            tool_registry=registry,
        )

        empty_plan = ExecutionPlan(intent="空计划", subtasks=[])

        binding_plan = await planner.create_binding_plan(
            execution_plan=empty_plan,
            user_input="测试",
        )

        assert binding_plan is not None
        assert len(binding_plan.steps) == 0

    @pytest.mark.asyncio
    async def test_create_binding_plan_llm_failure(self, registry, execution_plan):
        """测试 LLM 调用失败时的处理"""
        # 创建会抛出异常的 mock client
        failing_client = MagicMock()
        failing_client.chat = AsyncMock(side_effect=Exception("LLM 调用失败"))

        planner = BindingPlanner(
            llm_client=failing_client,
            tool_registry=registry,
        )

        binding_plan = await planner.create_binding_plan(
            execution_plan=execution_plan,
            user_input="测试",
        )

        # 应该返回空绑定计划，不抛出异常
        assert binding_plan is not None
        assert len(binding_plan.steps) == 0
        assert "失败" in binding_plan.reasoning


class TestBindingSourceTypes:
    """测试不同绑定来源类型"""

    def test_user_input_binding(self):
        """测试用户输入绑定"""
        binding = ParameterBinding(
            source="query",
            source_type=BindingSourceType.USER_INPUT,
            confidence=1.0,
        )
        assert binding.source_type == BindingSourceType.USER_INPUT

    def test_step_output_binding(self):
        """测试步骤输出绑定"""
        binding = ParameterBinding(
            source="step_1.output.result",
            source_type=BindingSourceType.STEP_OUTPUT,
            confidence=0.9,
        )
        assert binding.source_type == BindingSourceType.STEP_OUTPUT

    def test_state_binding(self):
        """测试状态绑定"""
        binding = ParameterBinding(
            source="documents",
            source_type=BindingSourceType.STATE,
            confidence=0.8,
        )
        assert binding.source_type == BindingSourceType.STATE

    def test_literal_binding(self):
        """测试字面量绑定"""
        binding = ParameterBinding(
            source="",
            source_type=BindingSourceType.LITERAL,
            confidence=1.0,
            default_value="default_value",
        )
        assert binding.source_type == BindingSourceType.LITERAL
        assert binding.default_value == "default_value"

    def test_generated_binding(self):
        """测试生成绑定（需要 LLM 推理）"""
        binding = ParameterBinding(
            source="",
            source_type=BindingSourceType.GENERATED,
            confidence=0.3,
            fallback=BindingFallbackPolicy.LLM_INFER,
        )
        assert binding.source_type == BindingSourceType.GENERATED
        assert binding.fallback == BindingFallbackPolicy.LLM_INFER


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
