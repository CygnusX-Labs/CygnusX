"""Persist versioned research intent, without modifying business execution tables."""

import sqlalchemy as sa
from alembic import op

revision = "bioopsphase5"
down_revision = "bioopsphase4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("series_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(80), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("gaps", sa.JSON(), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "superseded_by", sa.Uuid(), sa.ForeignKey("research_plans.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "user_id", "project_id", "request_key", name="uq_research_plan_request"
        ),
        sa.UniqueConstraint("series_id", "version", name="uq_research_plan_version"),
    )
    op.create_index("ix_research_plans_owner_project", "research_plans", ["user_id", "project_id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION cygnusx_research_plan_guard() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.user_id IS DISTINCT FROM OLD.user_id
                   OR NEW.project_id IS DISTINCT FROM OLD.project_id
                   OR NEW.series_id IS DISTINCT FROM OLD.series_id
                   OR NEW.version IS DISTINCT FROM OLD.version
                   OR NEW.request_key IS DISTINCT FROM OLD.request_key
                   OR NEW.draft::text IS DISTINCT FROM OLD.draft::text
                   OR NEW.digest IS DISTINCT FROM OLD.digest THEN
                    RAISE EXCEPTION 'Research intent is immutable; create a new version';
                END IF;
                RETURN NEW;
            END; $$
        """)
        op.execute("""
            CREATE TRIGGER research_plan_document_immutable BEFORE UPDATE ON research_plans
            FOR EACH ROW EXECUTE FUNCTION cygnusx_research_plan_guard()
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER research_plan_document_immutable ON research_plans")
        op.execute("DROP FUNCTION cygnusx_research_plan_guard()")
    op.drop_table("research_plans")
