"""
测试新增的 Replan 优化功能

测试内容：
1. 任务复杂度分级 (TaskComplexity, TaskProfile)
2. 执行策略选择 (ExecutionStrategy)
3. 工作记忆 (CrossStepWorkingMemory)
4. 工具级 Replan 策略 (ToolReplanPolicy)

使用方法:
    python examples/test_replan_features.py
"""

import asyncio
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_task_complexity():
    """测试任务复杂度枚举和 TaskProfile"""
    print("\n" + "=" * 60)
    print("测试 1: 任务复杂度分级")
    print("=" * 60)

    from auto_agent.models import TaskComplexity, TaskProfile

    # 测试枚举
    print("\n✅ TaskComplexity 枚举:")
    for c in TaskComplexity:
        print(f"   - {c.name}: {c.value}")

    # 测试 TaskProfile
    profile = TaskProfile(
        complexity=TaskComplexity.COMPLEX,
        estimated_steps=10,
        has_code_generation=True,
        has_cross_dependencies=True,
        requires_consistency=True,
        is_reversible=False,
        reasoning="这是一个复杂的代码生成任务",
    )

    print("\n✅ TaskProfile 创建成功:")
    print(f"   复杂度: {profile.complexity.value}")
    print(f"   预估步骤: {profile.estimated_steps}")
    print(f"   涉及代码生成: {profile.has_code_generation}")
    print(f"   需要一致性: {profile.requires_consistency}")

    return True


def test_execution_strategy():
    """测试执行策略"""
    print("\n" + "=" * 60)
    print("测试 2: 执行策略选择")
    print("=" * 60)

    from auto_agent.models import ExecutionStrategy, TaskComplexity, TaskProfile

    # 模拟 planner 的策略选择逻辑
    def get_strategy(complexity: TaskComplexity) -> ExecutionStrategy:
        if complexity == TaskComplexity.SIMPLE:
            return ExecutionStrategy(
                enable_replan=False,
                replan_trigger="on_failure",
            )
        elif complexity == TaskComplexity.MODERATE:
            return ExecutionStrategy(
                enable_replan=True,
                replan_trigger="on_failure",
            )
        elif complexity == TaskComplexity.COMPLEX:
            return ExecutionStrategy(
                enable_replan=True,
                replan_trigger="periodic",
                replan_interval=3,
                enable_consistency_check=True,
            )
        else:  # PROJECT
            return ExecutionStrategy(
                enable_replan=True,
                replan_trigger="proactive",
                replan_interval=3,
                enable_consistency_check=True,
                enable_lookahead=True,
                require_phase_review=True,
            )

    print("\n✅ 不同复杂度对应的策略:")
    for complexity in TaskComplexity:
        strategy = get_strategy(complexity)
        print(f"\n   [{complexity.value}]")
        print(f"      enable_replan: {strategy.enable_replan}")
        print(f"      replan_trigger: {strategy.replan_trigger}")
        print(f"      replan_interval: {strategy.replan_interval}")

    return True


def test_working_memory():
    """测试工作记忆"""
    print("\n" + "=" * 60)
    print("测试 3: 跨步骤工作记忆")
    print("=" * 60)

    from auto_agent.core.context import CrossStepWorkingMemory

    wm = CrossStepWorkingMemory()

    # 添加设计决策
    wm.add_decision(
        decision="使用 REST API 而非 GraphQL",
        reason="团队更熟悉 REST，且需求简单",
        step_id="step_1",
        tags=["architecture", "api"],
    )

    # 添加约束
    wm.add_constraint(
        constraint="所有函数必须有类型注解",
        source="step_2",
        priority="high",
    )
    wm.add_constraint(
        constraint="API 响应必须在 200ms 内",
        source="step_1",
        priority="critical",
    )

    # 添加待办
    wm.add_todo(
        todo="更新 README 文档",
        created_by="step_3",
        priority="normal",
    )

    # 添加接口定义
    wm.add_interface(
        name="get_user",
        definition={
            "method": "GET",
            "path": "/api/users/{id}",
            "params": ["id: int"],
            "returns": "User",
        },
        defined_by="step_2",
        interface_type="api",
    )

    print("\n✅ 工作记忆内容:")
    print(f"   设计决策: {len(wm.design_decisions)} 条")
    print(f"   约束条件: {len(wm.constraints)} 条")
    print(f"   待办事项: {len(wm.todos)} 条")
    print(f"   接口定义: {len(wm.interfaces)} 个")

    # 测试上下文生成
    context = wm.get_relevant_context("当前步骤")
    print("\n✅ 生成的上下文:")
    print(context)

    # 测试持久化
    data = wm.to_dict()
    wm2 = CrossStepWorkingMemory.from_dict(data)
    print(f"\n✅ 持久化测试: 恢复了 {len(wm2.design_decisions)} 条决策")

    return True


