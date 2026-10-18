"""Project-level durable export, deliberately independent of analysis Task."""

import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from cygnusx.infrastructure.database.base import Base, TimestampMixin


class ProjectExportJobModel(Base, TimestampMixin):
    __tablename__ = "project_export_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "request_key", name="uq_project_export_request"),
        UniqueConstraint(
            "user_id", "project_id", "manifest_digest", name="uq_project_export_manifest"
        ),
        CheckConstraint(
            "status IN ('queued','collecting','validating','packaging','verifying','publishing','ready','failed')",
            name="ck_project_export_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    request_key: Mapped[str] = mapped_column(String(36))
    manifest_digest: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    archive_path: Mapped[str | None] = mapped_column(String(1024))
    archive_sha256: Mapped[str | None] = mapped_column(String(64))
    archive_size: Mapped[int | None] = mapped_column(Integer)
    file_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_records.id", ondelete="RESTRICT")
    )


class ProjectExportRequestModel(Base, TimestampMixin):
    """Persist all request aliases when identical frozen manifests share one job."""

    __tablename__ = "project_export_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "project_id", "request_key", name="uq_project_export_request_alias"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    request_key: Mapped[str] = mapped_column(String(36))
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_export_jobs.id", ondelete="RESTRICT")
    )


@event.listens_for(ProjectExportJobModel, "before_update")
def guard_export_scope(_mapper: object, _connection: object, target: ProjectExportJobModel) -> None:
    state = inspect(target)
    for key in ("user_id", "project_id", "request_key", "manifest_digest", "manifest"):
        if state.attrs[key].history.has_changes():
            raise ValueError("Frozen project export scope cannot change")
