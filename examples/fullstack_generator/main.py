#!/usr/bin/env python3
"""
全栈项目生成器 Demo - 入口文件

用于测试 auto-agent 的跨步骤智能重规划功能：
- 任务复杂度分级 (PROJECT 级别)
- 工作记忆 (设计决策、约束、接口定义)
- 全局一致性检查 (检查模型、服务、路由的一致性)
- 增量重规划 (发现不一致时只重新生成受影响的部分)
- 统一后处理策略 (ToolPostPolicy)

使用方法:
1. 设置环境变量:
   export OPENAI_API_KEY=your-api-key  # 或 DEEPSEEK_API_KEY
   export OPENAI_BASE_URL=https://api.deepseek.com/v1  # 可选
   export OPENAI_MODEL=deepseek-chat  # 可选

2. 运行:
   python examples/fullstack_generator/main.py

3. 或者使用自定义需求:
   python examples/fullstack_generator/main.py --requirements "你的需求描述"
"""

import argparse
import asyncio
import os
import sys

# 添加项目根目录到 path，使用本地版本而非安装的包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from examples.fullstack_generator.runner import FullstackGeneratorRunner


# 预定义的示例需求
SAMPLE_REQUIREMENTS = {
    "blog": """
一个博客系统 API，包含以下功能：

1. 用户管理
   - 用户注册、登录
   - 用户信息（用户名、邮箱、头像、简介）
   - 用户可以关注其他用户

2. 文章管理
   - 创建、编辑、删除文章
   - 文章包含标题、内容、封面图、标签
   - 文章有草稿和发布两种状态
   - 支持文章分类

3. 评论系统
   - 用户可以评论文章
   - 支持评论回复（嵌套评论）
   - 评论可以点赞

4. 业务规则
   - 只有作者可以编辑/删除自己的文章
   - 用户不能关注自己
   - 删除文章时同时删除相关评论
""",

    "ecommerce": """
一个电商系统 API，包含以下功能：

1. 商品管理
   - 商品信息（名称、描述、价格、库存、图片）
   - 商品分类（支持多级分类）
   - 商品规格（如颜色、尺寸）

2. 购物车
   - 添加/删除商品
   - 修改数量
   - 计算总价

3. 订单管理
   - 创建订单
   - 订单状态（待支付、已支付、已发货、已完成、已取消）
   - 订单详情（商品列表、收货地址、支付信息）

4. 用户管理
   - 用户注册、登录
   - 收货地址管理
   - 订单历史

5. 业务规则
   - 下单时检查库存
   - 支付成功后扣减库存
   - 取消订单恢复库存
""",

    "task": """
一个任务管理系统 API，包含以下功能：

1. 项目管理
   - 创建、编辑、删除项目
   - 项目成员管理
   - 项目状态（进行中、已完成、已归档）

2. 任务管理
   - 创建、编辑、删除任务
   - 任务属性（标题、描述、优先级、截止日期）
   - 任务状态（待办、进行中、已完成）
   - 任务分配给成员
   - 子任务支持

3. 标签系统
   - 创建、编辑、删除标签
   - 任务可以有多个标签

4. 评论和附件
   - 任务评论
   - 任务附件上传

5. 业务规则
   - 只有项目成员可以查看/编辑项目内的任务
   - 完成所有子任务后父任务自动完成
   - 删除项目时删除所有相关任务
""",
}


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="全栈项目生成器 - 测试跨步骤智能重规划功能"
    )
    parser.add_argument(
        "--sample",
        type=str,
        choices=["blog", "ecommerce", "task"],
        default="task",
        help="使用预定义的示例需求 (默认: task)",
    )
    parser.add_argument(
        "--requirements",
        type=str,
        help="自定义需求描述（覆盖 --sample）",
    )
    parser.add_argument(
        "--project-name",
        type=str,
        default=None,
        help="项目名称（默认根据 sample 自动生成）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="安静模式，减少输出",
    )

    args = parser.parse_args()

    # 确定需求和项目名称
    if args.requirements:
        requirements = args.requirements
        project_name = args.project_name or "custom_project"
    else:
        requirements = SAMPLE_REQUIREMENTS[args.sample]
        project_name = args.project_name or f"{args.sample}_api"

    print("=" * 70)
    print("🏗️  全栈项目生成器 Demo")
    print("=" * 70)
    print("\n📌 测试功能:")
    print("   - 任务复杂度分级 (PROJECT 级别)")
    print("   - 工作记忆 (设计决策、约束、接口定义)")
    print("   - 全局一致性检查")
    print("   - 增量重规划")
    print("   - 统一后处理策略 (ToolPostPolicy)")
    print("\n" + "-" * 70)

    # 检查 API Key
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("\n❌ 未设置 API Key，请设置环境变量:")
        print("   export OPENAI_API_KEY=your-api-key")
        print("   # 或")
        print("   export DEEPSEEK_API_KEY=your-api-key")
        return

    # 创建执行器并运行
    runner = FullstackGeneratorRunner()
    
    result = await runner.run(
        requirements=requirements,
        project_name=project_name,
        verbose=not args.quiet,
    )

    # 显示结果
    print("\n" + "=" * 70)
    print("📊 执行结果")
    print("=" * 70)
    
    if result["success"]:
        print(f"\n✅ 项目生成成功!")
        print(f"   📁 输出目录: {result['output_dir']}")
        print(f"   📄 生成文件: {', '.join(result['generated_files'])}")
        
        # 显示追踪统计
        trace = result.get("trace")
        if trace:
            summary = trace.get("summary", {})
            llm_calls = summary.get("llm_calls", {})
            print(f"\n📈 执行统计:")
            print(f"   - 追踪ID: {trace.get('trace_id', 'N/A')}")
            print(f"   - LLM调用: {llm_calls.get('count', 0)} 次")
            print(f"   - Token消耗: {llm_calls.get('total_tokens', 0):,}")
    else:
        print(f"\n❌ 项目生成失败: {result.get('error', '未知错误')}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