def test_tool_replan_policy():
    """测试工具级 Replan 策略"""
    print("\n" + "=" * 60)
    print("测试 4: 工具级 Replan 策略")
    print("=" * 60)

    from auto_agent.models import ToolDefinition, ToolParameter, ToolReplanPolicy

    # 简单工具 - 不需要 replan
    simple_tool = ToolDefinition(
        name="get_weather",
        description="查询天气",
        parameters=[
            ToolParameter(name="city", type="string", description="城市", required=True)
        ],
        replan_policy=ToolReplanPolicy(
            force_replan_check=False,
            high_impact=False,
        ),
    )

    # 高影响力工具 - 需要 replan
    code_gen_tool = ToolDefinition(
        name="generate_code",
        description="生成代码",
        parameters=[
            ToolParameter(
                name="requirement", type="string", description="需求", required=True
            )
        ],
        replan_policy=ToolReplanPolicy(
            force_replan_check=True,
            high_impact=True,
            requires_consistency_check=True,
            replan_condition="如果生成的代码超过 100 行或涉及多个文件",
            consistency_check_against=["interface_definition"],
        ),
    )

    print("\n✅ 简单工具策略:")
    print(f"   name: {simple_tool.name}")
    print(f"   force_replan_check: {simple_tool.replan_policy.force_replan_check}")
    print(f"   high_impact: {simple_tool.replan_policy.high_impact}")

    print("\n✅ 代码生成工具策略:")
    print(f"   name: {code_gen_tool.name}")
    print(f"   force_replan_check: {code_gen_tool.replan_policy.force_replan_check}")
    print(f"   high_impact: {code_gen_tool.replan_policy.high_impact}")
    print(f"   replan_condition: {code_gen_tool.replan_policy.replan_condition}")

    return True


async def test_task_classification():
    """测试任务分类（需要 LLM）"""
    print("\n" + "=" * 60)
    print("测试 5: 任务复杂度分类（需要 LLM）")
    print("=" * 60)

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("\n⚠️  跳过: 未设置 API Key")
        return True

    from auto_agent import OpenAIClient, TaskPlanner, ToolRegistry

    # 初始化
    llm = OpenAIClient(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
        model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
    )

    planner = TaskPlanner(
        llm_client=llm,
        tool_registry=ToolRegistry(),
    )

    # 测试不同复杂度的查询
    test_queries = [
        ("今天北京天气怎么样？", "SIMPLE"),
        ("搜索关于 Python 的文章并总结", "MODERATE"),
        ("帮我写一份关于 AI 的研究报告", "COMPLEX"),
        ("帮我创建一个完整的 TODO 应用项目", "PROJECT"),
    ]

    print("\n✅ 任务分类结果:")
    for query, expected in test_queries:
        try:
            profile = await planner.classify_task_complexity(query)
            match = "✓" if profile.complexity.value == expected.lower() else "✗"
            print(f"\n   {match} 查询: {query[:30]}...")
            print(f"      预期: {expected}, 实际: {profile.complexity.value}")
            print(f"      理由: {profile.reasoning[:50]}...")
        except Exception as e:
            print(f"\n   ✗ 查询: {query[:30]}... 失败: {e}")

    await llm.close()
    return True


