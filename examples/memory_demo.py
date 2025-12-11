"""
记忆系统示例
"""

from auto_agent.memory import LongTermMemory, ShortTermMemory


def long_term_memory_demo():
    """长期记忆示例"""
    ltm = LongTermMemory(storage_path="./data/demo_memories")

    # 加载用户记忆
    user_id = "demo_user"
    memory_content = ltm.load(user_id)
    print("用户记忆内容:")
    print(memory_content)

    # 添加事实
    ltm.add_fact(
        user_id=user_id,
        fact="用户是一名 Python 开发者，擅长 FastAPI",
        category="技能",
    )

    # 更新记忆
    ltm.update(
        user_id=user_id,
        updates={
            "偏好语言": "中文",
            "响应风格": "详细",
        },
    )

    # 获取相关上下文
    context = ltm.get_relevant_context(user_id, "帮我写一个 FastAPI 接口")
    print("\n相关上下文:")
    print(context)


def short_term_memory_demo():
    """短期记忆示例"""
    from auto_agent.models import Message
    import time

    stm = ShortTermMemory(backend="memory")

    # 创建对话
    conv_id = stm.create_conversation(user_id="demo_user")
    print(f"创建对话: {conv_id}")

    # 添加消息
    stm.add_message(
        conv_id,
        Message(role="user", content="你好", timestamp=int(time.time()), metadata={}),
    )
    stm.add_message(
        conv_id,
        Message(role="assistant", content="你好！有什么可以帮助你的？", timestamp=int(time.time()), metadata={}),
    )

    # 获取对话历史
    history = stm.get_conversation_history(conv_id)
    print("\n对话历史:")
    for msg in history:
        print(f"{msg.role}: {msg.content}")

    # 总结对话
    summary = stm.summarize_conversation(conv_id)
    print("\n对话总结:")
    print(summary)


if __name__ == "__main__":
    print("=" * 50)
    print("长期记忆示例")
    print("=" * 50)
    long_term_memory_demo()

    print("\n" + "=" * 50)
    print("短期记忆示例")
    print("=" * 50)
    short_term_memory_demo()
