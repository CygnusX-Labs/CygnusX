"""Persist one-use lease renewal nonces for the trusted download Supervisor."""

import sqlalchemy as sa
from alembic import op

revision = "dwnlease03"
down_revision = "dwnbinding02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_execution_lease_nonces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supervisor_id", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("execution_epoch", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "supervisor_id", "nonce", name="uq_download_execution_lease_nonce"
        ),
        sa.CheckConstraint(
            "length(trim(supervisor_id)) > 0", name="ck_download_lease_nonce_supervisor"
        ),
        sa.CheckConstraint("execution_epoch > 0", name="ck_download_lease_nonce_epoch"),
    )
    op.create_index(
        "ix_download_execution_lease_nonces_expires_at",
        "download_execution_lease_nonces",
        ["expires_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    count = connection.execute(
        sa.text("SELECT count(*) FROM download_execution_lease_nonces")
    ).scalar_one()
    if count:
        raise RuntimeError("Lease replay audit data exists; preserve it and use a forward migration")
    op.drop_index(
        "ix_download_execution_lease_nonces_expires_at",
        table_name="download_execution_lease_nonces",
    )
    op.drop_table("download_execution_lease_nonces")
