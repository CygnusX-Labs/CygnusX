"""Bind one deterministic execution identity to each consumed admission."""

import sqlalchemy as sa
from alembic import op

revision = "dwnexec04"
down_revision = "dwnlease03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    legacy_consumed = connection.execute(
        sa.text(
            "SELECT count(*) FROM download_execution_admissions "
            "WHERE status IN ('CONSUMED', 'SETTLED')"
        )
    ).scalar_one()
    if legacy_consumed:
        raise RuntimeError(
            "Consumed admissions lack execution identity; preserve them and use a "
            "forward reconciliation migration before dwnexec04"
        )
    op.add_column(
        "download_execution_admissions",
        sa.Column("execution_id", sa.Uuid(), nullable=True),
    )
    # The column must exist before this audit query.  A non-null value can only
    # come from a forward reconciliation migration; never overwrite it here.
    legacy_identity = connection.execute(
        sa.text("SELECT count(*) FROM download_execution_admissions WHERE execution_id IS NOT NULL")
    ).scalar_one()
    if legacy_identity:
        raise RuntimeError(
            "Execution identity column already contains data; use a forward "
            "reconciliation migration before dwnexec04"
        )
    op.create_unique_constraint(
        "uq_download_admission_execution_identity",
        "download_execution_admissions",
        ["task_id", "execution_id"],
    )
    op.execute(
        "UPDATE download_execution_admissions SET status = 'RECONCILIATION_REQUIRED', "
        "revoked = true WHERE status = 'READY' AND execution_id IS NULL"
    )


def downgrade() -> None:
    connection = op.get_bind()
    count = connection.execute(
        sa.text("SELECT count(*) FROM download_execution_admissions WHERE execution_id IS NOT NULL")
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Execution identity audit data exists; preserve it and use a forward migration"
        )
    op.drop_constraint(
        "uq_download_admission_execution_identity",
        "download_execution_admissions",
        type_="unique",
    )
    op.drop_column("download_execution_admissions", "execution_id")
