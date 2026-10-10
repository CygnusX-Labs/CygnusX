"""add dynamic model routing metadata to providers"""

import sqlalchemy as sa
from alembic import op

revision = "dynamicrouting01"
down_revision = "skillnull2026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_provider_configs", sa.Column("tier", sa.String(16), nullable=False, server_default="light"))
    op.add_column("ai_provider_configs", sa.Column("cost_per_1m_in", sa.Float(), nullable=True))
    op.add_column("ai_provider_configs", sa.Column("cost_per_1m_out", sa.Float(), nullable=True))
    op.add_column("ai_provider_configs", sa.Column("latency_budget_ms", sa.Integer(), nullable=True))
    op.add_column("ai_provider_configs", sa.Column("vendor", sa.String(64), nullable=True))
    op.add_column("ai_provider_configs", sa.Column("weight", sa.Integer(), nullable=False, server_default="100"))
    op.execute(
        sa.text(
            """
            UPDATE ai_provider_configs
            SET is_default = FALSE
            WHERE is_default = TRUE
              AND id NOT IN (
                  SELECT id FROM ai_provider_configs
                  WHERE is_default = TRUE
                  ORDER BY updated_at DESC NULLS LAST, id
                  LIMIT 1
              )
            """
        )
    )
    op.create_index(
        "uq_ai_provider_configs_default",
        "ai_provider_configs",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default = TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_ai_provider_configs_default", table_name="ai_provider_configs")
    for column in ("weight", "vendor", "latency_budget_ms", "cost_per_1m_out", "cost_per_1m_in", "tier"):
        op.drop_column("ai_provider_configs", column)
