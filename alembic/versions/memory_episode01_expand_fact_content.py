"""Allow bounded episodic summaries in the existing fact store."""

import sqlalchemy as sa
from alembic import op

revision = "memory_episode01"
down_revision = "memory_project01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("memory_facts", "content", type_=sa.String(1200), existing_type=sa.String(300))


def downgrade() -> None:
    # Never truncate user history merely to roll back a schema expansion.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM memory_facts WHERE length(content) > 300")):
        raise RuntimeError("Cannot downgrade while long memory facts exist; reviewed data conversion required")
    op.alter_column("memory_facts", "content", type_=sa.String(300), existing_type=sa.String(1200))
