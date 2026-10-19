"""Redis 异步客户端"""

import asyncio
import socket
import time

import redis.asyncio as redis

from cygnusx.core.config import get_settings

_redis: redis.Redis | None = None
_redis_loop: asyncio.AbstractEventLoop | None = None
_redis_dns_disabled_until = 0.0
_redis_dns_key: tuple[str, int] | None = None


def get_redis() -> redis.Redis:
    """获取 Redis 客户端（按当前 event loop 缓存）。

    Celery 任务用 asyncio.run() 每次新建事件循环；async redis 客户端绑定到首次使用的 loop，
    跨 loop 复用会抛 "Event loop is closed" / "attached to a different loop"。
    故按 get_running_loop() 缓存：同一 loop 内复用，loop 变化时重建。
    web(FastAPI 单 loop) 与 celery(每任务新 loop) 均安全。进程内同一时刻仅一个 loop 在跑，单缓存即可。

    在可选缓存路径上先做主机解析；解析失败时短暂熔断，避免 asyncio Redis
    连接任务在 DNS 失败后无法取消而阻塞请求或短命测试进程。
    """
    global _redis, _redis_loop, _redis_dns_disabled_until, _redis_dns_key
    loop = asyncio.get_running_loop()
    if _redis is None or _redis_loop is not loop:
        settings = get_settings()
        dns_key = (settings.redis_host, settings.redis_port)
        now = time.monotonic()
        if _redis_dns_key == dns_key and now < _redis_dns_disabled_until:
            raise ConnectionError("Redis host resolution is temporarily disabled")
        if _redis_dns_key != dns_key or now >= _redis_dns_disabled_until:
            try:
                socket.getaddrinfo(
                    settings.redis_host,
                    settings.redis_port,
                    type=socket.SOCK_STREAM,
                )
            except OSError as exc:
                _redis_dns_key = dns_key
                _redis_dns_disabled_until = now + 30.0
                raise ConnectionError("Redis host is unavailable") from exc
            _redis_dns_key = dns_key
            _redis_dns_disabled_until = 0.0
        _redis = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )  # type: ignore[no-untyped-call]
        _redis_loop = loop
    return _redis


async def close_redis() -> None:
    """关闭 Redis 连接"""
    global _redis, _redis_loop, _redis_dns_disabled_until, _redis_dns_key
    if _redis is not None:
        await _redis.close()
        _redis = None
        _redis_loop = None
        _redis_dns_disabled_until = 0.0
        _redis_dns_key = None
