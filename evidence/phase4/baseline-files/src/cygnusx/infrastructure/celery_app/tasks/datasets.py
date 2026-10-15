"""Reconcile existing download Tasks only; never submit or replay downloads."""

from __future__ import annotations

import asyncio
import logging

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.services.dataset_import_service import (
    DatasetImportService,
    require_import_write,
)
from cygnusx.core.exceptions import AuthorizationError
from cygnusx.infrastructure.database.models.dataset import DatasetIngestionModel


@shared_task(
    name="cygnusx.infrastructure.celery_app.tasks.datasets.reconcile_dataset_jobs",
    soft_time_limit=540,
    time_limit=570,
)  # type: ignore[untyped-decorator]
def reconcile_dataset_jobs() -> dict[str, int | str]:
    try:
        require_import_write()
    except AuthorizationError:
        return {"status": "BLOCKED", "reconciled": 0}
    return asyncio.run(_reconcile())


async def _reconcile() -> dict[str, int | str]:
    from cygnusx.infrastructure.database.session import create_unpooled_engine

    require_import_write()
    engine = create_unpooled_engine()
    count = 0
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            # Ambiguous SUBMITTING and human-review states must never be auto-replayed.
            rows = (
                (
                    await db.execute(
                        select(DatasetIngestionModel)
                        .where(DatasetIngestionModel.state.in_(["QUEUED", "RUNNING", "VERIFYING"]))
                        .order_by(DatasetIngestionModel.created_at)
                        .limit(20)
                    )
                )
                .scalars()
                .all()
            )
            keys = [(row.user_id, row.project_id, row.id) for row in rows]
            await db.rollback()
            for owner, project, ingestion in keys:
                try:
                    await DatasetImportService(db).reconcile(owner, project, ingestion)
                    await db.commit()
                    count += 1
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Dataset reconciliation failed: job=%s type=%s",
                        ingestion,
                        type(exc).__name__,
                    )
                    # No exception text/credentials in public state. An operator can
                    # inspect server logs and explicitly reconcile the durable row.
                    await db.rollback()
                    row = await db.get(DatasetIngestionModel, ingestion)
                    if row:
                        row.state = "RECONCILIATION_REQUIRED"
                        row.errors = [*row.errors, {"code": "RECONCILE_FAILED"}]
                        await db.commit()
    finally:
        await engine.dispose()
    return {"status": "OK", "reconciled": count}
