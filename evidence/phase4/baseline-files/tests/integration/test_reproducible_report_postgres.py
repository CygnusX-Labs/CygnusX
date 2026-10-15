"""Opt-in PostgreSQL migration/locking tests, restricted to a disposable report_test DB.

Never reads DATABASE_URL or production Settings. With no explicit test URL these
checks are skipped, not counted as proof of live PostgreSQL concurrency.
"""

import asyncio
import importlib.util
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from cygnusx.infrastructure.celery_app.tasks.reports import task_lock_key
from cygnusx.infrastructure.database.models.report import ReportGenerationJobModel

pytestmark = pytest.mark.integration


@pytest.fixture
async def report_pg() -> AsyncIterator[AsyncEngine]:
    value = os.environ.get("CYGNUSX_REPORT_TEST_DATABASE_URL", "")
    if not value:
        pytest.skip("No authorized disposable PostgreSQL report_test database configured")
    url = make_url(value)
    if url.get_backend_name() != "postgresql" or not (url.database or "").startswith("report_test"):
        pytest.fail("Report DB tests require an explicitly named disposable report_test database")
    schema = "report_test_" + uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    engine = create_async_engine(
        url, poolclass=NullPool, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE reports (id uuid PRIMARY KEY, user_id uuid NOT NULL)")
            )
            await connection.execute(text("CREATE TABLE report_files (id uuid PRIMARY KEY)"))
            path = Path("alembic/versions/reportauditphase1_add_reproducible_report_tables.py")
            spec = importlib.util.spec_from_file_location("live_report_migration", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def upgrade(sync_connection: object) -> None:
                with Operations.context(MigrationContext.configure(sync_connection)):
                    module.upgrade()

            await connection.run_sync(upgrade)
        yield engine
    finally:
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()
        await admin.dispose()


@pytest.mark.asyncio
async def test_postgres_concurrent_active_job_uniqueness(report_pg: AsyncEngine) -> None:
    owner, task_id = uuid4(), uuid4()

    async def insert() -> str:
        async with AsyncSession(report_pg) as db:
            db.add(
                ReportGenerationJobModel(
                    id=uuid4(),
                    user_id=owner,
                    task_id=task_id,
                    template_version="audit-v1.0.0",
                    idempotency_key=uuid4().hex,
                    status="queued",
                    error_message="",
                    retryable=False,
                    evidence_partial=True,
                    attempt_count=0,
                )
            )
            try:
                await db.commit()
                return "created"
            except IntegrityError:
                await db.rollback()
                return "deduplicated"

    assert sorted(await asyncio.gather(insert(), insert())) == ["created", "deduplicated"]


@pytest.mark.asyncio
async def test_postgres_task_lock_survives_status_commit_and_releases(
    report_pg: AsyncEngine,
) -> None:
    key = task_lock_key(uuid4())
    async with report_pg.connect() as first, report_pg.connect() as second:
        assert await first.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        await first.commit()
        assert not await second.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        await first.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
        await first.commit()
        assert await second.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        await second.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
        await second.commit()


@pytest.mark.asyncio
async def test_postgres_snapshot_trigger_and_published_uniqueness(report_pg: AsyncEngine) -> None:
    owner, task_id, snapshot_id = uuid4(), uuid4(), uuid4()
    async with report_pg.begin() as connection:
        await connection.execute(
            text("""
            INSERT INTO report_snapshots
                (id,user_id,task_id,schema_version,snapshot_digest,payload,captured_at)
            VALUES (:id,:owner,:task,'v1',:digest,'{}',now())
        """),
            {"id": snapshot_id, "owner": owner, "task": task_id, "digest": "a" * 64},
        )
    async with report_pg.connect() as connection:
        with pytest.raises(DBAPIError):
            await connection.execute(
                text("UPDATE report_snapshots SET payload = '{}' WHERE id = :id"),
                {"id": snapshot_id},
            )
        await connection.rollback()

    async def publish() -> str:
        async with report_pg.begin() as connection:
            try:
                await connection.execute(
                    text("""
                    INSERT INTO reports (id,user_id,snapshot_id,template_version)
                    VALUES (:id,:owner,:snapshot,'audit-v1.0.0')
                """),
                    {"id": uuid4(), "owner": owner, "snapshot": snapshot_id},
                )
                return "published"
            except IntegrityError:
                await connection.rollback()
                return "deduplicated"

    assert sorted(await asyncio.gather(publish(), publish())) == ["deduplicated", "published"]