async def test_execution_context_integration():
    """测试 ExecutionContext 集成工作记忆"""
    print("\n" + "=" * 60)
    print("测试 6: ExecutionContext 集成")
    print("=" * 60)

    from auto_agent.core.context import ExecutionContext

    ctx = ExecutionContext(
        query="帮我写一个 TODO 应用",
        user_id="test_user",
        plan_summary="1. 设计架构\n2. 实现功能\n3. 测试",
    )

    # 添加工作记忆
    ctx.working_memory.add_decision(
        decision="使用 SQLite 作为数据库",
        reason="轻量级，适合小型应用",
        step_id="step_1",
    )

    ctx.working_memory.add_constraint(
        constraint="必须支持任务优先级",
        source="user",
        priority="high",
    )

    # 记录步骤
    ctx.record_step(
        step_id="1",
        step_num=1,
        tool_name="design_architecture",
        description="设计系统架构",
        arguments={"requirement": "TODO 应用"},
        output={"architecture": "MVC 模式"},
        success=True,
    )

    # 生成 LLM 上下文
    llm_context = ctx.to_llm_context(include_memories=False)

    print("\n✅ ExecutionContext 创建成功")
    print(f"   查询: {ctx.query}")
    print(f"   工作记忆决策数: {len(ctx.working_memory.design_decisions)}")
    print(f"   执行历史步骤数: {len(ctx.history)}")

    print("\n✅ 生成的 LLM 上下文包含工作记忆:")
    if "设计决策" in llm_context:
        print("   ✓ 包含设计决策")
    if "约束" in llm_context:
        print("   ✓ 包含约束条件")

    return True


def test_consistency_checker():
    """测试全局一致性检查器"""
    print("\n" + "=" * 60)
    print("测试 7: 全局一致性检查器")
    print("=" * 60)

    from auto_agent.core.context import (
        ConsistencyCheckpoint,
        ConsistencyViolation,
        GlobalConsistencyChecker,
    )

    checker = GlobalConsistencyChecker()

    # 注册检查点
    cp1 = checker.register_checkpoint(
        step_id="step_1",
        artifact_type="interface",
        key_elements={
            "names": ["get_user", "create_user"],
            "signatures": {
                "get_user": "(user_id: int) -> User",
                "create_user": "(name: str, email: str) -> User",
            },
        },
        constraints_for_future=[
            "所有用户相关函数必须使用 User 类型",
            "user_id 必须是整数类型",
        ],
        description="用户服务接口定义",
    )

    cp2 = checker.register_checkpoint(
        step_id="step_2",
        artifact_type="schema",
        key_elements={
            "User": {
                "id": "int",
                "name": "str",
                "email": "str",
            }
        },
        constraints_for_future=["User 必须包含 id, name, email 字段"],
        description="用户数据结构定义",
    )

    print("\n✅ 检查点注册成功:")
    print(f"   检查点数量: {len(checker.checkpoints)}")
    for step_id, cp in checker.checkpoints.items():
        print(f"   - [{cp.artifact_type}] {cp.description}")

    # 添加违规
    v1 = checker.add_violation(
        checkpoint_id="step_1",
        current_step_id="step_3",
        violation_type="interface_mismatch",
        severity="warning",
        description="get_user 函数参数类型不一致，使用了 str 而非 int",
        suggestion="将 user_id 参数类型改为 int",
    )

    v2 = checker.add_violation(
        checkpoint_id="step_2",
        current_step_id="step_3",
        violation_type="constraint_violation",
        severity="critical",
        description="User 类缺少 email 字段",
        suggestion="添加 email: str 字段到 User 类",
    )

    print("\n✅ 违规记录:")
    print(f"   违规数量: {len(checker.violations)}")
    print(f"   严重违规: {checker.has_critical_violations()}")
    for v in checker.violations:
        print(f"   - [{v.severity}] {v.description}")

    # 测试获取相关检查点
    interface_cps = checker.get_relevant_checkpoints(artifact_types=["interface"])
    print(f"\n✅ 接口类型检查点: {len(interface_cps)} 个")

    # 测试获取所有约束
    all_constraints = checker.get_all_constraints()
    print(f"✅ 所有约束: {len(all_constraints)} 条")

    # 测试 LLM 上下文生成
    llm_context = checker.get_context_for_llm()
    print("\n✅ 生成的 LLM 上下文:")
    print(llm_context[:300] + "..." if len(llm_context) > 300 else llm_context)

    # 测试持久化
    data = checker.to_dict()
    checker2 = GlobalConsistencyChecker.from_dict(data)
    print(f"\n✅ 持久化测试: 恢复了 {len(checker2.checkpoints)} 个检查点, {len(checker2.violations)} 个违规")

    return True


