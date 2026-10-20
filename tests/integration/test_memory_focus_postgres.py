"""Opt-in PostgreSQL focus migration/concurrent-create rehearsal on a disposable DB.

MEMORY_TEST_DATABASE_URL must name memory_acceptance_test*. No production fallback.
This does not prove the complete snapshot migration or model/Worker acceptance.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from cygnusx.application.services.agent_memory_service import AgentMemoryService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_focus_migration_concurrent_create_and_protected_downgrade(monkeypatch):
    dsn = os.environ.get("MEMORY_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("No dedicated MEMORY_TEST_DATABASE_URL; actual PostgreSQL acceptance pending")
    url = make_url(dsn)
    if url.get_backend_name() != "postgresql" or not (url.database or "").startswith("memory_acceptance_test"):
        pytest.fail("Dedicated memory_acceptance_test PostgreSQL required")
    schema = "memory_focus_" + uuid4().hex
    engine = create_async_engine(url.set(drivername="postgresql+asyncpg"),
                                 connect_args={"server_settings": {"search_path": f"{schema},public"}})
    path = "alembic/versions/memory_focus_project01_scope_focus_blocks.py"
    spec = importlib.util.spec_from_file_location("memory_focus_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    from types import SimpleNamespace

    monkeypatch.setattr("cygnusx.application.services.agent_memory_service.get_settings",
                        lambda: SimpleNamespace(memory_focus_per_project_enabled=True))

    def migrate(sync, direction):
        migration.op = Operations(MigrationContext.configure(sync))
        getattr(migration, direction)()

    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text("""CREATE TABLE memory_blocks (
                id SERIAL PRIMARY KEY, user_id VARCHAR(50) NOT NULL, agent_id VARCHAR(50) NOT NULL,
                block_name VARCHAR(32) NOT NULL, content TEXT NOT NULL DEFAULT '',
                char_limit INTEGER NOT NULL DEFAULT 2000, version INTEGER NOT NULL DEFAULT 1,
                status VARCHAR(16) NOT NULL DEFAULT 'active', superseded_by INTEGER REFERENCES memory_blocks(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_memory_blocks_owner_name UNIQUE(user_id,agent_id,block_name)
            )"""))
            await connection.execute(text("INSERT INTO memory_blocks(user_id,agent_id,block_name,content) VALUES ('owner','a','current_focus','preserve general')"))
            await connection.run_sync(lambda sync: migrate(sync, "upgrade"))
            assert await connection.scalar(text("SELECT content FROM memory_blocks WHERE project_id IS NULL")) == "preserve general"

        async def create():
            async with AsyncSession(engine) as db:
                await AgentMemoryService(db).ensure_focus_block("owner", "a", "p")
                await db.commit()

        await asyncio.wait_for(asyncio.gather(*(create() for _ in range(8))), timeout=20)
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM memory_blocks WHERE project_id='p'")) == 1
        with pytest.raises(RuntimeError, match="exported/reviewed"):
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: migrate(sync, "downgrade"))
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM memory_blocks WHERE project_id IS NOT NULL"))
            await connection.run_sync(lambda sync: migrate(sync, "downgrade"))
            assert await connection.scalar(text("SELECT content FROM memory_blocks WHERE agent_id='a' AND block_name='current_focus'")) == "preserve general"
            await connection.run_sync(lambda sync: migrate(sync, "upgrade"))
            assert await connection.scalar(text("SELECT count(*) FROM memory_blocks WHERE project_id IS NOT NULL")) == 0
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
