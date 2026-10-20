"""Exercise memory project data migration against a disposable SQL database."""

import hashlib
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.unit


def test_project_migration_recovers_only_owned_sources_and_preserves_unknown_history() -> None:
    path = Path("alembic/versions/memory_project01_add_fact_project_boundary.py")
    spec = importlib.util.spec_from_file_location("memory_project_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE memory_facts (
            id INTEGER PRIMARY KEY, user_id TEXT, source_session_id TEXT,
            scope TEXT, status TEXT, content TEXT, content_hash TEXT
        )"""))
        connection.execute(text("""CREATE TABLE chat_sessions (
            session_id TEXT, user_id TEXT, project_id TEXT
        )"""))
        connection.execute(text("INSERT INTO chat_sessions VALUES ('known','owner','project-a')"))
        for fact_id, owner, scope in [(1, "owner", "project"), (2, "other", "project"),
                                      (3, "owner", "preference")]:
            connection.execute(text("""INSERT INTO memory_facts VALUES (
                :id, :owner, 'known', :scope, 'active', 'fact', :hash
            )"""), {"id": fact_id, "owner": owner, "scope": scope,
                 "hash": hashlib.sha256(b"fact").hexdigest()})
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        rows = connection.execute(text("SELECT * FROM memory_facts ORDER BY id")).mappings().all()
        assert rows[0]["project_id"] == "project-a"
        assert rows[0]["status"] == "active"
        assert rows[0]["content_hash"] == hashlib.sha256(b"project-a\0fact").hexdigest()
        assert rows[1]["project_id"] is None
        assert rows[1]["status"] == "archived"
        assert rows[2]["project_id"] is None and rows[2]["status"] == "active"
        migration.downgrade()
        assert connection.scalar(text("SELECT count(*) FROM memory_facts")) == 3
        assert connection.scalar(text("SELECT status FROM memory_facts WHERE id=2")) == "archived"
    engine.dispose()


def test_ranking_migration_defaults_and_downgrade_preserve_fact_content() -> None:
    path = Path("alembic/versions/memory_rank01_add_recall_signals.py")
    spec = importlib.util.spec_from_file_location("memory_rank_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE memory_facts (id INTEGER PRIMARY KEY, content TEXT)"))
        connection.execute(text("INSERT INTO memory_facts VALUES (1, 'preserved')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        row = connection.execute(text("SELECT * FROM memory_facts")).mappings().one()
        assert row["importance"] == 5 and row["recall_count"] == 0
        migration.downgrade()
        assert connection.scalar(text("SELECT content FROM memory_facts")) == "preserved"
    engine.dispose()



def test_reupgrade_preserves_scoped_and_historical_version_hashes() -> None:
    path = Path("alembic/versions/memory_project01_add_fact_project_boundary.py")
    spec = importlib.util.spec_from_file_location("memory_project_reupgrade", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    hashes = [hashlib.sha256(b"historical:1\0old-key").hexdigest(),
              hashlib.sha256(b"p\0fact").hexdigest()]
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE memory_facts (
            id INTEGER PRIMARY KEY, user_id TEXT, source_session_id TEXT,
            scope TEXT, status TEXT, content TEXT, content_hash TEXT UNIQUE
        )"""))
        connection.execute(text("CREATE TABLE chat_sessions (session_id TEXT, user_id TEXT, project_id TEXT)"))
        connection.execute(text("INSERT INTO chat_sessions VALUES ('source','owner','p')"))
        for index, digest in enumerate(hashes):
            connection.execute(text("""INSERT INTO memory_facts VALUES (
                :id, 'owner', 'source', 'project', 'active', 'fact', :digest
            )"""), {"id": index + 1, "digest": digest})
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.execute(text(
            "SELECT content_hash FROM memory_facts ORDER BY id"
        )).scalars().all() == hashes
        migration.downgrade()
        migration.upgrade()
        assert connection.execute(text(
            "SELECT content_hash FROM memory_facts ORDER BY id"
        )).scalars().all() == hashes
    engine.dispose()
