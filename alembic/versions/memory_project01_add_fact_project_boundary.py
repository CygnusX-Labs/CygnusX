"""Add project boundaries to memory facts and recover known source ownership."""

import hashlib

import sqlalchemy as sa
from alembic import op

revision = "memory_project01"
down_revision = "dwnscope06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_facts", sa.Column("project_id", sa.String(50), nullable=True))
    op.create_index("ix_memory_facts_project_id", "memory_facts", ["project_id"])
    op.execute(sa.text("""
        UPDATE memory_facts AS f SET project_id = s.project_id
        FROM chat_sessions AS s
        WHERE f.source_session_id = s.session_id AND f.user_id = s.user_id
          AND f.scope IN ('project', 'summary') AND s.project_id IS NOT NULL
    """))
    # Unattributed old project data must not silently become global memory.
    op.execute(sa.text("""
        UPDATE memory_facts SET status = 'archived'
        WHERE scope IN ('project', 'summary') AND project_id IS NULL AND status = 'active'
    """))
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT id, project_id, content, content_hash FROM memory_facts WHERE project_id IS NOT NULL"
    )).mappings()
    for row in rows:
        # A rollback/re-upgrade can encounter already scoped hashes and retired
        # historical slots. Rehash only original legacy keys, never versions.
        if row["content_hash"] != hashlib.sha256(row["content"].encode()).hexdigest():
            continue
        digest = hashlib.sha256(f"{row['project_id']}\0{row['content']}".encode()).hexdigest()
        connection.execute(sa.text(
            "UPDATE memory_facts SET content_hash = :digest WHERE id = :id"
        ), {"digest": digest, "id": row["id"]})


def downgrade() -> None:
    # Preserve facts and archive decisions; changing hashes back could collide
    # for equal content saved independently in different projects.
    op.drop_index("ix_memory_facts_project_id", table_name="memory_facts")
    op.drop_column("memory_facts", "project_id")
