"""
测试一致性检查功能
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from auto_agent.core.context import ExecutionContext, GlobalConsistencyChecker


def test_consistency_checker_for_project():
    """测试项目生成场景下的一致性检查"""
    print("\n" + "=" * 60)
    print("测试: 项目生成场景的一致性检查")
    print("=" * 60)

    # 创建执行上下文
    ctx = ExecutionContext(
        query="生成一个博客系统 API",
        user_id="developer",
    )

    # 模拟步骤 1: 需求分析 - 注册检查点
    ctx.consistency_checker.register_checkpoint(
        step_id="step_1",
        artifact_type="requirements",
        key_elements={
            "entities": ["User", "Post", "Comment"],
            "id_type": "int",
            "auth_required": True,
        },
        constraints_for_future=[
            "所有实体必须有 id 字段，类型为 int",
            "所有端点必须有认证",
        ],
        description="博客系统需求分析",
    )

    # 模拟步骤 2: API 设计 - 注册检查点
    ctx.consistency_checker.register_checkpoint(
        step_id="step_2",
        artifact_type="interface",
        key_elements={
            "endpoints": [
                {"method": "GET", "path": "/api/posts", "params": {"page": "int"}},
                {"method": "POST", "path": "/api/posts", "body": {"title": "str"}},
                {"method": "GET", "path": "/api/posts/{id}", "params": {"id": "int"}},
            ],
            "models": ["PostCreate", "PostResponse", "PostList"],
        },
        constraints_for_future=[
            "服务层必须实现所有端点对应的方法",
            "路由层必须使用定义的模型类",
        ],
        description="REST API 接口设计",
    )

    # 模拟步骤 3: 模型生成 - 注册检查点
    ctx.consistency_checker.register_checkpoint(
        step_id="step_3",
        artifact_type="code",
        key_elements={
            "classes": ["Post", "PostCreate", "PostUpdate", "PostResponse"],
            "fields": {
                "Post": {"id": "int", "title": "str", "content": "str"},
            },
        },
        constraints_for_future=[
            "服务层必须使用这些模型类",
            "路由层必须使用这些模型类作为请求/响应类型",
        ],
        description="Pydantic 数据模型",
    )

    print("\n✅ 注册的检查点:")
    for step_id, cp in ctx.consistency_checker.checkpoints.items():
        print(f"   [{cp.artifact_type}] {cp.description}")
        print(f"      约束: {cp.constraints_for_future[:2]}")

    # 模拟检测到一致性违规
    ctx.consistency_checker.add_violation(
        checkpoint_id="step_2",
        current_step_id="step_4",
        violation_type="interface_mismatch",
        severity="warning",
        description="服务层 get_post 方法的参数类型与 API 设计不一致",
        suggestion="将 post_id 参数类型从 str 改为 int",
    )

    ctx.consistency_checker.add_violation(
        checkpoint_id="step_3",
        current_step_id="step_5",
        violation_type="model_mismatch",
        severity="critical",
        description="路由层使用了未定义的模型类 PostDetail",
        suggestion="使用已定义的 PostResponse 类",
    )

    print("\n⚠️  违规记录:")
    for v in ctx.consistency_checker.violations:
        print(f"   [{v.severity}] {v.description}")
        print(f"      建议: {v.suggestion}")

    # 检查是否有严重违规
    has_critical = ctx.consistency_checker.has_critical_violations()
    print(f"\n✅ 有严重违规: {has_critical}")

    # 获取特定类型的检查点
    interface_checkpoints = ctx.consistency_checker.get_relevant_checkpoints(
        artifact_types=["interface"]
    )
    print(f"✅ 接口类型检查点: {len(interface_checkpoints)} 个")

    # 生成 LLM 上下文
    cc_context = ctx.consistency_checker.get_context_for_llm()
    print("\n📋 一致性检查上下文预览:")
    print("-" * 40)
    print(cc_context[:500] if len(cc_context) > 500 else cc_context)
    print("-" * 40)

    return has_critical and len(ctx.consistency_checker.checkpoints) == 3


def test_consistency_checker_persistence():
    """测试一致性检查器的持久化"""
    print("\n" + "=" * 60)
    print("测试: 一致性检查器持久化")
    print("=" * 60)

    # 创建并填充检查器
    checker = GlobalConsistencyChecker()
    checker.register_checkpoint(
        step_id="step_1",
        artifact_type="interface",
        key_elements={"endpoints": ["/api/users"]},
        constraints_for_future=["必须实现用户端点"],
        description="用户 API",
    )
    checker.add_violation(
        checkpoint_id="step_1",
        current_step_id="step_2",
        violation_type="missing_endpoint",
        severity="warning",
        description="缺少用户端点实现",
    )

    # 序列化
    data = checker.to_dict()
    print(f"\n✅ 序列化成功: {len(str(data))} 字符")

    # 反序列化
    checker2 = GlobalConsistencyChecker.from_dict(data)
    print(f"✅ 反序列化成功:")
    print(f"   - 检查点: {len(checker2.checkpoints)} 个")
    print(f"   - 违规: {len(checker2.violations)} 条")

    return len(checker2.checkpoints) == 1 and len(checker2.violations) == 1


def test_get_relevant_checkpoints():
    """测试获取相关检查点"""
    print("\n" + "=" * 60)
    print("测试: 获取相关检查点")
    print("=" * 60)

    checker = GlobalConsistencyChecker()

    # 注册多个检查点
    checker.register_checkpoint(
        step_id="step_1",
        artifact_type="requirements",
        key_elements={"entities": ["User"]},
        constraints_for_future=[],
        description="需求分析",
    )
    checker.register_checkpoint(
        step_id="step_2",
        artifact_type="interface",
        key_elements={"endpoints": ["/api/users"]},
        constraints_for_future=[],
        description="API 设计",
    )
    checker.register_checkpoint(
        step_id="step_3",
        artifact_type="code",
        key_elements={"classes": ["User"]},
        constraints_for_future=[],
        description="模型代码",
    )

    # 获取相关检查点
    relevant = checker.get_relevant_checkpoints(
        artifact_types=["interface", "code"],
    )

    print(f"\n✅ 相关检查点 (interface, code): {len(relevant)} 个")
    for cp in relevant:
        print(f"   - [{cp.artifact_type}] {cp.description}")

    return len(relevant) == 2


if __name__ == "__main__":
    results = []

    results.append(("项目生成场景的一致性检查", test_consistency_checker_for_project()))
    results.append(("一致性检查器持久化", test_consistency_checker_persistence()))
    results.append(("获取相关检查点", test_get_relevant_checkpoints()))

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
