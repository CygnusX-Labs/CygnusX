"""add model routing decision audit table"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "dynamicrouting02"
down_revision = "dynamicrouting01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_routing_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("complexity", sa.String(16)),
        sa.Column("explicit_model_id", sa.String(64)),
        sa.Column("model_tier", sa.String(16)),
        sa.Column("chosen_provider", sa.String(64), nullable=False),
        sa.Column("cascade_providers", JSONB, nullable=False, server_default="[]"),
        sa.Column("candidates_considered", JSONB, nullable=False, server_default="[]"),
        sa.Column("decision_reason", sa.String(64), nullable=False),
        sa.Column("cascade_events", JSONB, nullable=False, server_default="[]"),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("degrade_reason", sa.String(64)),
        sa.Column("usage_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_mrd_request", "model_routing_decisions", ["request_id", "step_index"])
    op.create_index("idx_mrd_created", "model_routing_decisions", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_mrd_created", table_name="model_routing_decisions")
    op.drop_index("idx_mrd_request", table_name="model_routing_decisions")
    op.drop_table("model_routing_decisions")
