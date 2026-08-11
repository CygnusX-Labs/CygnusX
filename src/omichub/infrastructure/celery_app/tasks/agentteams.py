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
_EVENT_CONSUMER_LOCK_KEY = "agentteams:case-event-consumer:lock"
_APPROVAL_TIMEOUT_LOCK_KEY = "agentteams:approval-timeout:lock"
_STALE_TASK_LOCK_KEY = "agentteams:stale-task-watch:lock"
_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@shared_task(name="omichub.infrastructure.celery_app.tasks.agentteams.watch_cases")
def watch_cases() -> dict[str, int | str]:
    return asyncio.run(_watch_cases())


@shared_task(name="omichub.infrastructure.celery_app.tasks.agentteams.consume_case_events")
def consume_case_events() -> dict[str, int | str]:
    return asyncio.run(_consume_case_events())


@shared_task(name="omichub.infrastructure.celery_app.tasks.agentteams.requeue_stale_tasks")
def requeue_stale_tasks() -> dict[str, int | str]:
    return asyncio.run(_requeue_stale_tasks())


@shared_task(name="omichub.infrastructure.celery_app.tasks.agentteams.reconcile_approval_timeouts")
def reconcile_approval_timeouts() -> dict[str, int | str]:
    return asyncio.run(_reconcile_approval_timeouts())


@shared_task(name="omichub.infrastructure.celery_app.tasks.agentteams.cleanup_evidence")
def cleanup_evidence() -> dict[str, object]:
    return asyncio.run(_cleanup_evidence())


async def _cleanup_evidence() -> dict[str, object]:
    from omichub.application.services.agentteams_evidence_gc_service import (
        AgentTeamsEvidenceGcService,
    )

    try:
        return await AgentTeamsEvidenceGcService().cleanup()
    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentTeams evidence cleanup failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


async def _watch_cases() -> dict[str, int | str]:
    from omichub.application.services.agentteams_case_watch_service import (
        AgentTeamsCaseWatchService,
    )
    from omichub.infrastructure.database.session import get_session_factory

    return await _watch_cases_with_factory(get_session_factory, AgentTeamsCaseWatchService)


async def _consume_case_events() -> dict[str, int | str]:
    from omichub.application.services.agentteams_case_event_consumer_service import (
        AgentTeamsCaseEventConsumerService,
    )
    from omichub.infrastructure.database.session import get_session_factory

    return await _consume_case_events_with_factory(
        get_session_factory, AgentTeamsCaseEventConsumerService
    )


async def _requeue_stale_tasks() -> dict[str, int | str]:
    from omichub.application.services.agentteams_stale_task_service import (
        AgentTeamsStaleTaskService,
    )
    from omichub.infrastructure.database.session import get_session_factory

    return await _requeue_stale_tasks_with_factory(
        get_session_factory, AgentTeamsStaleTaskService
    )


async def _reconcile_approval_timeouts() -> dict[str, int | str]:
    from omichub.infrastructure.database.session import get_session_factory

    return await _reconcile_approval_timeouts_with_factory(get_session_factory)


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