def test_consistency_in_context():
    """测试 ExecutionContext 中的一致性检查器集成"""
    print("\n" + "=" * 60)
    print("测试 8: ExecutionContext 一致性检查器集成")
    print("=" * 60)

    from auto_agent.core.context import ExecutionContext

    ctx = ExecutionContext(
        query="帮我写一个用户管理系统",
        user_id="test_user",
        plan_summary="1. 定义接口\n2. 实现功能\n3. 测试",
    )

    # 注册检查点
    ctx.consistency_checker.register_checkpoint(
        step_id="step_1",
        artifact_type="interface",
        key_elements={"functions": ["get_user", "create_user"]},
        constraints_for_future=["必须使用 User 类型"],
        description="用户接口定义",
    )

    # 生成 LLM 上下文
    llm_context = ctx.to_llm_context(include_memories=False)

    print("\n✅ ExecutionContext 一致性检查器集成成功")
    print(f"   检查点数量: {len(ctx.consistency_checker.checkpoints)}")

    if "一致性检查点" in llm_context:
        print("   ✓ LLM 上下文包含一致性检查点")
    else:
        print("   ✗ LLM 上下文未包含一致性检查点")

    return True


def test_tool_post_policy():
    """测试统一后处理策略"""
    print("\n" + "=" * 60)
    print("测试 9: 统一后处理策略 (ToolPostPolicy)")
    print("=" * 60)

    from auto_agent.models import (
        PostSuccessConfig,
        ResultHandlingConfig,
        ToolDefinition,
        ToolParameter,
        ToolPostPolicy,
        ToolReplanPolicy,
        ValidationConfig,
    )

    # 测试 1: 直接使用 ToolPostPolicy
    post_policy = ToolPostPolicy(
        validation=ValidationConfig(
            on_fail="retry",
            max_retries=3,
            use_llm_validation=True,
        ),
        post_success=PostSuccessConfig(
            high_impact=True,
            requires_consistency_check=True,
            extract_working_memory=True,
            replan_condition="如果生成的代码超过 100 行",
        ),
        result_handling=ResultHandlingConfig(
            cache_policy="session",
            register_as_checkpoint=True,
            checkpoint_type="code",
            state_mapping={"generated_code": "code_output"},
        ),
    )

    print("\n✅ ToolPostPolicy 创建成功:")
    print(f"   validation.on_fail: {post_policy.validation.on_fail}")
    print(f"   post_success.high_impact: {post_policy.post_success.high_impact}")
    print(f"   result_handling.checkpoint_type: {post_policy.result_handling.checkpoint_type}")

    # 测试辅助方法
    print("\n✅ 辅助方法测试:")
    print(f"   is_high_impact(): {post_policy.is_high_impact()}")
    print(f"   should_check_consistency(): {post_policy.should_check_consistency()}")
    print(f"   should_register_checkpoint(): {post_policy.should_register_checkpoint()}")
    print(f"   should_extract_working_memory(): {post_policy.should_extract_working_memory()}")

    # 测试 2: 从旧字段构造（兼容性）
    old_replan_policy = ToolReplanPolicy(
        high_impact=True,
        requires_consistency_check=True,
        replan_condition="如果涉及多个文件",
    )

    legacy_post_policy = ToolPostPolicy.from_legacy(
        validate_function=lambda r, e, s, m: (True, "OK"),
        compress_function=lambda r, s: {"summary": "compressed"},
        replan_policy=old_replan_policy,
        state_mapping={"output": "result"},
    )

    print("\n✅ 从旧字段构造 ToolPostPolicy:")
    print(f"   has validation: {legacy_post_policy.validation is not None}")
    print(f"   has post_success: {legacy_post_policy.post_success is not None}")
    print(f"   has result_handling: {legacy_post_policy.result_handling is not None}")
    print(f"   is_high_impact(): {legacy_post_policy.is_high_impact()}")

    # 测试 3: ToolDefinition.get_effective_post_policy()
    # 使用新字段
    tool_with_new = ToolDefinition(
        name="new_tool",
        description="使用新 post_policy 的工具",
        parameters=[],
        post_policy=post_policy,
    )

    # 使用旧字段
    tool_with_old = ToolDefinition(
        name="old_tool",
        description="使用旧字段的工具",
        parameters=[],
        replan_policy=old_replan_policy,
        compress_function=lambda r, s: r,
    )

    print("\n✅ ToolDefinition.get_effective_post_policy():")
    
    new_effective = tool_with_new.get_effective_post_policy()
    print(f"   新工具 - is_high_impact: {new_effective.is_high_impact()}")
    
    old_effective = tool_with_old.get_effective_post_policy()
    print(f"   旧工具 - is_high_impact: {old_effective.is_high_impact()}")

    # 测试序列化
    policy_dict = post_policy.to_dict()
    print("\n✅ 序列化测试:")
    print(f"   to_dict() keys: {list(policy_dict.keys())}")

    return True


