"""Make project status explicit and retain deleted identities."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "project_lifecycle01"
down_revision = "memory_settle_cursor01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE projects SET status = 'active' WHERE status IS NULL")
    with op.batch_alter_table("projects") as batch:
        batch.alter_column(
            "status", existing_type=sa.String(20), nullable=False, server_default="active"
        )
    op.create_table(
        "project_tombstones",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column(
            "deleted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "slug", name="uq_project_tombstones_user_slug"),
    )


def downgrade() -> None:
    # Never erase deletion decisions: an older backfill would resurrect these slugs.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM project_tombstones LIMIT 1")).first():
        raise RuntimeError("Retained project tombstones prevent lifecycle downgrade")
    op.drop_table("project_tombstones")
    with op.batch_alter_table("projects") as batch:
        batch.alter_column(
            "status", existing_type=sa.String(20), nullable=True, server_default=None
        )
