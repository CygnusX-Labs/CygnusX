"""Real SQL transaction coverage for asynchronous recall batch semantics.

SQLite exercises transaction rollback and idempotency, not pgvector compatibility.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from cygnusx.infrastructure.celery_app.tasks.memory import _record_recall_batch
from cygnusx.infrastructure.database.models.agent_memory import MemoryRecallBatchModel

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_recall_receipt_and_owned_counter_commit_and_rollback_together(monkeypatch) -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        MemoryRecallBatchModel.__table__.create(connection)
        connection.execute(text("""CREATE TABLE memory_facts (
            id INTEGER PRIMARY KEY, user_id TEXT, status TEXT,
            recall_count INTEGER NOT NULL, last_recalled_at DATETIME
        )"""))
        connection.execute(text("""INSERT INTO memory_facts VALUES
            (1,'owner','active',0,NULL), (2,'other','active',0,NULL),
            (3,'owner','archived',0,NULL)
        """))
    fail_commit = False

    @asynccontextmanager
    async def session_context():
        with engine.begin() as connection:
            class Adapter:
                async def scalar(self, statement):
                    return connection.scalar(statement)

                async def execute(self, statement):
                    return connection.execute(statement)

                async def commit(self):
                    if fail_commit:
                        raise RuntimeError("simulated transaction failure")
                    connection.commit()

            yield Adapter()

    monkeypatch.setattr(
        "cygnusx.core.config.get_settings", lambda: SimpleNamespace(memory_v2_enabled=True, memory_recall_tracking_enabled=True)
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.get_session_factory", lambda: session_context
    )
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "cygnusx.application.services.memory_runtime_policy.is_memory_runtime_enabled",
        AsyncMock(return_value=True),
    )
    assert await _record_recall_batch("owner", [1, 1, 2, 3], "batch-1") == {"status": "recorded"}
    assert await _record_recall_batch("owner", [1, 2, 3], "batch-1") == {"status": "already_recorded"}
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT recall_count FROM memory_facts ORDER BY id"
        )).scalars().all() == [1, 0, 0]
    fail_commit = True
    with pytest.raises(RuntimeError, match="simulated"):
        await _record_recall_batch("owner", [1], "batch-2")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM memory_recall_batches")) == 1
        assert connection.scalar(text("SELECT recall_count FROM memory_facts WHERE id=1")) == 1
    fail_commit = False
    assert await _record_recall_batch("owner", [1], "batch-2") == {"status": "recorded"}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT recall_count FROM memory_facts WHERE id=1")) == 2
    engine.dispose()