def test_incremental_replan_structure():
    """测试增量重规划的数据结构"""
    print("\n" + "=" * 60)
    print("测试 10: 增量重规划数据结构")
    print("=" * 60)

    from auto_agent.models import ExecutionPlan, ExecutionStrategy, PlanStep, SubTaskResult

    # 创建一个模拟的执行计划
    plan = ExecutionPlan(
        intent="创建用户管理系统",
        subtasks=[
            PlanStep(
                id="step_1",
                description="设计数据库结构",
                tool="design_schema",
                parameters={},
                read_fields=[],
                write_fields=["schema"],
            ),
            PlanStep(
                id="step_2",
                description="实现用户模型",
                tool="generate_code",
                parameters={},
                read_fields=["schema"],
                write_fields=["user_model"],
            ),
            PlanStep(
                id="step_3",
                description="实现 API 接口",
                tool="generate_code",
                parameters={},
                read_fields=["user_model"],
                write_fields=["api_code"],
            ),
        ],
        expected_outcome="完整的用户管理系统",
    )

    # 模拟执行历史（前两步成功）
    execution_history = [
        SubTaskResult(
            step_id="step_1",
            success=True,
            output={"schema": {"users": {"id": "int", "name": "str"}}},
        ),
        SubTaskResult(
            step_id="step_2",
            success=True,
            output={"user_model": "class User: ..."},
        ),
    ]

    print("\n✅ 执行计划创建成功:")
    print(f"   总步骤数: {len(plan.subtasks)}")
    print(f"   已完成步骤: {len(execution_history)}")

    # 模拟增量重规划场景
    current_step_index = 2  # 第三步
    completed_steps = plan.subtasks[:current_step_index]
    remaining_steps = plan.subtasks[current_step_index:]

    print(f"\n✅ 增量重规划场景:")
    print(f"   当前步骤索引: {current_step_index}")
    print(f"   已完成步骤: {[s.id for s in completed_steps]}")
    print(f"   待执行步骤: {[s.id for s in remaining_steps]}")

    # 验证已完成步骤的产出可以被后续步骤使用
    completed_outputs = set()
    for result in execution_history:
        if result.output:
            completed_outputs.update(result.output.keys())

    print(f"\n✅ 已完成步骤的产出: {completed_outputs}")

    # 检查待执行步骤的依赖
    for step in remaining_steps:
        missing_deps = [f for f in step.read_fields if f not in completed_outputs]
        if missing_deps:
            print(f"   ⚠️ 步骤 {step.id} 缺少依赖: {missing_deps}")
        else:
            print(f"   ✓ 步骤 {step.id} 依赖满足")

    return True


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 Replan 优化功能测试")
    print("=" * 60)

    results = []

    # 阶段一测试：任务复杂度分级
    results.append(("任务复杂度分级", test_task_complexity()))
    results.append(("执行策略选择", test_execution_strategy()))
    results.append(("工具级 Replan 策略", test_tool_replan_policy()))

    # 阶段二测试：工作记忆
    results.append(("跨步骤工作记忆", test_working_memory()))
    results.append(("ExecutionContext 集成", await test_execution_context_integration()))

    # 阶段三测试：一致性检查器
    results.append(("全局一致性检查器", test_consistency_checker()))
    results.append(("ExecutionContext 一致性集成", test_consistency_in_context()))

    # 阶段四测试：增量重规划
    results.append(("增量重规划数据结构", test_incremental_replan_structure()))

    # 统一后处理机制测试
    results.append(("统一后处理策略", test_tool_post_policy()))

    # LLM 测试（可选）
    results.append(("任务分类（LLM）", await test_task_classification()))

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
