"""Normalize legacy personal memory partitions without deleting source history."""

import hashlib
from collections import defaultdict
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "memory_partition01"
down_revision = "memory_rank01"
branch_labels = None
depends_on = None


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def upgrade() -> None:
    with op.batch_alter_table("memory_blocks") as batch:
        batch.add_column(sa.Column("status", sa.String(16), nullable=False, server_default="active"))
        batch.add_column(sa.Column("superseded_by", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_memory_blocks_superseded_by", "memory_blocks", ["superseded_by"], ["id"])
    connection = op.get_bind()
    metadata = sa.MetaData()
    facts = sa.Table("memory_facts", metadata, autoload_with=connection)
    blocks = sa.Table("memory_blocks", metadata, autoload_with=connection)

    # Empty Agent partitions are personal shared memory, never project storage.
    connection.execute(facts.update().where(
        facts.c.agent_id == "", facts.c.scope.in_(["project", "summary"]),
        facts.c.status == "active",
    ).values(status="archived"))
    legacy = connection.execute(sa.select(
        facts.c.id, facts.c.user_id, facts.c.scope, facts.c.content,
        facts.c.agent_id, facts.c.project_id, facts.c.content_hash,
    ).where(
        facts.c.status == "active", facts.c.scope.in_(["profile", "preference"]),
    ).order_by(facts.c.created_at.asc(), facts.c.id.asc())).mappings().all()
    for source in legacy:
        key = _digest(source["content"])
        if source["agent_id"] == "" and source["project_id"] is None and source["content_hash"] == key:
            continue
        occupied = connection.execute(sa.select(
            facts.c.id, facts.c.status, facts.c.scope, facts.c.project_id,
        ).where(
            facts.c.user_id == source["user_id"], facts.c.agent_id == "",
            facts.c.content_hash == key,
        )).mappings().first()
        if occupied is not None and (
            occupied["scope"] not in {"profile", "preference"}
            or occupied["project_id"] is not None
        ):
            connection.execute(facts.update().where(facts.c.id == occupied["id"]).values(
                content_hash=_digest(f"historical:{occupied['id']}\0{key}")
            ))
            occupied = None
        if occupied is None:
            columns = [column.name for column in facts.c if column.name != "id"]
            overrides = {
                "agent_id": sa.literal(""), "project_id": sa.null(), "content_hash": sa.literal(key),
                "status": sa.literal("active"), "superseded_by": sa.null(),
            }
            # Copy JSON/vector columns inside SQL, preserving their database types.
            copied = sa.select(*(overrides.get(name, facts.c[name]) for name in columns)).where(
                facts.c.id == source["id"]
            )
            target_id = connection.execute(facts.insert().from_select(columns, copied).returning(facts.c.id)).scalar_one()
            target_status = "active"
        else:
            target_id, target_status = occupied["id"], occupied["status"]
        connection.execute(facts.update().where(facts.c.id == source["id"]).values(
            status="archived" if target_status == "archived" else "superseded",
            superseded_by=None if target_status == "archived" else target_id,
        ))

    # Existing curated shared content wins. A never-edited empty block can be
    # seeded from the most recently edited legacy block; all source rows remain.
    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for source in connection.execute(sa.select(blocks).where(
        blocks.c.agent_id != "", blocks.c.block_name.in_(["profile", "preferences"]),
        blocks.c.status == "active",
    ).order_by(blocks.c.updated_at.desc(), blocks.c.id.desc())).mappings():
        groups[(source["user_id"], source["block_name"])].append(source)
    for (user_id, name), sources in groups.items():
        target = connection.execute(sa.select(blocks).where(
            blocks.c.user_id == user_id, blocks.c.agent_id == "", blocks.c.block_name == name,
        )).mappings().first()
        selected = next((row for row in sources if row["content"].strip()), sources[0])
        default_limit = 1500 if name == "profile" else 2000
        version = max([row["version"] for row in sources] + ([target["version"]] if target else [])) + 1
        if target is None:
            target_id = connection.execute(blocks.insert().values(
                user_id=user_id, agent_id="", block_name=name, content=selected["content"],
                char_limit=max(default_limit, selected["char_limit"], len(selected["content"])),
                version=version, status="active", created_at=sa.func.current_timestamp(),
                updated_at=sa.func.current_timestamp(),
            ).returning(blocks.c.id)).scalar_one()
        else:
            target_id = target["id"]
            values = {"version": version, "updated_at": sa.func.current_timestamp()}
            if target["status"] == "active" and not target["content"] and target["version"] == 1:
                values.update(content=selected["content"], char_limit=max(
                    target["char_limit"], selected["char_limit"], len(selected["content"])
                ))
            connection.execute(blocks.update().where(blocks.c.id == target_id).values(**values))
        connection.execute(blocks.update().where(blocks.c.id.in_([row["id"] for row in sources])).values(
            status="archived", superseded_by=target_id,
        ))


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM memory_blocks WHERE status != 'active' OR superseded_by IS NOT NULL")):
        raise RuntimeError("Reviewed data rollback required before dropping archived memory block history")
    with op.batch_alter_table("memory_blocks") as batch:
        batch.drop_constraint("fk_memory_blocks_superseded_by", type_="foreignkey")
        batch.drop_column("superseded_by")
        batch.drop_column("status")
