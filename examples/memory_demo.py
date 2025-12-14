"""
记忆系统演示 - 触发机制和完整流程

展示：
1. 记忆触发的时机和条件
2. 查询分析和记忆路由
3. 反馈学习机制
4. 记忆注入到 Prompt 的过程
"""

import asyncio
import time
from auto_agent import MemorySystem, OpenAIClient
from auto_agent.memory.models import MemoryCategory, MemorySource


class MemoryTriggerDemo:
    """记忆触发机制演示"""

    def __init__(self):
        # 初始化记忆系统
        self.memory = MemorySystem(
            storage_path="./demo_memory",
            token_budget=2000,
        )
        self.user_id = "demo_user"

        # 初始化一些示例记忆
        self._setup_demo_memories()

    def _setup_demo_memories(self):
        """设置演示用的记忆数据"""
        print("🔧 初始化演示记忆...")

        # 用户偏好
        self.memory.set_preference(self.user_id, "编程语言", "Python")
        self.memory.set_preference(self.user_id, "代码风格", "简洁清晰")
        self.memory.set_preference(self.user_id, "框架偏好", "FastAPI")

        # 知识记忆
        self.memory.add_knowledge(
            self.user_id,
            "用户熟悉异步编程，经常使用 async/await",
            tags=["技能", "异步"],
        )
        self.memory.add_knowledge(
            self.user_id,
            "用户之前做过文档管理系统项目",
            tags=["项目经验", "文档"],
        )

        # 策略记忆
        self.memory.add_strategy(
            self.user_id,
            "写代码前先写测试用例，TDD 开发",
            is_successful=True,
            tags=["开发方法", "测试"],
        )
        self.memory.add_strategy(
            self.user_id,
            "使用 Pydantic 做数据验证比手动验证更可靠",
            is_successful=True,
            tags=["最佳实践", "验证"],
        )

        # 工作记忆
        self.memory.add_memory(
            self.user_id,
            "最近在学习 LangChain 和 Agent 开发",
            category=MemoryCategory.WORK,
            tags=["学习", "AI", "Agent"],
        )

        print(f"✅ 初始化完成，共 {len(self.memory.semantic._memories.get(self.user_id, {}))} 条记忆")

    def demonstrate_trigger_conditions(self):
        """演示记忆触发条件"""
        print("\n" + "=" * 60)
        print("📋 记忆触发条件演示")
        print("=" * 60)

        test_queries = [
            ("你好", "简单问候"),
            ("今天天气怎么样", "无关查询"),
            ("帮我写一个 Python 函数", "编程相关"),
            ("总结一下我之前的学习经验", "反思类查询"),
            ("我应该选择哪个框架", "决策类查询"),
            ("帮我设计一个 API", "工作相关"),
        ]

        for query, desc in test_queries:
            should_use, reason = self.memory.router.should_use_memory(query)
            analysis = self.memory.router.analyze_query(query)

            print(f"\n查询: '{query}' ({desc})")
            print(f"  是否使用记忆: {'✅' if should_use else '❌'} - {reason}")
            print(f"  意图类型: {analysis['intent']}")
            print(f"  相关领域: {[c.value for c in analysis['categories']]}")

    def demonstrate_memory_routing(self):
        """演示记忆路由过程"""
        print("\n" + "=" * 60)
        print("🧠 记忆路由演示")
        print("=" * 60)

        query = "帮我写一个 Python API，要用异步的方式"

        print(f"查询: '{query}'")
        print("\n🔍 步骤 1: 查询分析")
        analysis = self.memory.router.analyze_query(query)
        print(f"  - 意图: {analysis['intent']}")
        print(f"  - 领域: {[c.value for c in analysis['categories']]}")
        print(f"  - 关键词: {analysis['keywords']}")

        print("\n🎯 步骤 2: 记忆检索")
        result = self.memory.router.route(
            user_id=self.user_id,
            query=query,
            token_budget=1500,
        )

        print(f"  - 命中记忆数: {len(result['memories'])}")
        print(f"  - Token 估计: {result['token_estimate']}")

        print("\n📝 步骤 3: 生成的上下文")
        print("─" * 40)
        print(result["context"])
        print("─" * 40)

        return result

    def demonstrate_feedback_learning(self):
        """演示反馈学习机制"""
        print("\n" + "=" * 60)
        print("👍👎 反馈学习演示")
        print("=" * 60)

        # 添加一个新记忆
        item = self.memory.add_memory(
            self.user_id,
            "建议使用 SQLAlchemy ORM 进行数据库操作",
            category=MemoryCategory.STRATEGY,
            tags=["数据库", "ORM"],
            confidence=0.6,
        )

        print(f"新记忆: {item.content}")
        print(f"初始状态 - 置信度: {item.confidence:.2f}, 奖励: {item.reward:.2f}")

        # 正反馈
        print("\n👍 用户给出正反馈...")
        self.memory.thumbs_up(self.user_id, item.memory_id)
        updated = self.memory.get_memory(self.user_id, item.memory_id)
        print(f"正反馈后 - 置信度: {updated.confidence:.2f}, 奖励: {updated.reward:.2f}")

        # 负反馈
        print("\n👎 用户给出负反馈...")
        self.memory.thumbs_down(self.user_id, item.memory_id, reason="项目不需要 ORM")
        updated = self.memory.get_memory(self.user_id, item.memory_id)
        print(f"负反馈后 - 置信度: {updated.confidence:.2f}, 奖励: {updated.reward:.2f}")
        print(f"需要修订: {updated.needs_revision}")

        # 展示得分变化
        score = updated.calculate_score()
        print(f"综合得分: {score:.3f}")

    def demonstrate_working_memory_promotion(self):
        """演示短时记忆提炼"""
        print("\n" + "=" * 60)
        print("🔄 短时记忆提炼演示")
        print("=" * 60)

        # 模拟一个任务执行过程
        task_id = self.memory.start_task(self.user_id, "开发一个用户管理 API")
        wm = self.memory.get_working_memory(task_id)

        print(f"任务开始: {wm.query}")

        # 模拟执行步骤
        print("\n📝 执行步骤:")
        wm.add_decision("使用 FastAPI 框架", "用户偏好，性能好", step_id="s1")
        print("  1. 决策: 使用 FastAPI 框架")

        wm.add_tool_call(
            "design_api",
            {"endpoints": ["POST /users", "GET /users"]},
            {"success": True, "schema": "generated"},
            step_id="s2",
        )
        print("  2. 工具调用: 设计 API 成功")

        wm.add_tool_call(
            "generate_code",
            {"framework": "fastapi"},
            {"success": True, "files": ["main.py", "models.py"]},
            step_id="s3",
        )
        print("  3. 工具调用: 生成代码成功")

        wm.add_result({"api_created": True, "test_passed": True}, step_id="s4")
        print("  4. 任务完成")

        # 提取候选记忆
        candidates = wm.extract_for_long_term()
        print(f"\n🎯 提取到 {len(candidates)} 个候选记忆:")
        for i, candidate in enumerate(candidates, 1):
            print(f"  {i}. [{candidate.get('category')}] {candidate.get('content')}")

        # 提炼到长期记忆
        print("\n⬆️ 提炼到长期记忆...")
        self.memory.end_task(self.user_id, task_id, promote_to_long_term=True)
        print("✅ 提炼完成")

    def demonstrate_context_injection(self):
        """演示上下文注入机制"""
        print("\n" + "=" * 60)
        print("💉 上下文注入演示")
        print("=" * 60)

        queries = [
            "帮我写一个简单的 Hello World",
            "设计一个用户认证系统",
            "总结一下我的开发经验",
        ]

        for query in queries:
            print(f"\n查询: '{query}'")
            result = self.memory.get_context_for_query(self.user_id, query)

            if result["context"]:
                print("📋 注入的记忆上下文:")
                print("─" * 30)
                # 只显示前 200 字符
                context_preview = result["context"][:200]
                if len(result["context"]) > 200:
                    context_preview += "..."
                print(context_preview)
                print("─" * 30)
                print(f"Token 估计: {result['token_estimate']}")
                print(f"命中记忆: {len(result['memories'])} 条")
            else:
                print("❌ 无相关记忆，跳过注入")
                print(f"原因: {result.get('analysis', {}).get('skip_reason', '未知')}")

    def demonstrate_memory_stats(self):
        """展示记忆统计"""
        print("\n" + "=" * 60)
        print("📊 记忆统计")
        print("=" * 60)

        stats = self.memory.get_stats(self.user_id)
        print(f"语义记忆总数: {stats['semantic']['total_memories']}")
        print(f"叙事记忆数: {stats['narrative_count']}")
        print(f"活跃任务数: {stats['active_tasks']}")
        print(f"平均奖励分: {stats['semantic']['average_reward']:.3f}")

        print("\n按分类统计:")
        for category, count in stats["semantic"]["by_category"].items():
            print(f"  - {category}: {count} 条")

    def run_full_demo(self):
        """运行完整演示"""
        print("🚀 记忆系统触发机制演示")
        print("=" * 60)

        try:
            self.demonstrate_trigger_conditions()
            self.demonstrate_memory_routing()
            self.demonstrate_feedback_learning()
            self.demonstrate_working_memory_promotion()
            self.demonstrate_context_injection()
            self.demonstrate_memory_stats()

            print("\n" + "=" * 60)
            print("✅ 演示完成！")
            print("=" * 60)

        except Exception as e:
            print(f"❌ 演示过程中出错: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数"""
    demo = MemoryTriggerDemo()
    demo.run_full_demo()


if __name__ == "__main__":
    asyncio.run(main())