"""Execute shared-partition data migration in disposable SQL storage."""

import hashlib
import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

pytestmark = pytest.mark.unit


@pytest.fixture
def partition_database():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    facts = sa.Table("memory_facts", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("agent_id", sa.String(50), nullable=False),
        sa.Column("project_id", sa.String(50)), sa.Column("scope", sa.String(16)),
        sa.Column("content", sa.String(1200)), sa.Column("content_hash", sa.String(64)),
        sa.Column("status", sa.String(16), server_default="active"),
        sa.Column("superseded_by", sa.Integer), sa.Column("embedding", sa.Text),
        sa.Column("keywords", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("user_id", "agent_id", "content_hash"),
    )
    blocks = sa.Table("memory_blocks", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String(50), nullable=False),
        sa.Column("agent_id", sa.String(50), nullable=False),
        sa.Column("block_name", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("char_limit", sa.Integer, nullable=False, server_default="2000"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("user_id", "agent_id", "block_name"),
    )
    metadata.create_all(engine)
    path = Path("alembic/versions/memory_partition01_normalize_shared_memory.py")
    spec = importlib.util.spec_from_file_location("memory_partition_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        yield connection, facts, blocks, migration
    engine.dispose()


def _fact(connection, table, user, agent, content, *, status="active", scope="preference", project=None):
    return connection.execute(table.insert().values(
        user_id=user, agent_id=agent, content=content, status=status, scope=scope, project_id=project,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        embedding="[0.1,0.2]", keywords=["reference"],
    ).returning(table.c.id)).scalar_one()


def _block(connection, table, user, agent, name, content, version, *, day=1):
    return connection.execute(table.insert().values(
        user_id=user, agent_id=agent, block_name=name, content=content, version=version,
        updated_at=datetime(2026, 10, day),
    ).returning(table.c.id)).scalar_one()


def test_personal_facts_normalize_with_links_without_reviving_shared_forgetting(partition_database):
    connection, facts, _, migration = partition_database
    old_a = _fact(connection, facts, "owner", "a", "GRCh38")
    old_b = _fact(connection, facts, "owner", "b", "GRCh38")
    other = _fact(connection, facts, "other", "a", "GRCh38")
    forgotten = _fact(connection, facts, "owner", "", "forgotten", status="archived")
    shadow = _fact(connection, facts, "owner", "a", "forgotten")
    invalid_project = _fact(connection, facts, "owner", "", "GRCh38", scope="project", project="p")
    migration.upgrade()
    rows = {row["id"]: row for row in connection.execute(sa.text("SELECT * FROM memory_facts")).mappings()}
    target = rows[old_a]["superseded_by"]
    assert target != old_a and rows[target]["agent_id"] == ""
    assert rows[target]["project_id"] is None and rows[target]["status"] == "active"
    assert rows[target]["embedding"] == "[0.1,0.2]"  # SQL copies opaque vector bytes without parsing.
    assert rows[old_b]["superseded_by"] == target and rows[old_b]["status"] == "superseded"
    assert rows[old_a]["content"] == "GRCh38" and rows[old_a]["agent_id"] == "a"
    assert rows[other]["superseded_by"] != target
    assert rows[forgotten]["status"] == "archived" and rows[shadow]["status"] == "archived"
    assert rows[invalid_project]["status"] == "archived"


def test_block_normalization_preserves_curated_and_cleared_content_and_source_history(partition_database):
    connection, _, blocks, migration = partition_database
    old = _block(connection, blocks, "owner", "a", "profile", "older profile", 4)
    latest = _block(connection, blocks, "owner", "b", "profile", "latest profile", 7, day=2)
    curated = _block(connection, blocks, "owner", "", "preferences", "curated", 3)
    legacy = _block(connection, blocks, "owner", "a", "preferences", "legacy text", 10)
    cleared = _block(connection, blocks, "cleared", "", "profile", "", 2)
    _block(connection, blocks, "cleared", "a", "profile", "must not return", 5)
    seeded = _block(connection, blocks, "seed", "", "preferences", "", 1)
    _block(connection, blocks, "seed", "a", "preferences", "seed content", 2)
    focus = _block(connection, blocks, "owner", "a", "current_focus", "ongoing", 1)
    migration.upgrade()
    rows = {row["id"]: row for row in connection.execute(sa.text("SELECT * FROM memory_blocks")).mappings()}
    canonical = rows[rows[old]["superseded_by"]]
    assert canonical["agent_id"] == "" and canonical["content"] == "latest profile"
    assert canonical["version"] == 8
    assert rows[old]["status"] == rows[latest]["status"] == "archived"
    assert rows[old]["content"] == "older profile"
    assert rows[curated]["content"] == "curated" and rows[curated]["version"] == 11
    assert rows[legacy]["superseded_by"] == curated
    assert rows[cleared]["content"] == ""  # Edited empty content is deliberate, not an uninitialized slot.
    assert rows[seeded]["content"] == "seed content"
    assert rows[focus]["status"] == "active" and rows[focus]["superseded_by"] is None
    with pytest.raises(RuntimeError, match="Reviewed data rollback"):
        migration.downgrade()
    assert len(connection.execute(sa.text("SELECT * FROM memory_blocks")).all()) == len(rows)


def test_empty_partition_migration_downgrades_schema(partition_database):
    connection, _, _, migration = partition_database
    migration.upgrade()
    migration.downgrade()
    assert "status" not in {column["name"] for column in sa.inspect(connection).get_columns("memory_blocks")}



def test_miskeyed_shared_fact_gets_canonical_slot_without_erasing_source(partition_database):
    connection, facts, _, migration = partition_database
    old = _fact(connection, facts, "owner", "", "miskeyed")
    connection.execute(facts.update().where(facts.c.id == old).values(content_hash="old-custom-key"))
    migration.upgrade()
    rows = {row["id"]: row for row in connection.execute(sa.text("SELECT * FROM memory_facts")).mappings()}
    target = rows[old]["superseded_by"]
    assert rows[old]["content_hash"] == "old-custom-key" and rows[old]["status"] == "superseded"
    assert rows[target]["content_hash"] == hashlib.sha256(b"miskeyed").hexdigest()
    assert rows[target]["status"] == "active" and rows[target]["superseded_by"] is None
