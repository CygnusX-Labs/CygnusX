"""Minimal project report identity; legacy Task report tables remain unchanged."""

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


class ProjectReportJobModel(Base, TimestampMixin):
    __tablename__ = "project_report_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "request_key", name="uq_project_report_request"),
        UniqueConstraint("user_id", "project_id", "source_digest", name="uq_project_report_source"),
        CheckConstraint(
            "status IN ('queued','validating','rendering','publishing','ready','failed')",
            name="ck_project_report_status",
        ),
        CheckConstraint(
            "status != 'ready' OR (html_file_record_id IS NOT NULL AND html_sha256 IS NOT NULL AND html_size IS NOT NULL AND html_size > 0)",
            name="ck_project_report_ready_file",
        ),
        CheckConstraint("version >= 1 AND attempt_count >= 0", name="ck_project_report_counters"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    source_manifest_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_export_jobs.id", ondelete="RESTRICT")
    )
    request_key: Mapped[str] = mapped_column(String(36))
    source_digest: Mapped[str] = mapped_column(String(64))
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_report_jobs.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    archive_path: Mapped[str | None] = mapped_column(String(1024))
    html_file_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_records.id", ondelete="RESTRICT")
    )
    html_sha256: Mapped[str | None] = mapped_column(String(64))
    html_size: Mapped[int | None] = mapped_column(Integer)
    pdf_file_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_records.id", ondelete="RESTRICT")
    )
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_size: Mapped[int | None] = mapped_column(Integer)
    pdf_status: Mapped[str] = mapped_column(String(32), default="PDF_NOT_GENERATED")


class ProjectReportRequestModel(Base, TimestampMixin):
    __tablename__ = "project_report_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "request_key", name="uq_project_report_alias"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    request_key: Mapped[str] = mapped_column(String(36))
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_report_jobs.id", ondelete="RESTRICT")
    )


@event.listens_for(ProjectReportJobModel, "before_update")
def guard_project_report_source(
    _mapper: object, _connection: object, target: ProjectReportJobModel
) -> None:
    state = inspect(target)
    previous_status = state.attrs.status.history.deleted
    if (
        target.status == "ready"
        and not state.attrs.status.history.has_changes()
        or previous_status == ["ready"]
    ):
        for key in (
            "status",
            "archive_path",
            "html_file_record_id",
            "html_sha256",
            "html_size",
            "pdf_file_record_id",
            "pdf_sha256",
            "pdf_size",
            "pdf_status",
        ):
            if state.attrs[key].history.has_changes():
                raise ValueError("Published project report cannot change")
    for key in (
        "user_id",
        "project_id",
        "source_manifest_job_id",
        "request_key",
        "source_digest",
        "source_snapshot",
        "parent_id",
        "version",
    ):
        if state.attrs[key].history.has_changes():
            raise ValueError("Frozen project report identity cannot change")
