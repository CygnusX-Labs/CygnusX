"""Persist immutable evidence captures and independent report jobs.

Revision ID: reportauditphase1
Revises: dynamicrouting03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "reportauditphase1"
down_revision = "dynamicrouting03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uid = postgresql.UUID(as_uuid=True)
    clock = sa.DateTime(timezone=True)
    op.create_table(
        "report_snapshots",
        sa.Column("id", uid, primary_key=True),
        sa.Column("task_id", uid, nullable=False),
        sa.Column("user_id", uid, nullable=False),
        sa.Column("run_id", uid, nullable=True),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("captured_at", clock, nullable=False),
        sa.Column("created_at", clock, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", clock, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_report_snapshots_task_id", "report_snapshots", ["task_id"])
    op.create_index("ix_report_snapshots_user_id", "report_snapshots", ["user_id"])
    op.create_index(
        "uq_report_snapshots_digest",
        "report_snapshots",
        ["user_id", "task_id", "snapshot_digest"],
        unique=True,
    )
    # Application validation alone cannot protect snapshots from bulk SQL updates.
    op.execute("""
        CREATE FUNCTION reject_report_snapshot_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'report snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER report_snapshots_immutable
        BEFORE UPDATE ON report_snapshots FOR EACH ROW
        EXECUTE FUNCTION reject_report_snapshot_update()
    """)
    op.add_column(
        "reports",
        sa.Column("report_kind", sa.String(32), nullable=False, server_default="scientific"),
    )
    op.add_column("reports", sa.Column("snapshot_id", uid, nullable=True))
    op.add_column("reports", sa.Column("template_version", sa.String(40), nullable=True))
    op.add_column("reports", sa.Column("evidence_partial", sa.Boolean(), nullable=True))
    op.create_foreign_key(
        "fk_reports_snapshot_id",
        "reports",
        "report_snapshots",
        ["snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_reports_snapshot_template",
        "reports",
        ["user_id", "snapshot_id", "template_version"],
        unique=True,
    )
    op.add_column("report_files", sa.Column("sha256", sa.String(64), nullable=True))
    op.create_table(
        "report_generation_jobs",
        sa.Column("id", uid, primary_key=True),
        sa.Column("task_id", uid, nullable=False),
        sa.Column("user_id", uid, nullable=False),
        sa.Column("run_id", uid, nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("template_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("evidence_partial", sa.Boolean(), nullable=False),
        sa.Column("finished_at", clock, nullable=True),
        sa.Column("archive_path", sa.String(1024), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", uid, nullable=True),
        sa.Column("report_id", uid, nullable=True),
        sa.Column("created_at", clock, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", clock, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["report_snapshots.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('queued','collecting','rendering','publishing','ready','failed')",
            name="ck_report_generation_jobs_status",
        ),
    )
    for column in ("task_id", "user_id", "status"):
        op.create_index(f"ix_report_generation_jobs_{column}", "report_generation_jobs", [column])
    op.create_index(
        "ix_report_generation_jobs_user_id_created_at",
        "report_generation_jobs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "uq_report_generation_jobs_idempotency_key",
        "report_generation_jobs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "uq_report_generation_jobs_active",
        "report_generation_jobs",
        ["user_id", "task_id", "template_version"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','collecting','rendering','publishing')"),
    )


def downgrade() -> None:
    op.drop_table("report_generation_jobs")
    op.drop_column("report_files", "sha256")
    op.drop_index("uq_reports_snapshot_template", table_name="reports")
    op.drop_constraint("fk_reports_snapshot_id", "reports", type_="foreignkey")
    for column in ("evidence_partial", "template_version", "snapshot_id", "report_kind"):
        op.drop_column("reports", column)
    op.drop_table("report_snapshots")
    op.execute("DROP FUNCTION reject_report_snapshot_update()")
