"""Index recall idempotency receipts for bounded TTL cleanup."""

from alembic import op

revision = "memory_recall_purge01"
down_revision = "memory_consolidate_rollback01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_memory_recall_batches_created_at",
        "memory_recall_batches",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_recall_batches_created_at", table_name="memory_recall_batches")
