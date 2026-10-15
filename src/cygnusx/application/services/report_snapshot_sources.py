"""Read-only Task/Run source adapter. No inferred joins, flushes or service writes."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.research_delivery import ResearchProvenance
from cygnusx.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cygnusx.infrastructure.database.models.file import FileRecordModel
from cygnusx.infrastructure.database.models.run import RunModel
from cygnusx.infrastructure.database.models.run_event import RunEventModel
from cygnusx.infrastructure.database.models.task import TaskModel

EVENT_CAPTURE_LIMIT = 1000
FILE_CAPTURE_LIMIT = 2000


@dataclass(frozen=True)
class TaskEvidenceRecords:
    task: TaskModel
    run: RunModel | None
    files: tuple[FileRecordModel, ...]
    events: tuple[RunEventModel, ...]
    events_truncated: bool = False
    files_truncated: bool = False
    research_delivery: ResearchProvenance | None = None


class TaskEvidenceSource(Protocol):
    async def read(
        self,
        owner_id: UUID,
        task_id: UUID,
        run_id: UUID | None = None,
    ) -> TaskEvidenceRecords: ...


def validate_records(
    records: TaskEvidenceRecords, owner_id: UUID, task_id: UUID, run_id: UUID | None
) -> None:
    """Recheck injected adapters too; trust is not conveyed by an arbitrary source reference."""
    task = records.task
    if task.user_id != owner_id:
        raise AuthorizationError("Execution owner mismatch", code="snapshot_owner_mismatch")
    if task.id != task_id:
        raise ConflictError("Task identity mismatch", code="snapshot_identity_conflict")
    if task.flow_id != "rna_seq" and not (task.flow_id == "counts_deg" and records.research_delivery is not None):
        raise ValidationError("Phase 0 supports RNA-seq Tasks only")
    run = records.run
    if run_id is not None and (run is None or run.id != run_id):
        raise ConflictError("Requested Run not associated with Task")
    if run is not None:
        if run.user_id != owner_id:
            raise AuthorizationError("Execution owner mismatch", code="snapshot_owner_mismatch")
        if run.task_id != task_id or run.flow_id != task.flow_id or run.confirmed_at is None:
            raise ConflictError("Unverified Run association", code="snapshot_identity_conflict")
    for file in records.files:
        if file.user_id != owner_id or file.owner_scope != "personal":
            raise AuthorizationError("File owner mismatch")
        if file.task_id != task_id:
            raise ConflictError("File is not associated with Task")
    for event in records.events:
        if run is None or event.run_id != run.id or event.task_id not in {None, task_id}:
            raise ConflictError("Event identity mismatch")


class DatabaseTaskEvidenceSource:
    """Caller owns transaction; use a read-only DB role/transaction for live collection."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def read(
        self,
        owner_id: UUID,
        task_id: UUID,
        run_id: UUID | None = None,
    ) -> TaskEvidenceRecords:
        with self._db.no_autoflush:
            task = await self._db.scalar(
                select(TaskModel).where(
                    TaskModel.id == task_id,
                    TaskModel.user_id == owner_id,
                )
            )
            if task is None:
                raise NotFoundError("Task not found")
            query = select(RunModel).where(RunModel.user_id == owner_id)
            query = (
                query.where(RunModel.id == run_id)
                if run_id
                else query.where(
                    RunModel.task_id == task_id,
                )
            )
            runs = tuple((await self._db.scalars(query)).all())
            if len(runs) > 1:
                raise ConflictError("Ambiguous Run association")
            if run_id is not None and not runs:
                raise NotFoundError("Run not found")
            run = runs[0] if runs else None
            files = tuple(
                (
                    await self._db.scalars(
                        select(FileRecordModel)
                        .where(
                            FileRecordModel.task_id == task_id,
                            FileRecordModel.user_id == owner_id,
                            FileRecordModel.owner_scope == "personal",
                        )
                        .order_by(FileRecordModel.id)
                        .limit(FILE_CAPTURE_LIMIT + 1)
                    )
                ).all()
            )
            events = (
                tuple(
                    (
                        await self._db.scalars(
                            select(RunEventModel)
                            .where(
                                RunEventModel.run_id == run.id,
                            )
                            .order_by(RunEventModel.sequence)
                            .limit(EVENT_CAPTURE_LIMIT + 1)
                        )
                    ).all()
                )
                if run
                else ()
            )
        research = None
        from cygnusx.core.config import get_settings

        if getattr(get_settings(), "research_delivery_read_enabled", False):
            from cygnusx.application.services.research_provenance_service import (
                ResearchProvenanceService,
            )

            research = await ResearchProvenanceService(self._db).task(
                owner_id, task_id, include_reports=False
            )
        records = TaskEvidenceRecords(
            task,
            run,
            files[:FILE_CAPTURE_LIMIT],
            events[:EVENT_CAPTURE_LIMIT],
            len(events) > EVENT_CAPTURE_LIMIT,
            len(files) > FILE_CAPTURE_LIMIT,
            research_delivery=research,
        )
        validate_records(records, owner_id, task_id, run_id)
        return records
