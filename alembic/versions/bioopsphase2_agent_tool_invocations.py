"""Minimal owner/project/session/tool/task audit links.

Revision ID: bioopsphase2
Revises: reportauditphase1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "bioopsphase2"
down_revision = "reportauditphase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_tool_invocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.String(50), nullable=False),
        sa.Column("project_id", sa.String(64)),
        sa.Column("conversation_id", sa.String(50), nullable=False),
        sa.Column("agent_kind", sa.String(40), nullable=False),
        sa.Column("capability_id", sa.String(100), nullable=False),
        sa.Column("request_id", sa.String(80), nullable=False),
        sa.Column("parameters_hash", sa.String(64), nullable=False),
        sa.Column("confirmation_id", sa.String(128)),
        sa.Column("task_id", sa.Uuid()),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_agent_tool_invocations_owner_session",
        "agent_tool_invocations",
        ["owner_id", "conversation_id"],
    )
    op.create_index(
        "ix_agent_tool_invocations_owner_project",
        "agent_tool_invocations",
        ["owner_id", "project_id"],
    )


def downgrade() -> None:
    op.drop_table("agent_tool_invocations")
