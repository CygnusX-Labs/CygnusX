"""AgentTeams Case SSE publication deduplication tests."""

from __future__ import annotations

import json

import pytest

import omichub.infrastructure.cache.chat_case_pubsub as pubsub


class FakeRedis:
    def __init__(self) -> None:
        self.eval_calls: list[tuple[object, ...]] = []
        self.publish_calls: list[tuple[object, ...]] = []

    async def eval(self, *args: object) -> int:
        self.eval_calls.append(args)
        return 1

    async def publish(self, *args: object) -> int:
        self.publish_calls.append(args)
        return 1


@pytest.mark.asyncio
async def test_case_event_with_idempotency_key_uses_atomic_redis_publish(monkeypatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(pubsub, "get_redis", lambda: redis)

    await pubsub.publish_chat_case_event(
        "session-1",
        {"type": "room_speech", "idempotency_key": "case-1:event-1:room_speech:0"},
    )

    assert len(redis.eval_calls) == 1
    assert redis.publish_calls == []
    _, key_count, dedup_key, channel, payload, ttl = redis.eval_calls[0]
    assert key_count == 2
    assert dedup_key == "chat:agentteams_case:dedup:session-1:case-1:event-1:room_speech:0"
    assert channel == "chat:agentteams_case:session-1"
    assert json.loads(payload) == {
        "type": "room_speech",
        "idempotency_key": "case-1:event-1:room_speech:0",
    }
    assert ttl == 604800
