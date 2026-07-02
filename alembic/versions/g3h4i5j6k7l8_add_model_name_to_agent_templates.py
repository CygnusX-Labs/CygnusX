"""add_model_name_to_agent_templates

Revision ID: g3h4i5j6k7l8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-02 10:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'g3h4i5j6k7l8'
down_revision: str | None = 'c2d3e4f5a6b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'agent_templates',
        sa.Column('model_name', sa.String(length=100), nullable=False, server_default='')
    )


def downgrade() -> None:
    op.drop_column('agent_templates', 'model_name')
