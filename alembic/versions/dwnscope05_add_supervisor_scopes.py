"""Persist Supervisor scope identity and process lifecycle facts."""

import sqlalchemy as sa
from alembic import op

revision = "dwnscope05"
down_revision = "dwnexec04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_execution_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope_ref", sa.Uuid(), nullable=False),
        sa.Column("admission_ref", sa.Uuid(), nullable=False),
        sa.Column("budget_ref", sa.Uuid(), nullable=False),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("execution_epoch", sa.Integer(), nullable=False),
        sa.Column("caller_id", sa.String(128), nullable=False),
        sa.Column("environment_id", sa.String(128), nullable=False),
        sa.Column("policy_revision", sa.String(128), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("pid", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("lease_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("egress_revoked", sa.Boolean(), nullable=False),
        sa.Column("cleanup_complete", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "execution_id", name="uq_download_scope_execution"),
        sa.UniqueConstraint("scope_ref", name="uq_download_scope_ref"),
        sa.CheckConstraint("execution_epoch > 0", name="ck_download_scope_epoch"),
        sa.CheckConstraint(
            "state IN ('prepared', 'starting', 'running', 'stopped', 'unknown')",
            name="ck_download_scope_state",
        ),
    )
    op.create_index(
        "ix_download_execution_scopes_expiry",
        "download_execution_scopes",
        ["state", "lease_deadline"],
    )


def downgrade() -> None:
    op.drop_index("ix_download_execution_scopes_expiry", table_name="download_execution_scopes")
    op.drop_table("download_execution_scopes")