async def _consume_case_events_with_factory(
    session_factory,
    consumer_service_cls,
    *,
    redis_getter=get_redis,
    stream_seconds: int | None = None,
) -> dict[str, int | str]:
    from omichub.application.services.agentteams_case_watch_service import (
        TERMINAL_STATUSES,
        _watchable_sessions_query,
    )

    settings = get_settings()
    duration = stream_seconds or settings.agentteams_case_event_stream_seconds
    lock_token = uuid.uuid4().hex
    redis = redis_getter()
    acquired = False
    try:
        acquired = bool(
            await redis.set(
                _EVENT_CONSUMER_LOCK_KEY,
                lock_token,
                nx=True,
                ex=max(30, duration + 15),
            )
        )
        if not acquired:
            return {"status": "skipped_locked"}
        async with session_factory()() as discovery_session:
            sessions = list((await discovery_session.scalars(_watchable_sessions_query())).all())
            bindings = [
                (session.session_id, case_id)
                for session in sessions
                for case_id in (session.sandbox_meta or {}).get("agentteams_case_ids", [])
                if isinstance(case_id, str)
                and (session.sandbox_meta or {})
                .get("agentteams_case_status", {})
                .get(case_id)
                not in TERMINAL_STATUSES
            ]

        async def consume_binding(session_id: str, case_id: str) -> dict[str, int]:
            async with session_factory()() as db:
                result = await consumer_service_cls(db).consume(
                    session_id, case_id, watch_seconds=duration
                )
                await db.commit()
                return result

        results = await asyncio.gather(
            *(consume_binding(session_id, case_id) for session_id, case_id in bindings),
            return_exceptions=True,
        )
        summary = {"bindings": len(bindings), "events": 0, "projected": 0, "failed": 0}
        for result in results:
            if isinstance(result, BaseException):
                summary["failed"] += 1
                logger.warning("AgentTeams Case SSE consumer failed: %s", result)
                continue
            summary["events"] += result["events"]
            summary["projected"] += result["projected"]
        return summary
    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentTeams Case SSE consumer orchestration failed: %s", exc)
        return {"status": "failed"}
    finally:
        if acquired:
            try:
                await redis.eval(_RELEASE_LOCK_LUA, 1, _EVENT_CONSUMER_LOCK_KEY, lock_token)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AgentTeams Case SSE consumer lock release failed: %s", exc)


async def _requeue_stale_tasks_with_factory(
    session_factory,
    service_cls,
    *,
    redis_getter=get_redis,
    lock_ttl_seconds: int = 290,
) -> dict[str, int | str]:
    lock_token = uuid.uuid4().hex
    redis = redis_getter()
    try:
        acquired = await redis.set(
            _STALE_TASK_LOCK_KEY, lock_token, nx=True, ex=lock_ttl_seconds
        )
        if not acquired:
            logger.info("AgentTeams stale task watch skipped because another worker holds the lock")
            return {"status": "skipped_locked"}
        async with session_factory()() as session:
            return await service_cls(session).scan(
                stale_after_seconds=get_settings().agentteams_stale_task_seconds
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentTeams stale task watch failed: %s", exc)
        return {"status": "failed"}
    finally:
        if "acquired" in locals() and acquired:
            try:
                await redis.eval(_RELEASE_LOCK_LUA, 1, _STALE_TASK_LOCK_KEY, lock_token)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AgentTeams stale task watch lock release failed: %s", exc)


async def _reconcile_approval_timeouts_with_factory(
    session_factory,
    *,
    redis_getter=get_redis,
) -> dict[str, int | str]:
    from omichub.application.services.agentteams_bridge_settings_service import (
        AgentTeamsBridgeSettingsService,
    )
    from omichub.application.services.agentteams_service import AgentTeamsService

    lock_token = uuid.uuid4().hex
    redis = redis_getter()
    acquired = False
    try:
        acquired = bool(
            await redis.set(
                _APPROVAL_TIMEOUT_LOCK_KEY, lock_token, nx=True, ex=3500
            )
        )
        if not acquired:
            return {"status": "skipped_locked"}
        settings = get_settings()
        async with session_factory()() as db:
            runtime = await AgentTeamsBridgeSettingsService(db, settings).get_runtime_config()
            service = AgentTeamsService(settings, runtime)
            if not service.available:
                return {"status": "skipped_unavailable"}
            return await service.reconcile_approval_timeouts()
    except Exception as exc:  # noqa: BLE001
        logger.exception("AgentTeams approval timeout reconciliation failed: %s", exc)
        return {"status": "failed"}
    finally:
        if acquired:
            try:
                await redis.eval(_RELEASE_LOCK_LUA, 1, _APPROVAL_TIMEOUT_LOCK_KEY, lock_token)
            except Exception as exc:  # noqa: BLE001
                logger.warning("AgentTeams approval timeout lock release failed: %s", exc)
