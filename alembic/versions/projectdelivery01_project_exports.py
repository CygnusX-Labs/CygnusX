"""Independent immutable project export scope and durable publication job."""

import sqlalchemy as sa
from alembic import op

revision = "projectdelivery01"
down_revision = "bioopsphase5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_export_jobs",
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
        sa.Column("manifest_digest", sa.String(64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("archive_path", sa.String(1024)),
        sa.Column("archive_sha256", sa.String(64)),
        sa.Column("archive_size", sa.Integer()),
        sa.Column(
            "file_record_id", sa.Uuid(), sa.ForeignKey("file_records.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "user_id", "project_id", "request_key", name="uq_project_export_request"
        ),
        sa.UniqueConstraint(
            "user_id", "project_id", "manifest_digest", name="uq_project_export_manifest"
        ),
        sa.CheckConstraint(
            "status IN ('queued','collecting','validating','packaging','verifying','publishing','ready','failed')",
            name="ck_project_export_status",
        ),
    )
    for name in ("user_id", "project_id", "status"):
        op.create_index(f"ix_project_export_jobs_{name}", "project_export_jobs", [name])
    op.create_table(
        "project_export_requests",
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
            sa.ForeignKey("project_export_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "user_id", "project_id", "request_key", name="uq_project_export_request_alias"
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION cygnusx_project_export_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.project_id IS DISTINCT FROM OLD.project_id
            OR NEW.request_key IS DISTINCT FROM OLD.request_key OR NEW.manifest_digest IS DISTINCT FROM OLD.manifest_digest
            OR NEW.manifest::text IS DISTINCT FROM OLD.manifest::text THEN
                RAISE EXCEPTION 'Frozen project export scope cannot change';
            END IF;
            RETURN NEW;
        END; $$""")
        op.execute(
            "CREATE TRIGGER project_export_scope_guard BEFORE UPDATE ON project_export_jobs FOR EACH ROW EXECUTE FUNCTION cygnusx_project_export_guard()"
        )


def downgrade() -> None:
    # Only for an explicitly disposable isolated database; never erase production evidence.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER project_export_scope_guard ON project_export_jobs")
        op.execute("DROP FUNCTION cygnusx_project_export_guard()")
    op.drop_table("project_export_requests")
    op.drop_table("project_export_jobs")
