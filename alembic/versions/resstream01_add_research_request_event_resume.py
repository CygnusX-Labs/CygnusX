"""Add idempotency key for resumable research-agent generations."""

import sqlalchemy as sa
from alembic import op

revision = "resstream01"
down_revision = "dwnreceiptnonce01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_chat_messages_research_request",
        "chat_messages",
        ["session_id", sa.text("(metadata_json ->> 'research_request_id')")],
        unique=True,
        postgresql_where=sa.text(
            "role = 'user' AND (metadata_json ->> 'research_request_id') IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_chat_messages_research_request", table_name="chat_messages")
