"""
测试工作记忆功能
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from auto_agent.core.context import ExecutionContext


def test_working_memory_for_project():
    """测试项目生成场景下的工作记忆"""
    print("\n" + "=" * 60)
    print("测试: 项目生成场景的工作记忆")
    print("=" * 60)

    # 创建执行上下文
    ctx = ExecutionContext(
        query="生成一个博客系统 API",
        user_id="developer",
        plan_summary="1. 分析需求\n2. 设计API\n3. 生成模型\n4. 生成服务\n5. 生成路由",
    )

    # 模拟步骤 1: 需求分析 - 添加设计决策
    ctx.working_memory.add_decision(
        decision="使用 RESTful API 风格",
        reason="符合行业标准，易于理解和维护",
        step_id="step_1",
        tags=["architecture", "api"],
    )

    ctx.working_memory.add_decision(
        decision="所有 ID 字段使用整数类型",
        reason="便于数据库索引和查询优化",
        step_id="step_1",
        tags=["data_type"],
    )

    # 添加约束
    ctx.working_memory.add_constraint(
        constraint="所有端点必须有认证",
        source="step_1",
        priority="high",
    )

    ctx.working_memory.add_constraint(
        constraint="响应必须包含 success 字段",
        source="step_1",
        priority="medium",
    )

    # 模拟步骤 2: API 设计 - 添加接口定义
    ctx.working_memory.add_interface(
        name="GET /api/posts",
        definition={
            "method": "GET",
            "path": "/api/posts",
            "params": {"page": "int", "size": "int"},
            "response": {"posts": "list", "total": "int"},
        },
        defined_by="step_2",
        interface_type="api",
    )

    ctx.working_memory.add_interface(
        name="POST /api/posts",
        definition={
            "method": "POST",
            "path": "/api/posts",
            "body": {"title": "str", "content": "str"},
            "response": {"id": "int", "title": "str"},
        },
        defined_by="step_2",
        interface_type="api",
    )

    # 模拟步骤 3: 模型生成 - 添加待办
    ctx.working_memory.add_todo(
        todo="为 Post 模型添加字段验证",
        created_by="step_3",
        priority="normal",
    )

    # 验证工作记忆内容
    print("\n✅ 工作记忆内容:")
    print(f"   - 设计决策: {len(ctx.working_memory.design_decisions)} 条")
    print(f"   - 约束条件: {len(ctx.working_memory.constraints)} 条")
    print(f"   - 接口定义: {len(ctx.working_memory.interfaces)} 个")
    print(f"   - 待办事项: {len(ctx.working_memory.todos)} 条")

    # 生成上下文
    wm_context = ctx.working_memory.get_relevant_context("生成服务层代码")
    print("\n📋 工作记忆上下文预览:")
    print("-" * 40)
    print(wm_context[:600] if len(wm_context) > 600 else wm_context)
    print("-" * 40)

    # 验证 LLM 上下文包含工作记忆
    llm_context = ctx.to_llm_context(include_memories=False)
    
    checks = [
        ("设计决策" in llm_context, "包含设计决策"),
        ("约束" in llm_context, "包含约束条件"),
        ("接口" in llm_context, "包含接口定义"),
    ]

    print("\n✅ LLM 上下文检查:")
    for passed, desc in checks:
        status = "✓" if passed else "✗"
        print(f"   {status} {desc}")

    return all(passed for passed, _ in checks)


def test_working_memory_persistence():
    """测试工作记忆的持久化"""
    print("\n" + "=" * 60)
    print("测试: 工作记忆持久化")
    print("=" * 60)

    from auto_agent.core.context import CrossStepWorkingMemory

    # 创建并填充工作记忆
    wm = CrossStepWorkingMemory()
    wm.add_decision(
        decision="使用 Pydantic v2",
        reason="更好的性能和类型支持",
        step_id="step_1",
    )
    wm.add_constraint(
        constraint="所有字段必须有类型注解",
        source="step_1",
    )

    # 序列化
    data = wm.to_dict()
    print(f"\n✅ 序列化成功: {len(str(data))} 字符")

    # 反序列化
    wm2 = CrossStepWorkingMemory.from_dict(data)
    print(f"✅ 反序列化成功:")
    print(f"   - 设计决策: {len(wm2.design_decisions)} 条")
    print(f"   - 约束条件: {len(wm2.constraints)} 条")

    return len(wm2.design_decisions) == 1 and len(wm2.constraints) == 1


if __name__ == "__main__":
    results = []

    results.append(("项目生成场景的工作记忆", test_working_memory_for_project()))
    results.append(("工作记忆持久化", test_working_memory_persistence()))

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
