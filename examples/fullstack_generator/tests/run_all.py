#!/usr/bin/env python3
"""
运行所有测试
"""

import os
import sys
import subprocess

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def run_test(test_file: str) -> bool:
    """运行单个测试文件"""
    print(f"\n{'=' * 70}")
    print(f"🧪 运行: {test_file}")
    print("=" * 70)

    result = subprocess.run(
        [sys.executable, test_file],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    return result.returncode == 0


def main():
    """运行所有测试"""
    print("=" * 70)
    print("🧪 全栈项目生成器 - 测试套件")
    print("=" * 70)
    print("\n测试跨步骤智能重规划功能:")
    print("  - 工具 ToolPostPolicy 配置")
    print("  - 工作记忆 (CrossStepWorkingMemory)")
    print("  - 一致性检查 (GlobalConsistencyChecker)")

    tests_dir = os.path.dirname(os.path.abspath(__file__))
    test_files = [
        os.path.join(tests_dir, "test_tools.py"),
        os.path.join(tests_dir, "test_working_memory.py"),
        os.path.join(tests_dir, "test_consistency.py"),
    ]

    results = []
    for test_file in test_files:
        if os.path.exists(test_file):
            success = run_test(test_file)
            results.append((os.path.basename(test_file), success))
        else:
            print(f"\n⚠️  测试文件不存在: {test_file}")
            results.append((os.path.basename(test_file), False))

    # 汇总
    print("\n" + "=" * 70)
    print("📊 测试套件汇总")
    print("=" * 70)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {status} - {name}")

    print(f"\n   总计: {passed}/{total} 通过")
    print("=" * 70)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
