"""Allow focus blocks per project while retaining all legacy general blocks."""

import sqlalchemy as sa
from alembic import op

revision = "memory_focus_project01"
down_revision = "memory_consolidate01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_blocks", sa.Column("project_id", sa.String(50), nullable=True))
    op.drop_constraint("uq_memory_blocks_owner_name", "memory_blocks", type_="unique")
    op.create_index(
        "uq_memory_blocks_general", "memory_blocks", ["user_id", "agent_id", "block_name"],
        unique=True, postgresql_where=sa.text("project_id IS NULL"),
    )
    op.create_index(
        "uq_memory_blocks_project", "memory_blocks",
        ["user_id", "agent_id", "block_name", "project_id"], unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM memory_blocks WHERE project_id IS NOT NULL")):
        raise RuntimeError("Project focus content must be exported/reviewed before downgrade")
    op.drop_index("uq_memory_blocks_project", table_name="memory_blocks")
    op.drop_index("uq_memory_blocks_general", table_name="memory_blocks")
    op.drop_column("memory_blocks", "project_id")
    op.create_unique_constraint(
        "uq_memory_blocks_owner_name", "memory_blocks", ["user_id", "agent_id", "block_name"],
    )
