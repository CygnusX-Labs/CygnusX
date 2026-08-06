"""AgentTeams Bridge 的低频状态巡检任务。"""

from __future__ import annotations

import asyncio
import logging
import uuid

from celery import shared_task

from omichub.core.config import get_settings
from omichub.infrastructure.cache.redis_client import get_redis

logger = logging.getLogger(__name__)

_WATCH_LOCK_KEY = "agentteams:case-watch:lock"
_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@shared_task(name="omichub.infrastructure.celery_app.tasks.agentteams.watch_cases")
def watch_cases() -> dict[str, int | str]:
    return asyncio.run(_watch_cases())


async def _watch_cases() -> dict[str, int | str]:
    from omichub.application.services.agentteams_case_watch_service import (
        AgentTeamsCaseWatchService,
    )
    from omichub.infrastructure.database.session import get_session_factory

    return await _watch_cases_with_factory(get_session_factory, AgentTeamsCaseWatchService)


async def _watch_cases_with_factory(
    session_factory,
    watch_service_cls,
    *,
    redis_getter=get_redis,
    lock_ttl_seconds: int | None = None,
) -> dict[str, int | str]:
    ttl = lock_ttl_seconds or max(30, get_settings().agentteams_case_watch_interval_seconds * 2)
    lock_token = uuid.uuid4().hex
    redis = redis_getter()
    try:
        acquired = await redis.set(_WATCH_LOCK_KEY, lock_token, nx=True, ex=ttl)
        if not acquired:
            logger.info("AgentTeams Case watch skipped because another worker holds the lock")
            return {"status": "skipped_locked"}
        async with session_factory()() as session:
            result = await watch_service_cls(session).scan()
            await session.commit()
            return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentTeams Case watch failed: %s", exc)
        return {"status": "failed"}
    finally:
        if "acquired" in locals() and acquired:
            try:
                await redis.eval(_RELEASE_LOCK_LUA, 1, _WATCH_LOCK_KEY, lock_token)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AgentTeams Case watch lock release failed: %s", exc)
