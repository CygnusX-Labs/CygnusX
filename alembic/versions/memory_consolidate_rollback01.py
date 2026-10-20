"""Add idempotent consolidation rollback state."""

import sqlalchemy as sa
from alembic import op

revision = "memory_consolidate_rollback01"
down_revision = "memory_focus_project01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_consolidation_runs",
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_rollback = bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM memory_consolidation_runs "
            "WHERE rolled_back_at IS NOT NULL OR kind = 'rollback')"
        )
    )
    if has_rollback:
        raise RuntimeError("Export/review consolidation rollback history before schema downgrade")
    op.drop_column("memory_consolidation_runs", "rolled_back_at")
