"""Opt-in actual migration/constraints/trigger on disposable PostgreSQL only.

PROJECT_EXPORT_TEST_DATABASE_URL must explicitly name a project_export_test database.
Not a real Worker/broker/browser acceptance test, even when this check passes.
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
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_actual_postgres_migration_uniqueness_and_frozen_scope():
    dsn = os.environ.get("PROJECT_EXPORT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("BLOCKED: no explicitly authorized disposable project_export_test PostgreSQL")
    url = make_url(dsn)
    if url.get_backend_name() != "postgresql" or not (url.database or "").startswith(
        "project_export_test"
    ):
        pytest.fail("Refusing non-test PostgreSQL database")
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"), pool_size=2, max_overflow=0
    )
    schema = "export_test_" + uuid4().hex
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for table in ("users", "projects", "file_records"):
                await connection.execute(text(f'CREATE TABLE "{table}" (id uuid PRIMARY KEY)'))
            spec = importlib.util.spec_from_file_location(
                "project_export_migration", "alembic/versions/projectdelivery01_project_exports.py"
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def upgrade(sync):
                migration.op = Operations(MigrationContext.configure(sync))
                migration.upgrade()

            await connection.run_sync(upgrade)
        owner, project, job = uuid4(), uuid4(), uuid4()
        async with engine.begin() as connection:
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await connection.execute(text("INSERT INTO users(id) VALUES (:id)"), {"id": owner})
            await connection.execute(text("INSERT INTO projects(id) VALUES (:id)"), {"id": project})
            await connection.execute(
                text(
                    "INSERT INTO project_export_jobs(id,user_id,project_id,request_key,manifest_digest,manifest,status,attempt_count,retryable) VALUES (:id,:owner,:project,'request','digest','{}','queued',0,false)"
                ),
                {"id": job, "owner": owner, "project": project},
            )
        from sqlalchemy.exc import DBAPIError, IntegrityError

        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.execute(
                    text(
                        "INSERT INTO project_export_jobs(id,user_id,project_id,request_key,manifest_digest,manifest,status,attempt_count,retryable) VALUES (:id,:owner,:project,'request-two','digest','{}','queued',0,false)"
                    ),
                    {"id": uuid4(), "owner": owner, "project": project},
                )
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.execute(
                    text("UPDATE project_export_jobs SET manifest_digest='changed' WHERE id=:id"),
                    {"id": job},
                )
        async with engine.begin() as connection:
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await connection.execute(
                text("UPDATE project_export_jobs SET status='collecting' WHERE id=:id"), {"id": job}
            )

        async def concurrent_request():
            async with engine.begin() as connection:
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                await connection.execute(
                    text("SELECT id FROM projects WHERE id=:id FOR UPDATE"), {"id": project}
                )
                existing = await connection.scalar(
                    text("SELECT id FROM project_export_jobs WHERE manifest_digest='concurrent'")
                )
                if existing:
                    return existing
                new_id = uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO project_export_jobs(id,user_id,project_id,request_key,manifest_digest,manifest,status,attempt_count,retryable) VALUES (:id,:owner,:project,:request,'concurrent','{}','queued',0,false)"
                    ),
                    {"id": new_id, "owner": owner, "project": project, "request": str(uuid4())},
                )
                return new_id

        ids = await asyncio.gather(*(concurrent_request() for _ in range(8)))
        assert len(set(ids)) == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
