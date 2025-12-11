"""
Redis 存储后端
"""


class RedisStorage:
    """Redis 存储（占位实现）"""

    def __init__(self, host: str = "localhost", port: int = 6379):
        self.host = host
        self.port = port
        # TODO: 实现 Redis 存储
