"""Harden admission units and provenance; legacy bindings require reconciliation."""

import sqlalchemy as sa
from alembic import op

revision = "dwnbinding02"
down_revision = "dwnadmission01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("download_execution_budgets", "download_execution_admissions"):
        op.alter_column(table, "status", existing_type=sa.String(20), type_=sa.String(32))
    op.add_column("dataset_ingestions", sa.Column("approval_snapshot", sa.JSON(), nullable=True))
    for name in ("limit_bytes", "reserved_bytes", "admitted_bytes"):
        op.alter_column(
            "download_execution_budgets",
            name,
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            nullable=name == "admitted_bytes",
        )
    for name in ("disk_block_limit_bytes", "disk_inodes_limit"):
        op.add_column("download_execution_budgets", sa.Column(name, sa.BigInteger(), nullable=True))
    # Existing rows lack trusted measurement and OS limits. Never grandfather them.
    op.execute(
        "UPDATE download_execution_budgets SET status = 'RECONCILIATION_REQUIRED', admitted_bytes = NULL, disk_block_limit_bytes = 1, disk_inodes_limit = 1"
    )
    for name in ("disk_block_limit_bytes", "disk_inodes_limit"):
        op.alter_column("download_execution_budgets", name, nullable=False)
    op.create_check_constraint(
        "ck_download_budget_reservation",
        "download_execution_budgets",
        "limit_bytes > 0 AND reserved_bytes >= 0 AND reserved_bytes <= limit_bytes",
    )
    op.create_check_constraint(
        "ck_download_budget_measurement",
        "download_execution_budgets",
        "admitted_bytes IS NULL OR (admitted_bytes >= 0 AND admitted_bytes <= reserved_bytes)",
    )
    op.create_check_constraint(
        "ck_download_budget_disk",
        "download_execution_budgets",
        "disk_block_limit_bytes > 0 AND disk_inodes_limit > 0",
    )
    for name, kind in (
        ("caller_kind", sa.String(40)),
        ("tool_digest", sa.String(64)),
        ("source_digest", sa.String(64)),
        ("attempt_id", sa.Uuid()),
        ("reserved_bytes", sa.BigInteger()),
    ):
        op.add_column("download_execution_admissions", sa.Column(name, kind, nullable=True))
    op.execute(
        "UPDATE download_execution_admissions SET status = 'RECONCILIATION_REQUIRED', revoked = true, caller_kind = 'legacy_untrusted', tool_digest = repeat('0',64), source_digest = repeat('0',64), attempt_id = id, reserved_bytes = 0"
    )
    for name in ("caller_kind", "tool_digest", "source_digest", "attempt_id", "reserved_bytes"):
        op.alter_column("download_execution_admissions", name, nullable=False)
    op.create_unique_constraint(
        "uq_download_admission_attempt",
        "download_execution_admissions",
        ["task_id", "attempt_id", "execution_epoch"],
    )
    op.create_check_constraint(
        "ck_download_admission_epoch",
        "download_execution_admissions",
        "execution_epoch >= 0 AND reserved_bytes >= 0",
    )


def downgrade() -> None:
    # Refuse destructive narrowing or loss of unsettled audit evidence.
    connection = op.get_bind()
    count = connection.execute(
        sa.text("SELECT count(*) FROM download_execution_admissions")
    ).scalar_one()
    budgets = connection.execute(
        sa.text("SELECT count(*) FROM download_execution_budgets")
    ).scalar_one()
    snapshots = connection.execute(
        sa.text("SELECT count(*) FROM dataset_ingestions WHERE approval_snapshot IS NOT NULL")
    ).scalar_one()
    if count or budgets or snapshots:
        raise RuntimeError(
            "Admission audit data exists: preserve it and use a forward compatibility migration"
        )
    for table in ("download_execution_budgets", "download_execution_admissions"):
        op.alter_column(table, "status", existing_type=sa.String(32), type_=sa.String(20))
    op.drop_constraint("ck_download_admission_epoch", "download_execution_admissions")
    op.drop_constraint("uq_download_admission_attempt", "download_execution_admissions")
    for name in ("reserved_bytes", "attempt_id", "source_digest", "tool_digest", "caller_kind"):
        op.drop_column("download_execution_admissions", name)
    for name in (
        "ck_download_budget_disk",
        "ck_download_budget_measurement",
        "ck_download_budget_reservation",
    ):
        op.drop_constraint(name, "download_execution_budgets")
    for name in ("disk_inodes_limit", "disk_block_limit_bytes"):
        op.drop_column("download_execution_budgets", name)
    for name in ("limit_bytes", "reserved_bytes", "admitted_bytes"):
        op.alter_column(
            "download_execution_budgets",
            name,
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            nullable=False,
        )
    op.drop_column("dataset_ingestions", "approval_snapshot")
