"""Redis 异步客户端"""

import redis.asyncio as redis

from omichub.core.config import get_settings

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """获取 Redis 客户端（单例）"""
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    """关闭 Redis 连接"""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
