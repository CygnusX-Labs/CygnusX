"""Persist host process identity for safe Supervisor recovery."""

import sqlalchemy as sa
from alembic import op

revision = "dwnscope06"
down_revision = "dwnscope05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("download_execution_scopes", sa.Column("pid_start_time", sa.String(32)))
    op.add_column("download_execution_scopes", sa.Column("host_boot_id", sa.String(64)))
    op.add_column("download_execution_scopes", sa.Column("returncode", sa.Integer()))


def downgrade() -> None:
    op.drop_column("download_execution_scopes", "returncode")
    op.drop_column("download_execution_scopes", "host_boot_id")
    op.drop_column("download_execution_scopes", "pid_start_time")
