"""Versioned research input provenance; FileRecord remains the file authority.

No cascade from datasets into user files, samples, Tasks or reports. A published
version is append-only through DatasetService, including human metadata corrections.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from cygnusx.infrastructure.database.base import Base, TimestampMixin


class DatasetModel(Base, TimestampMixin):
    __tablename__ = "datasets"
    __table_args__ = (Index("ix_datasets_owner_project", "user_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    assay_type: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    organism: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)


class DatasetVersionModel(Base, TimestampMixin):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "number", name="uq_dataset_version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    review_annotations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    asset_fingerprint: Mapped[str | None] = mapped_column(String(64))
    handoff: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    revision_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    initiated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class DatasetSourceModel(Base, TimestampMixin):
    __tablename__ = "dataset_sources"
    __table_args__ = (Index("ix_dataset_sources_accession", "repository", "accession"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    repository: Mapped[str] = mapped_column(String(32), nullable=False)
    accession: Mapped[str] = mapped_column(String(80), nullable=False)
    parent_accession: Mapped[str | None] = mapped_column(String(80))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    access_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class DatasetAssetModel(Base, TimestampMixin):
    __tablename__ = "dataset_assets"
    __table_args__ = (
        UniqueConstraint("version_id", "file_record_id", name="uq_dataset_asset_file"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    file_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_records.id", ondelete="RESTRICT"), nullable=False
    )
    download_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="RESTRICT")
    )
    role: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    data_type: Mapped[str] = mapped_column(String(48), default="UNKNOWN", nullable=False)
    format: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    compression: Mapped[str] = mapped_column(String(16), default="none", nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(500), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    checksum_status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    availability: Mapped[str] = mapped_column(String(32), default="UNKNOWN", nullable=False)
    classification: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class DatasetSampleModel(Base, TimestampMixin):
    """Versioned evidence projection of an existing Sample, including many runs/files."""

    __tablename__ = "dataset_samples"
    __table_args__ = (UniqueConstraint("version_id", "sample_key", name="uq_dataset_sample_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("samples.id", ondelete="RESTRICT"), nullable=False
    )
    sample_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_accessions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    file_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    user_annotation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(32), default="NEEDS_REVIEW", nullable=False)


class DatasetIngestionModel(Base, TimestampMixin):
    """Import proposal and durable reservation; execution Task remains authoritative."""

    __tablename__ = "dataset_ingestions"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", "request_key", name="uq_dataset_import_request"),
        Index("ix_dataset_ingestions_owner_project", "user_id", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="RESTRICT")
    )
    request_key: Mapped[str] = mapped_column(String(80), nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confirmation_id: Mapped[str | None] = mapped_column(String(128))
    invocation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_tool_invocations.id", ondelete="RESTRICT")
    )
    agent_session_id: Mapped[str | None] = mapped_column(String(50))
    task_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="PREPARED", nullable=False)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    preview: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class DatasetAnalysisLinkModel(Base, TimestampMixin):
    __tablename__ = "dataset_analysis_links"
    __table_args__ = (UniqueConstraint("task_id", name="uq_dataset_analysis_task"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True
    )
    handoff_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    flow_id: Mapped[str] = mapped_column(String(80), nullable=False)
    confirmation_id: Mapped[str | None] = mapped_column(String(128))
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    execution_binding: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="PREPARED", nullable=False)
