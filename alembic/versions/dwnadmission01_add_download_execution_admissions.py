"""Persist server-issued download admission and shared budget bindings."""

import sqlalchemy as sa
from alembic import op

revision = "dwnadmission01"
down_revision = ("dwnreceiptnonce01", "resstream01")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_execution_budgets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="RESTRICT")),
        sa.Column("limit_bytes", sa.Integer(), nullable=False),
        sa.Column("reserved_bytes", sa.Integer(), nullable=False),
        sa.Column("admitted_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("policy_revision", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_download_execution_budgets_owner_status",
        "download_execution_budgets",
        ["owner_id", "status"],
    )
    op.create_table(
        "download_execution_admissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("budget_id", sa.Uuid(), sa.ForeignKey("download_execution_budgets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ingestion_id", sa.Uuid(), sa.ForeignKey("dataset_ingestions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("confirmation_id", sa.String(length=128), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("protocol", sa.String(length=20), nullable=False),
        sa.Column("policy_revision", sa.String(length=128), nullable=False),
        sa.Column("environment_id", sa.String(length=128), nullable=False),
        sa.Column("caller_id", sa.String(length=128), nullable=False),
        sa.Column("allowed_destinations", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("execution_epoch", sa.Integer(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_download_execution_admission_task"),
        sa.UniqueConstraint("ingestion_id", name="uq_download_execution_admission_ingestion"),
    )
    op.create_index(
        "ix_download_execution_admissions_expiry",
        "download_execution_admissions",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_download_execution_admissions_expiry", table_name="download_execution_admissions")
    op.drop_table("download_execution_admissions")
    op.drop_index("ix_download_execution_budgets_owner_status", table_name="download_execution_budgets")
    op.drop_table("download_execution_budgets")
