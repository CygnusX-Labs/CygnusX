"""Persist one-time nonces for trusted download execution receipts."""

import sqlalchemy as sa
from alembic import op

revision = "dwnreceiptnonce01"
down_revision = "projectreport01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_execution_receipt_nonces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supervisor_id", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "supervisor_id", "nonce", name="uq_download_execution_receipt_nonce"
        ),
    )
    op.create_index(
        "ix_download_execution_receipt_nonces_expires_at",
        "download_execution_receipt_nonces",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_download_execution_receipt_nonces_expires_at",
        table_name="download_execution_receipt_nonces",
    )
    op.drop_table("download_execution_receipt_nonces")
