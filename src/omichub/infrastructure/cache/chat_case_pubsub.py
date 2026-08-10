"""聊天会话内 AgentTeams Case 状态事件的 Redis Pub/Sub 通道。"""

from __future__ import annotations

import json
from typing import Any

from omichub.infrastructure.cache.redis_client import get_redis

_CHANNEL_PREFIX = "chat:agentteams_case:"
_DEDUP_PREFIX = "chat:agentteams_case:dedup:"
_PUBLISH_DEDUP_LUA = """
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[2]) then
  return redis.call('PUBLISH', KEYS[2], ARGV[1])
end
return 0
"""


def get_chat_case_channel(session_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{session_id}"


async def publish_chat_case_event(session_id: str, event: dict[str, Any]) -> None:
    redis = get_redis()
    channel = get_chat_case_channel(session_id)
    payload = json.dumps(event, ensure_ascii=False, default=str)
    idempotency_key = event.get("idempotency_key")
    if isinstance(idempotency_key, str) and idempotency_key:
        await redis.eval(
            _PUBLISH_DEDUP_LUA,
            2,
            f"{_DEDUP_PREFIX}{session_id}:{idempotency_key}",
            channel,
            payload,
            7 * 24 * 60 * 60,
        )
        return
    await redis.publish(channel, payload)


async def subscribe_chat_case_events(session_id: str):
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(get_chat_case_channel(session_id))
    return pubsub
