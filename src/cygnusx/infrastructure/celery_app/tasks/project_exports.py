"""Durable export outbox; dedicated PG advisory lock survives stage commits."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import shared_task
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.services.project_delivery_service import (
    ACTIVE,
    dispatch_export,
    export_enabled,
    run_project_export,
)
from cygnusx.core.config import get_settings
from cygnusx.infrastructure.database.models.project_export import ProjectExportJobModel

PREFIX = "cygnusx.infrastructure.celery_app.tasks.project_exports"


async def record_failure(db: AsyncSession, job_id: UUID, exc: Exception) -> None:
    from cygnusx.infrastructure.celery_app.tasks.reports import failure_details

    await db.rollback()
    job = await db.get(ProjectExportJobModel, job_id)
    if job is None or job.status == "ready":
        return
    code, _, retryable = failure_details(exc)
    job.status, job.error_code = "failed", code
    job.retryable = retryable and job.attempt_count < get_settings().project_export_max_attempts
    await db.commit()


@shared_task(
    name=f"{PREFIX}.generate_project_export",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=570,
    time_limit=600,
)  # type: ignore[untyped-decorator]
def generate_project_export(job_id: str) -> dict[str, str]:
    return asyncio.run(_run(UUID(job_id)))


async def _run(job_id: UUID) -> dict[str, str]:
    export_enabled()  # Before constructing an engine when disabled.
    from cygnusx.infrastructure.celery_app.tasks.reports import task_lock_key
    from cygnusx.infrastructure.database.session import create_unpooled_engine

    engine = create_unpooled_engine()
    try:
        async with (
            engine.connect() as connection,
            AsyncSession(bind=connection, expire_on_commit=False) as db,
        ):
            key = task_lock_key(job_id)
            locked = await db.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
            await db.commit()
            if not locked:
                return {"job_id": str(job_id), "status": "busy"}
            try:
                try:
                    async with asyncio.timeout(get_settings().project_export_timeout_seconds):
                        await run_project_export(db, job_id)
                except Exception as exc:
                    await record_failure(db, job_id, exc)
                job = await db.get(ProjectExportJobModel, job_id)
                return {"job_id": str(job_id), "status": job.status if job else "missing"}
            finally:
                await db.rollback()
                await db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                await db.commit()
    finally:
        await engine.dispose()


@shared_task(name=f"{PREFIX}.reconcile_project_exports")  # type: ignore[untyped-decorator]
def reconcile_project_exports() -> dict[str, int]:
    if (
        not get_settings().project_export_enabled
        or not get_settings().research_delivery_read_enabled
    ):
        return {"dispatched": 0}
    return asyncio.run(_reconcile())


async def _reconcile() -> dict[str, int]:
    from cygnusx.infrastructure.database.session import create_unpooled_engine

    settings = get_settings()
    engine = create_unpooled_engine()
    stale = datetime.now(UTC) - timedelta(seconds=settings.project_export_timeout_seconds + 60)
    queued = datetime.now(UTC) - timedelta(seconds=60)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            ids = list(
                (
                    await db.scalars(
                        select(ProjectExportJobModel.id)
                        .where(
                            or_(
                                (ProjectExportJobModel.status == "queued")
                                & (ProjectExportJobModel.updated_at < queued),
                                (ProjectExportJobModel.status.in_(ACTIVE))
                                & (ProjectExportJobModel.updated_at < stale),
                                (ProjectExportJobModel.status == "failed")
                                & ProjectExportJobModel.retryable
                                & (ProjectExportJobModel.updated_at < queued),
                            )
                        )
                        .order_by(ProjectExportJobModel.updated_at)
                        .limit(100)
                    )
                ).all()
            )
        for job_id in ids:
            await dispatch_export(job_id)
        return {"dispatched": len(ids)}
    finally:
        await engine.dispose()
