"""Versioned dataset inputs and import/task provenance. No historical backfill."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "bioopsphase3"
down_revision = "bioopsphase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assay_type", sa.String(40), nullable=False),
        sa.Column("organism", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_datasets_owner_project", "datasets", ["user_id", "project_id"])
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=False),
        sa.Column("review_annotations", sa.JSON(), nullable=False),
        sa.Column("asset_fingerprint", sa.String(64), nullable=True),
        sa.Column("handoff", sa.JSON(), nullable=True),
        sa.Column("revision_reason", sa.Text(), nullable=False),
        sa.Column(
            "initiated_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("dataset_id", "number", name="uq_dataset_version_number"),
    )
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])
    op.create_table(
        "dataset_sources",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("repository", sa.String(32), nullable=False),
        sa.Column("accession", sa.String(80), nullable=False),
        sa.Column("parent_accession", sa.String(80), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("access_status", sa.String(32), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_dataset_sources_accession", "dataset_sources", ["repository", "accession"])
    op.create_index("ix_dataset_sources_version_id", "dataset_sources", ["version_id"])
    op.create_table(
        "dataset_assets",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "file_record_id",
            sa.Uuid(),
            sa.ForeignKey("file_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "download_task_id",
            sa.Uuid(),
            sa.ForeignKey("tasks.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("data_type", sa.String(48), nullable=False),
        sa.Column("format", sa.String(32), nullable=False),
        sa.Column("compression", sa.String(16), nullable=False),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("storage_name", sa.String(500), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("checksum_status", sa.String(32), nullable=False),
        sa.Column("availability", sa.String(32), nullable=False),
        sa.Column("classification", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("version_id", "file_record_id", name="uq_dataset_asset_file"),
    )
    op.create_index("ix_dataset_assets_version_id", "dataset_assets", ["version_id"])
    op.create_table(
        "dataset_samples",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "sample_id", sa.Uuid(), sa.ForeignKey("samples.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("sample_key", sa.String(200), nullable=False),
        sa.Column("source_accessions", sa.JSON(), nullable=False),
        sa.Column("file_record_ids", sa.JSON(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("user_annotation", sa.JSON(), nullable=False),
        sa.Column("mapping_status", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("version_id", "sample_key", name="uq_dataset_sample_key"),
    )
    op.create_index("ix_dataset_samples_version_id", "dataset_samples", ["version_id"])
    op.create_table(
        "dataset_ingestions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("request_key", sa.String(80), nullable=False),
        sa.Column("parameters_hash", sa.String(64), nullable=False),
        sa.Column("normalized_request", sa.JSON(), nullable=False),
        sa.Column("confirmation_id", sa.String(128), nullable=True),
        sa.Column(
            "invocation_id",
            sa.Uuid(),
            sa.ForeignKey("agent_tool_invocations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("agent_session_id", sa.String(50), nullable=True),
        sa.Column("task_ids", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "user_id", "project_id", "request_key", name="uq_dataset_import_request"
        ),
    )
    op.create_index(
        "ix_dataset_ingestions_owner_project", "dataset_ingestions", ["user_id", "project_id"]
    )
    op.create_table(
        "dataset_analysis_links",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("handoff_hash", sa.String(64), nullable=False),
        sa.Column("flow_id", sa.String(80), nullable=False),
        sa.Column("confirmation_id", sa.String(128), nullable=True),
        sa.Column("parameters_hash", sa.String(64), nullable=False),
        sa.Column("normalized_request", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("task_id", name="uq_dataset_analysis_task"),
    )
    op.create_index(
        "ix_dataset_analysis_links_version_id", "dataset_analysis_links", ["version_id"]
    )


def downgrade() -> None:
    op.drop_table("dataset_analysis_links")
    op.drop_table("dataset_ingestions")
    op.drop_table("dataset_samples")
    op.drop_table("dataset_assets")
    op.drop_table("dataset_sources")
    op.drop_table("dataset_versions")
    op.drop_table("datasets")
