"""Keep bounded weekly consolidation budgets and auditable decisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "memory_consolidate01"
down_revision = "memory_partition01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_consolidation_budgets",
        sa.Column("week", sa.String(10), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "memory_consolidation_runs",
        sa.Column("run_key", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("week", sa.String(10), nullable=False),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("agent_id", sa.String(50), nullable=False),
        sa.Column("project_id", sa.String(50)),
        sa.Column("watermark", sa.Integer(), nullable=False),
        sa.Column("decisions", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM memory_consolidation_runs")):
        raise RuntimeError("Export/review consolidation audit history before schema downgrade")
    op.drop_table("memory_consolidation_runs")
    op.drop_table("memory_consolidation_budgets")
