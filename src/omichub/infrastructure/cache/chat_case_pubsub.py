"""聊天会话内 AgentTeams Case 状态事件的 Redis Pub/Sub 通道。"""

from __future__ import annotations

import json
from typing import Any

from omichub.infrastructure.cache.redis_client import get_redis

_CHANNEL_PREFIX = "chat:agentteams_case:"


def get_chat_case_channel(session_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{session_id}"


async def publish_chat_case_event(session_id: str, event: dict[str, Any]) -> None:
    await get_redis().publish(
        get_chat_case_channel(session_id),
        json.dumps(event, ensure_ascii=False, default=str),
    )


async def subscribe_chat_case_events(session_id: str):
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(get_chat_case_channel(session_id))
    return pubsub
