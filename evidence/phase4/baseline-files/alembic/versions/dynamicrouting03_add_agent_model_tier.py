"""persist model tier declarations on agent templates"""

import sqlalchemy as sa
from alembic import op

revision = "dynamicrouting03"
down_revision = "dynamicrouting02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_templates",
        sa.Column("model_tier", sa.String(16), nullable=False, server_default="auto"),
    )


def downgrade() -> None:
    op.drop_column("agent_templates", "model_tier")
