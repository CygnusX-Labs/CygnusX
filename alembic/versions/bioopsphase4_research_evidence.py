"""Bind execution and immutable result observations without rewriting historical records."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "bioopsphase4"
down_revision = "bioopsphase3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_analysis_links", sa.Column("execution_binding", sa.JSON(), nullable=True)
    )
    op.create_table(
        "result_manifest_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "analysis_link_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dataset_analysis_links.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("task_id", "evidence_digest", name="uq_result_observation_facts"),
    )
    for column in ("user_id", "project_id", "task_id"):
        op.create_index(
            "ix_result_manifest_observations_" + column, "result_manifest_observations", [column]
        )
    op.add_column(
        "reports", sa.Column("result_observation_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_index("ix_reports_result_observation_id", "reports", ["result_observation_id"])
    op.add_column(
        "report_files", sa.Column("file_record_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    # SQLite batch mode rebuilds only the affected test tables; production PostgreSQL uses ALTER.
    with op.batch_alter_table("reports") as batch:
        batch.create_foreign_key(
            "fk_reports_result_observation",
            "result_manifest_observations",
            ["result_observation_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    with op.batch_alter_table("report_files") as batch:
        batch.create_foreign_key(
            "fk_report_files_file_record",
            "file_records",
            ["file_record_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION cygnusx_reject_result_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Result observations are immutable'; END; $$"
        )
        op.execute(
            "CREATE TRIGGER result_observation_immutable BEFORE UPDATE OR DELETE ON result_manifest_observations FOR EACH ROW EXECUTE FUNCTION cygnusx_reject_result_update()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER result_observation_immutable ON result_manifest_observations")
        op.execute("DROP FUNCTION cygnusx_reject_result_update()")
    with op.batch_alter_table("report_files") as batch:
        batch.drop_constraint("fk_report_files_file_record", type_="foreignkey")
        batch.drop_column("file_record_id")
    with op.batch_alter_table("reports") as batch:
        batch.drop_constraint("fk_reports_result_observation", type_="foreignkey")
        batch.drop_index("ix_reports_result_observation_id")
        batch.drop_column("result_observation_id")
    op.drop_table("result_manifest_observations")
    op.drop_column("dataset_analysis_links", "execution_binding")
