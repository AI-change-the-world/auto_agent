"""
快速测试 Replan 优化功能

简化版测试，验证：
1. 工作记忆 (CrossStepWorkingMemory)
2. 一致性检查 (GlobalConsistencyChecker)
3. 工具级 replan_policy

使用方法:
    python examples/replan_quick_test.py
"""

import asyncio
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_working_memory_in_context():
    """测试工作记忆在执行上下文中的使用"""
    print("\n" + "=" * 60)
    print("测试 1: 工作记忆在执行上下文中的使用")
    print("=" * 60)

    from auto_agent.core.context import ExecutionContext

    # 创建执行上下文
    ctx = ExecutionContext(
        query="创建一个用户管理 API",
        user_id="test_user",
        plan_summary="1. 设计 API\n2. 生成模型\n3. 实现服务",
    )

    # 模拟步骤 1：设计 API（添加设计决策和约束）
    ctx.working_memory.add_decision(
        decision="使用 RESTful 风格设计 API",
        reason="符合行业标准，易于理解和维护",
        step_id="step_1",
        tags=["architecture", "api"],
    )

    ctx.working_memory.add_constraint(
        constraint="所有 ID 字段必须使用整数类型",
        source="step_1",
        priority="critical",
    )

    ctx.working_memory.add_constraint(
        constraint="响应必须包含 success 字段",
        source="step_1",
        priority="high",
    )

    ctx.working_memory.add_interface(
        name="GET /api/users/{id}",
        definition={
            "method": "GET",
            "path": "/api/users/{id}",
            "params": {"id": "int"},
            "response": {"id": "int", "name": "str", "email": "str"},
        },
        defined_by="step_1",
        interface_type="api",
    )

    # 模拟步骤 2：生成模型（添加待办）
    ctx.working_memory.add_todo(
        todo="为 User 模型添加验证逻辑",
        created_by="step_2",
        priority="normal",
    )

    # 记录步骤
    ctx.record_step(
        step_id="step_1",
        step_num=1,
        tool_name="design_api",
        description="设计 API 接口",
        arguments={"project_name": "user-api"},
        output={"endpoints": [{"path": "/api/users/{id}"}]},
        success=True,
    )

    # 生成 LLM 上下文
    llm_context = ctx.to_llm_context(include_memories=False)

    print("\n✅ 工作记忆内容:")
    print(f"   - 设计决策: {len(ctx.working_memory.design_decisions)} 条")
    print(f"   - 约束条件: {len(ctx.working_memory.constraints)} 条")
    print(f"   - 待办事项: {len(ctx.working_memory.todos)} 条")
    print(f"   - 接口定义: {len(ctx.working_memory.interfaces)} 个")

    print("\n✅ LLM 上下文包含:")
    if "设计决策" in llm_context:
        print("   ✓ 设计决策")
    if "约束" in llm_context:
        print("   ✓ 约束条件")
    if "待处理" in llm_context:
        print("   ✓ 待办事项")
    if "接口" in llm_context:
        print("   ✓ 接口定义")

    # 显示工作记忆上下文
    wm_context = ctx.working_memory.get_relevant_context("")
    print("\n📋 工作记忆上下文预览:")
    print("-" * 40)
    print(wm_context[:500] if len(wm_context) > 500 else wm_context)
    print("-" * 40)

    return True


async def test_consistency_checker_in_context():
    """测试一致性检查器在执行上下文中的使用"""
    print("\n" + "=" * 60)
    print("测试 2: 一致性检查器在执行上下文中的使用")
    print("=" * 60)

    from auto_agent.core.context import ExecutionContext

    # 创建执行上下文
    ctx = ExecutionContext(
        query="创建一个用户管理 API",
        user_id="test_user",
    )

    # 模拟步骤 1：注册 API 设计检查点
    ctx.consistency_checker.register_checkpoint(
        step_id="step_1",
        artifact_type="interface",
        key_elements={
            "endpoints": [
                {"method": "GET", "path": "/api/users/{id}", "params": {"id": "int"}},
                {"method": "POST", "path": "/api/users", "body": {"name": "str", "email": "str"}},
            ],
            "models": {
                "User": {"id": "int", "name": "str", "email": "str"},
            },
        },
        constraints_for_future=[
            "所有端点必须使用定义的 User 模型",
            "ID 参数必须是整数类型",
        ],
        description="用户管理 API 接口设计",
    )

    # 模拟步骤 2：注册模型代码检查点
    ctx.consistency_checker.register_checkpoint(
        step_id="step_2",
        artifact_type="code",
        key_elements={
            "classes": ["User", "UserCreate", "UserUpdate"],
            "fields": {
                "User": {"id": "int", "name": "str", "email": "str"},
            },
        },
        constraints_for_future=[
            "服务层必须使用这些模型类",
        ],
        description="用户数据模型代码",
    )

    # 模拟检测到违规
    ctx.consistency_checker.add_violation(
        checkpoint_id="step_1",
        current_step_id="step_3",
        violation_type="interface_mismatch",
        severity="warning",
        description="服务实现中 get_user 函数的参数类型与 API 设计不一致",
        suggestion="将 user_id 参数类型从 str 改为 int",
    )

    print("\n✅ 一致性检查器状态:")
    print(f"   - 检查点: {len(ctx.consistency_checker.checkpoints)} 个")
    print(f"   - 违规记录: {len(ctx.consistency_checker.violations)} 条")
    print(f"   - 有严重违规: {ctx.consistency_checker.has_critical_violations()}")

    # 显示检查点
    print("\n📋 注册的检查点:")
    for step_id, cp in ctx.consistency_checker.checkpoints.items():
        print(f"   [{cp.artifact_type}] {cp.description}")
        print(f"      约束: {cp.constraints_for_future[:2]}")

    # 显示违规
    print("\n⚠️  违规记录:")
    for v in ctx.consistency_checker.violations:
        print(f"   [{v.severity}] {v.description}")
        print(f"      建议: {v.suggestion}")

    # 生成 LLM 上下文
    llm_context = ctx.to_llm_context(include_memories=False)
    if "一致性检查点" in llm_context:
        print("\n✅ LLM 上下文包含一致性检查点信息")

    # 显示一致性上下文
    cc_context = ctx.consistency_checker.get_context_for_llm()
    print("\n📋 一致性检查上下文预览:")
    print("-" * 40)
    print(cc_context[:500] if len(cc_context) > 500 else cc_context)
    print("-" * 40)

    return True


