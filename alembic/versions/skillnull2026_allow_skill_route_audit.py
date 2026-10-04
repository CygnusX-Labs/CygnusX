"""allow audit records for sandbox executions without a selected Skill"""

from alembic import op

revision = "skillnull2026"
down_revision = ("f0a1b2c3d4e5", "e0f1a2b3c4d5")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("skill_invocations", "skill_id", nullable=True)


def downgrade() -> None:
    op.alter_column("skill_invocations", "skill_id", nullable=False)
