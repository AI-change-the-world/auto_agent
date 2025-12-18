"""
测试工具定义和 ToolPostPolicy 配置
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from examples.fullstack_generator.tools import (
    AnalyzeRequirementsTool,
    DesignAPITool,
    GenerateModelsTool,
    GenerateServiceTool,
    GenerateRouterTool,
    GenerateTestsTool,
    ValidateProjectTool,
)
from examples.fullstack_generator.tools_writer import (
    CodeWriterTool,
    ProjectInitTool,
)


def test_tool_post_policy():
    """测试工具的 ToolPostPolicy 配置"""
    print("\n" + "=" * 60)
    print("测试: 工具 ToolPostPolicy 配置")
    print("=" * 60)

    # 创建一个 mock LLM client
    class MockLLMClient:
        pass

    mock_client = MockLLMClient()

    tools = [
        AnalyzeRequirementsTool(mock_client),
        DesignAPITool(mock_client),
        GenerateModelsTool(mock_client),
        GenerateServiceTool(mock_client),
        GenerateRouterTool(mock_client),
        GenerateTestsTool(mock_client),
        ValidateProjectTool(mock_client),
        CodeWriterTool("/tmp/test_output"),
        ProjectInitTool("/tmp/test_output"),
    ]

    print("\n✅ 工具 PostPolicy 配置:")
    for tool in tools:
        defn = tool.definition
        policy = defn.get_effective_post_policy()

        print(f"\n   [{defn.name}]")
        print(f"      category: {defn.category}")
        print(f"      is_high_impact: {policy.is_high_impact()}")
        print(f"      should_check_consistency: {policy.should_check_consistency()}")
        print(f"      should_register_checkpoint: {policy.should_register_checkpoint()}")
        print(f"      should_extract_working_memory: {policy.should_extract_working_memory()}")

        if policy.post_success and policy.post_success.consistency_check_against:
            print(f"      consistency_check_against: {policy.post_success.consistency_check_against}")

        if policy.result_handling and policy.result_handling.checkpoint_type:
            print(f"      checkpoint_type: {policy.result_handling.checkpoint_type}")

    return True


def test_tool_param_aliases():
    """测试工具的参数别名配置"""
    print("\n" + "=" * 60)
    print("测试: 工具参数别名配置")
    print("=" * 60)

    class MockLLMClient:
        pass

    mock_client = MockLLMClient()

    tools_with_aliases = [
        DesignAPITool(mock_client),
        GenerateModelsTool(mock_client),
        GenerateServiceTool(mock_client),
        GenerateRouterTool(mock_client),
    ]

    print("\n✅ 参数别名配置:")
    for tool in tools_with_aliases:
        defn = tool.definition
        if defn.param_aliases:
            print(f"\n   [{defn.name}]")
            for param, alias in defn.param_aliases.items():
                print(f"      {param} <- state['{alias}']")

    return True


def test_tool_output_schema():
    """测试工具的输出 Schema"""
    print("\n" + "=" * 60)
    print("测试: 工具输出 Schema")
    print("=" * 60)

    class MockLLMClient:
        pass

    mock_client = MockLLMClient()

    tools = [
        AnalyzeRequirementsTool(mock_client),
        DesignAPITool(mock_client),
        GenerateModelsTool(mock_client),
    ]

    print("\n✅ 输出 Schema:")
    for tool in tools:
        defn = tool.definition
        print(f"\n   [{defn.name}]")
        if defn.output_schema:
            for key, schema in defn.output_schema.items():
                print(f"      {key}: {schema.get('type', 'any')} - {schema.get('description', '')}")

    return True


def test_code_writer_tool():
    """测试代码写入工具"""
    print("\n" + "=" * 60)
    print("测试: 代码写入工具 (CodeWriterTool)")
    print("=" * 60)

    import asyncio
    import tempfile
    from pathlib import Path

    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = CodeWriterTool(tmpdir)
        defn = writer.definition

        print(f"\n✅ 工具定义:")
        print(f"   name: {defn.name}")
        print(f"   category: {defn.category}")

        policy = defn.get_effective_post_policy()
        print(f"   is_high_impact: {policy.is_high_impact()}")
        print(f"   should_register_checkpoint: {policy.should_register_checkpoint()}")

        # 测试写入代码
        async def test_write():
            result = await writer.execute(
                filename="test_model.py",
                code="class User:\n    pass\n",
                code_type="model",
                description="测试模型",
            )
            return result

        result = asyncio.run(test_write())
        print(f"\n✅ 写入测试:")
        print(f"   success: {result.get('success')}")
        print(f"   file_path: {result.get('file_path')}")
        print(f"   line_count: {result.get('line_count')}")

        # 验证文件存在
        file_path = Path(result.get("file_path", ""))
        file_exists = file_path.exists()
        print(f"   file_exists: {file_exists}")

        return result.get("success") and file_exists


if __name__ == "__main__":
    results = []

    results.append(("工具 PostPolicy 配置", test_tool_post_policy()))
    results.append(("工具参数别名配置", test_tool_param_aliases()))
    results.append(("工具输出 Schema", test_tool_output_schema()))
    results.append(("代码写入工具", test_code_writer_tool()))

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
