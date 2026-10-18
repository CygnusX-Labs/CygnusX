"""Append minimal project report identity; never relax Task report tables."""

import sqlalchemy as sa
from alembic import op

revision = "projectreport01"
down_revision = "mcpdigestmerge01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_report_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
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
            "source_manifest_job_id",
            sa.Uuid(),
            sa.ForeignKey("project_export_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "parent_id", sa.Uuid(), sa.ForeignKey("project_report_jobs.id", ondelete="RESTRICT")
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("archive_path", sa.String(1024)),
        sa.Column(
            "html_file_record_id", sa.Uuid(), sa.ForeignKey("file_records.id", ondelete="RESTRICT")
        ),
        sa.Column("html_sha256", sa.String(64)),
        sa.Column("html_size", sa.Integer()),
        sa.Column(
            "pdf_file_record_id", sa.Uuid(), sa.ForeignKey("file_records.id", ondelete="RESTRICT")
        ),
        sa.Column("pdf_sha256", sa.String(64)),
        sa.Column("pdf_size", sa.Integer()),
        sa.Column("pdf_status", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "user_id", "project_id", "request_key", name="uq_project_report_request"
        ),
        sa.UniqueConstraint(
            "user_id", "project_id", "source_digest", name="uq_project_report_source"
        ),
        sa.CheckConstraint(
            "status IN ('queued','validating','rendering','publishing','ready','failed')",
            name="ck_project_report_status",
        ),
        sa.CheckConstraint(
            "status != 'ready' OR (html_file_record_id IS NOT NULL AND html_sha256 IS NOT NULL AND html_size IS NOT NULL AND html_size > 0)",
            name="ck_project_report_ready_file",
        ),
        sa.CheckConstraint(
            "version >= 1 AND attempt_count >= 0", name="ck_project_report_counters"
        ),
    )
    op.create_index("ix_project_report_jobs_status", "project_report_jobs", ["status"])
    with op.batch_alter_table("report_files") as batch:
        batch.add_column(sa.Column("project_report_job_id", sa.Uuid(), nullable=True))
        batch.alter_column("report_id", existing_type=sa.Uuid(), nullable=True)
        batch.create_foreign_key(
            "fk_report_files_project_job",
            "project_report_jobs",
            ["project_report_job_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_report_files_source",
            "(report_id IS NOT NULL AND project_report_job_id IS NULL) OR (report_id IS NULL AND project_report_job_id IS NOT NULL)",
        )
        batch.create_index("ix_report_files_project_report_job_id", ["project_report_job_id"])
    op.create_table(
        "project_report_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("project_report_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "project_id", "request_key", name="uq_project_report_alias"),
    )
    frozen = (
        "user_id",
        "project_id",
        "source_manifest_job_id",
        "request_key",
        "source_digest",
        "source_snapshot",
        "parent_id",
        "version",
    )
    if op.get_bind().dialect.name == "sqlite":
        condition = " OR ".join(f"NEW.{key} IS NOT OLD.{key}" for key in frozen)
        op.execute(
            f"CREATE TRIGGER project_report_source_guard BEFORE UPDATE ON project_report_jobs WHEN {condition} BEGIN SELECT RAISE(ABORT, 'Frozen project report identity cannot change'); END"
        )
        op.execute(
            "CREATE TRIGGER project_report_publication_guard BEFORE UPDATE ON project_report_jobs WHEN OLD.status = 'ready' AND (NEW.status IS NOT OLD.status OR NEW.archive_path IS NOT OLD.archive_path OR NEW.html_file_record_id IS NOT OLD.html_file_record_id OR NEW.html_sha256 IS NOT OLD.html_sha256 OR NEW.html_size IS NOT OLD.html_size OR NEW.pdf_file_record_id IS NOT OLD.pdf_file_record_id OR NEW.pdf_sha256 IS NOT OLD.pdf_sha256 OR NEW.pdf_size IS NOT OLD.pdf_size OR NEW.pdf_status IS NOT OLD.pdf_status) BEGIN SELECT RAISE(ABORT, 'Published project report cannot change'); END"
        )
    elif op.get_bind().dialect.name == "postgresql":
        condition = " OR ".join(
            f"NEW.{key}::text IS DISTINCT FROM OLD.{key}::text" for key in frozen
        )
        op.execute(
            f"CREATE FUNCTION cygnusx_project_report_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF {condition} THEN RAISE EXCEPTION 'Frozen project report identity cannot change'; END IF; RETURN NEW; END; $$"
        )
        op.execute(
            "CREATE TRIGGER project_report_source_guard BEFORE UPDATE ON project_report_jobs FOR EACH ROW EXECUTE FUNCTION cygnusx_project_report_guard()"
        )
        op.execute(
            "CREATE FUNCTION cygnusx_project_report_publication_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF OLD.status = 'ready' AND ROW(NEW.status,NEW.archive_path,NEW.html_file_record_id,NEW.html_sha256,NEW.html_size,NEW.pdf_file_record_id,NEW.pdf_sha256,NEW.pdf_size,NEW.pdf_status) IS DISTINCT FROM ROW(OLD.status,OLD.archive_path,OLD.html_file_record_id,OLD.html_sha256,OLD.html_size,OLD.pdf_file_record_id,OLD.pdf_sha256,OLD.pdf_size,OLD.pdf_status) THEN RAISE EXCEPTION 'Published project report cannot change'; END IF; RETURN NEW; END; $$"
        )
        op.execute(
            "CREATE TRIGGER project_report_publication_guard BEFORE UPDATE ON project_report_jobs FOR EACH ROW EXECUTE FUNCTION cygnusx_project_report_publication_guard()"
        )


def downgrade() -> None:
    raise RuntimeError(
        "Project report evidence is retained; destructive downgrade requires separate approval"
    )