async def test_tool_replan_policy():
    """测试工具级 replan_policy"""
    print("\n" + "=" * 60)
    print("测试 3: 工具级 Replan 策略")
    print("=" * 60)

    from auto_agent.models import ToolDefinition, ToolParameter, ToolReplanPolicy

    # 创建带有不同 replan_policy 的工具定义
    tools = [
        ToolDefinition(
            name="simple_query",
            description="简单查询工具",
            parameters=[],
            replan_policy=ToolReplanPolicy(
                high_impact=False,
                requires_consistency_check=False,
            ),
        ),
        ToolDefinition(
            name="design_api",
            description="API 设计工具",
            parameters=[],
            replan_policy=ToolReplanPolicy(
                high_impact=True,
                requires_consistency_check=True,
                force_replan_check=False,
            ),
        ),
        ToolDefinition(
            name="generate_code",
            description="代码生成工具",
            parameters=[],
            replan_policy=ToolReplanPolicy(
                high_impact=True,
                requires_consistency_check=True,
                replan_condition="如果生成的代码超过 100 行",
                consistency_check_against=["interface", "schema"],
            ),
        ),
    ]

    print("\n✅ 工具 Replan 策略:")
    for tool in tools:
        policy = tool.replan_policy
        print(f"\n   [{tool.name}]")
        print(f"      high_impact: {policy.high_impact}")
        print(f"      requires_consistency_check: {policy.requires_consistency_check}")
        if policy.replan_condition:
            print(f"      replan_condition: {policy.replan_condition}")
        if policy.consistency_check_against:
            print(f"      consistency_check_against: {policy.consistency_check_against}")

    return True


async def test_execution_strategy():
    """测试执行策略选择"""
    print("\n" + "=" * 60)
    print("测试 4: 执行策略选择")
    print("=" * 60)

    from auto_agent.models import ExecutionStrategy, TaskComplexity

    # 不同复杂度对应的策略
    strategies = {
        TaskComplexity.SIMPLE: ExecutionStrategy(
            enable_replan=False,
            replan_trigger="on_failure",
        ),
        TaskComplexity.MODERATE: ExecutionStrategy(
            enable_replan=True,
            replan_trigger="on_failure",
        ),
        TaskComplexity.COMPLEX: ExecutionStrategy(
            enable_replan=True,
            replan_trigger="periodic",
            replan_interval=3,
            enable_consistency_check=True,
        ),
        TaskComplexity.PROJECT: ExecutionStrategy(
            enable_replan=True,
            replan_trigger="proactive",
            replan_interval=2,
            enable_consistency_check=True,
            enable_lookahead=True,
            require_phase_review=True,
        ),
    }

    print("\n✅ 不同复杂度的执行策略:")
    for complexity, strategy in strategies.items():
        print(f"\n   [{complexity.value}]")
        print(f"      enable_replan: {strategy.enable_replan}")
        print(f"      replan_trigger: {strategy.replan_trigger}")
        print(f"      replan_interval: {strategy.replan_interval}")
        print(f"      enable_consistency_check: {strategy.enable_consistency_check}")
        if strategy.require_phase_review:
            print(f"      require_phase_review: {strategy.require_phase_review}")

    return True


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 Replan 优化功能快速测试")
    print("=" * 60)

    results = []

    results.append(("工作记忆在上下文中", await test_working_memory_in_context()))
    results.append(("一致性检查器在上下文中", await test_consistency_checker_in_context()))
    results.append(("工具级 Replan 策略", await test_tool_replan_policy()))
    results.append(("执行策略选择", await test_execution_strategy()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {status} - {name}")

    print(f"\n   总计: {passed}/{total} 通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
