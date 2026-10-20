"""Persist importance, reinforcement and idempotent recall receipts."""

import sqlalchemy as sa
from alembic import op

revision = "memory_rank01"
down_revision = "memory_episode01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_facts", sa.Column("importance", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("memory_facts", sa.Column("recall_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "memory_recall_batches",
        sa.Column("batch_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("memory_recall_batches")
    op.drop_column("memory_facts", "recall_count")
    op.drop_column("memory_facts", "importance")
