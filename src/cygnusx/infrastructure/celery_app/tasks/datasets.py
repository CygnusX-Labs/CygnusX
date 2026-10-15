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
        from cygnusx.application.services.research_provenance_service import require_research_write

        try:
            require_research_write()
        except AuthorizationError:
            return {"status": "BLOCKED", "reconciled": 0}
    return asyncio.run(_reconcile())


async def _reconcile() -> dict[str, int | str]:
    from cygnusx.infrastructure.database.session import create_unpooled_engine

    imports_enabled = True
    try:
        require_import_write()
    except AuthorizationError:
        imports_enabled = False
        from cygnusx.application.services.research_provenance_service import require_research_write

        require_research_write()
    engine = create_unpooled_engine()
    count = 0
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            # Ambiguous SUBMITTING and human-review states must never be auto-replayed.
            rows = (
                (
                    await db.execute(
                        select(DatasetIngestionModel)
                        .where(
                            DatasetIngestionModel.state.in_(["QUEUED", "RUNNING", "VERIFYING"]),
                            imports_enabled,
                        )
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
            from cygnusx.application.services.research_provenance_service import (
                ResearchProvenanceService,
                require_research_write,
            )
            from cygnusx.infrastructure.database.models.dataset import DatasetAnalysisLinkModel
            from cygnusx.infrastructure.database.models.task import TaskModel

            try:
                require_research_write()
            except AuthorizationError:
                return {"status": "OK_RESEARCH_BLOCKED", "reconciled": count}
            links = (
                (
                    await db.execute(
                        select(DatasetAnalysisLinkModel)
                        .join(TaskModel, TaskModel.id == DatasetAnalysisLinkModel.task_id)
                        .where(
                            TaskModel.status.in_(["success", "completed", "failed", "cancelled"])
                        )
                        .order_by(DatasetAnalysisLinkModel.updated_at)
                        .limit(20)
                    )
                )
                .scalars()
                .all()
            )
            task_ids = [(row.normalized_request.get("owner_id"), row.task_id) for row in links]
            await db.rollback()
            from uuid import UUID

            from cygnusx.application.services.reproducible_report_service import (
                ReproducibleReportService,
            )

            for owner_string, task_id in task_ids:
                if task_id is None or owner_string is None:
                    continue
                try:
                    graph = await ResearchProvenanceService(db).reconcile(
                        UUID(owner_string), task_id
                    )
                    await db.commit()
                    if graph.result_observation_id is not None:
                        await ReproducibleReportService(db).enqueue(
                            UUID(owner_string), task_id, request_key=graph.result_observation_id
                        )
                        if graph.flow.get("id") == "counts_deg" and graph.compute_state in {
                            "success",
                            "completed",
                        }:
                            await ReproducibleReportService(db).enqueue(
                                UUID(owner_string),
                                task_id,
                                request_key=graph.result_observation_id,
                                scientific=True,
                            )
                    count += 1
                except Exception as exc:
                    await db.rollback()
                    logging.getLogger(__name__).warning(
                        "Research reconciliation deferred: task=%s type=%s",
                        task_id,
                        type(exc).__name__,
                    )
    finally:
        await engine.dispose()
    return {"status": "OK", "reconciled": count}
