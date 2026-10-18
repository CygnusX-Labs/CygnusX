"""Project report outbox; dedicated PG advisory lock survives stage commits."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from celery import shared_task
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.services.project_report_publication import run_project_report
from cygnusx.application.services.project_report_service import (
    dispatch_project_report,
    project_report_write_enabled,
)
from cygnusx.core.config import get_settings
from cygnusx.infrastructure.database.models.project_report import ProjectReportJobModel

PREFIX = "cygnusx.infrastructure.celery_app.tasks.project_reports"


async def record_failure(db: AsyncSession, job_id: UUID, exc: Exception) -> None:
    from cygnusx.infrastructure.celery_app.tasks.reports import failure_details

    await db.rollback()
    job = await db.get(ProjectReportJobModel, job_id)
    if job is None or job.status == "ready":
        return
    code, _, retryable = failure_details(exc)
    job.status, job.error_code = "failed", code
    job.retryable = retryable and job.attempt_count < get_settings().report_generation_max_attempts
    await db.commit()


@shared_task(
    name=f"{PREFIX}.generate_project_report",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=1900,
    time_limit=1950,
)  # type: ignore[untyped-decorator]
def generate_project_report(job_id: str) -> dict[str, str]:
    return asyncio.run(_run(UUID(job_id)))


async def _run(job_id: UUID) -> dict[str, str]:
    project_report_write_enabled()  # Before constructing an engine when disabled.
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
                    async with asyncio.timeout(get_settings().report_generation_timeout_seconds):
                        await run_project_report(db, job_id)
                except Exception as exc:
                    await record_failure(db, job_id, exc)
                job = await db.get(ProjectReportJobModel, job_id)
                return {"job_id": str(job_id), "status": job.status if job else "missing"}
            finally:
                await db.rollback()
                await db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                await db.commit()
    finally:
        await engine.dispose()


@shared_task(name=f"{PREFIX}.reconcile_project_reports")  # type: ignore[untyped-decorator]
def reconcile_project_reports() -> dict[str, int]:
    if (
        not get_settings().project_report_write_enabled
        or not get_settings().research_delivery_read_enabled
    ):
        return {"dispatched": 0}
    return asyncio.run(_reconcile())


async def _reconcile() -> dict[str, int]:
    from cygnusx.infrastructure.database.session import create_unpooled_engine

    settings = get_settings()
    engine = create_unpooled_engine()
    stale = datetime.now(UTC) - timedelta(seconds=settings.report_generation_timeout_seconds + 60)
    queued = datetime.now(UTC) - timedelta(seconds=60)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            ids = list(
                (
                    await db.scalars(
                        select(ProjectReportJobModel.id)
                        .where(
                            or_(
                                (ProjectReportJobModel.status == "queued")
                                & (ProjectReportJobModel.updated_at < queued),
                                (
                                    ProjectReportJobModel.status.in_(
                                        ("validating", "rendering", "publishing")
                                    )
                                )
                                & (ProjectReportJobModel.updated_at < stale),
                                (ProjectReportJobModel.status == "failed")
                                & ProjectReportJobModel.retryable
                                & (ProjectReportJobModel.updated_at < queued),
                            )
                        )
                        .order_by(ProjectReportJobModel.updated_at)
                        .limit(100)
                    )
                ).all()
            )
        for job_id in ids:
            await dispatch_project_report(job_id)
        return {"dispatched": len(ids)}
    finally:
        await engine.dispose()
