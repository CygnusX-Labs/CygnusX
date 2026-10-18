"""Download reliability on the existing Task row and existing queue."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_DISPATCH_SNAPSHOTS_KEY = "download_dispatch_snapshots"


def intent_digest(owner: str, project: str, parameters: dict[str, Any]) -> str:
    payload = {"owner": owner, "project": project, "parameters": parameters}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def dispatch_download(task_id: str) -> bool:
    """Return whether the transport call returned, not whether the broker acked."""
    try:
        from cygnusx.infrastructure.celery_app.tasks.download import run_download
        from cygnusx.infrastructure.task_queue.dispatcher import enqueue_task

        enqueue_task(run_download, task_id, task_id=task_id)
        logger.info("download.enqueue task_id=%s outcome=transport_call_returned", task_id)
        return True
    except Exception:
        logger.warning("download.enqueue task_id=%s outcome=deferred", task_id)
        return False


def notify_after_commit(session: Session, task_id: UUID) -> None:
    # Only an outer commit can publish; savepoint commits must not publish.
    session.info.setdefault("download_dispatch", set()).add(str(task_id))


@event.listens_for(Session, "after_transaction_create")
def _snapshot_nested_dispatch(session: Session, transaction: Any) -> None:
    if transaction.nested:
        snapshots = session.info.setdefault(_DISPATCH_SNAPSHOTS_KEY, {})
        snapshots[id(transaction)] = set(session.info.get("download_dispatch", set()))


@event.listens_for(Session, "after_commit")
def _committed(session: Session) -> None:
    if session.in_nested_transaction():
        nested = session.get_nested_transaction()
        if nested is not None:
            session.info.get(_DISPATCH_SNAPSHOTS_KEY, {}).pop(id(nested), None)
        return
    for task_id in session.info.pop("download_dispatch", set()):
        try:
            dispatch_download(task_id)
        except Exception:
            # The database is already committed. Never turn this into a false rollback.
            logger.warning("Download post-commit dispatch deferred for Task %s", task_id)


@event.listens_for(Session, "after_transaction_end")
def _transaction_ended(session: Session, transaction: Any) -> None:
    if transaction.parent is None:
        session.info.pop("download_dispatch", None)
        session.info.pop(_DISPATCH_SNAPSHOTS_KEY, None)


@event.listens_for(Session, "after_soft_rollback")
def _rolled_back(session: Session, previous: Any) -> None:
    snapshots = session.info.get(_DISPATCH_SNAPSHOTS_KEY, {})
    if previous.nested:
        snapshot = snapshots.pop(id(previous), None)
        if snapshot is not None:
            if snapshot:
                session.info["download_dispatch"] = snapshot
            else:
                session.info.pop("download_dispatch", None)
        return
    session.info.pop("download_dispatch", None)
    session.info.pop(_DISPATCH_SNAPSHOTS_KEY, None)


async def reconcile_download_tasks(db: AsyncSession) -> dict[str, int]:
    from cygnusx.infrastructure.database.models.task import TaskModel

    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    rows = (await db.execute(select(TaskModel).where(
        TaskModel.flow_id == "ebi_download",
        TaskModel.parameters["_download_reliability"]["version"].as_integer() == 1,
        TaskModel.status.in_(["queued", "running"]), TaskModel.updated_at < cutoff,
    ).order_by(TaskModel.updated_at, TaskModel.id).limit(100).with_for_update(skip_locked=True))).scalars().all()
    queued = []
    uncertain = 0
    for row in rows:
        state = (row.parameters or {}).get("_download_reliability", {})
        if state.get("version") != 1:
            continue  # Legacy rows are never automatically replayed.
        row.parameters = {**row.parameters, "_download_reliability": {
            **state, "last_recovery_attempt": datetime.now(UTC).isoformat(),
            "recovery_attempts": state.get("recovery_attempts", 0) + 1,
        }}
        if row.status == "queued":
            queued.append(str(row.id))
        else:
            uncertain += 1
            row.parameters = {**row.parameters, "_download_recovery": {
                "state": "RECONCILIATION_REQUIRED", "process_tree_stopped": False,
                "egress_revoked": False, "scientific_ready": False,
            }}
        row.updated_at = datetime.now(UTC)
        logger.info("download.recovery task_id=%s owner=%s project=%s digest=%s status=%s attempt=%s",
                    row.id, row.user_id, row.parameters.get("project_id"),
                    row.parameters.get("_download_intent"), row.status,
                    row.parameters["_download_reliability"]["recovery_attempts"])
    await db.commit()
    dispatched = sum(dispatch_download(task_id) for task_id in queued)
    return {"dispatched": dispatched, "reconciliation_required": uncertain}
