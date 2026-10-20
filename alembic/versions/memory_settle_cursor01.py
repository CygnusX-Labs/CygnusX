"""Cover ordered memory settlement cursor reads."""

from alembic import op

revision = "memory_settle_cursor01"
down_revision = "memory_recall_purge01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_chat_messages_session_created_message",
        "chat_messages",
        ["session_id", "created_at", "message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_created_message", table_name="chat_messages")
