"""AgentTeams Bridge 的低频状态巡检任务。"""

from __future__ import annotations

import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="omichub.infrastructure.celery_app.tasks.agentteams.watch_cases")
def watch_cases() -> dict[str, int | str]:
    return asyncio.run(_watch_cases())


async def _watch_cases() -> dict[str, int | str]:
    from omichub.application.services.agentteams_case_watch_service import (
        AgentTeamsCaseWatchService,
    )
    from omichub.infrastructure.database.session import get_session_factory

    return await _watch_cases_with_factory(get_session_factory, AgentTeamsCaseWatchService)


async def _watch_cases_with_factory(session_factory, watch_service_cls) -> dict[str, int | str]:
    try:
        async with session_factory()() as session:
            result = await watch_service_cls(session).scan()
            await session.commit()
            return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("AgentTeams Case watch failed: %s", exc)
        return {"status": "failed"}
