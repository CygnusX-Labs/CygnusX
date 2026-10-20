"""Opt-in vector/model SQL acceptance in a dedicated disposable pgvector DB.

This exercises real pgvector and captures a small synthetic EXPLAIN. It is not a
production-sized HNSW latency benchmark, Provider test or snapshot rehearsal.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.application.services.memory_embedding_service import MemoryEmbeddingService
from cygnusx.infrastructure.database.models.agent_memory import MemoryFactModel
from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate, PostgresFactStore

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_pgvector_model_filter_lexical_backfill_and_explain(monkeypatch, record_property):
    dsn = os.environ.get("MEMORY_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("No dedicated MEMORY_TEST_DATABASE_URL; actual vector acceptance pending")
    url = make_url(dsn)
    if url.get_backend_name() != "postgresql" or not (url.database or "").startswith(
        "memory_acceptance_test"
    ):
        pytest.fail("Dedicated memory_acceptance_test PostgreSQL required")
    schema = "memory_model_" + uuid4().hex
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        connect_args={
            "server_settings": {"search_path": f"{schema},public"},
        },
    )
    settings = SimpleNamespace(
        agent_memory_embedding_model="new",
        memory_embedding_model_filter_enabled=True,
        memory_hybrid_retrieval_enabled=False,
    )
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "cygnusx.application.services.memory_embedding_service.get_settings", lambda: settings
    )
    vector = [1.0, *([0.0] * 1023)]
    try:
        async with engine.begin() as connection:
            version = await connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            )
            if not version:
                pytest.skip("pgvector extension must already be installed in the disposable DB")
            record_property("pgvector_version", version)
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.run_sync(MemoryFactModel.__table__.create)
        async with AsyncSession(engine, expire_on_commit=False) as db:
            store = PostgresFactStore(db)
            current = await store.insert(
                MemoryFactCreate(
                    user_id="synthetic-user",
                    agent_id="a",
                    project_id="p",
                    scope="project",
                    content="GRCh38 current",
                    embedding=vector,
                    embedding_model="new",
                )
            )
            old = await store.insert(
                MemoryFactCreate(
                    user_id="synthetic-user",
                    agent_id="a",
                    project_id="p",
                    scope="project",
                    content="GRCh38 previous",
                    embedding=vector,
                    embedding_model="old",
                )
            )
            await db.commit()
            found = await store.search(
                "synthetic-user", "a", vector, project_id="p", embedding_model="new"
            )
            assert [fact.id for fact in found] == [current.id]
            merged = await AgentMemoryService(db)._search_facts_merged(
                "synthetic-user", "a", vector, limit=10, query="GRCh38", project_id="p"
            )
            assert {fact.id for fact in merged} == {current.id, old.id}
            vectors, keywords = await store.hybrid_candidates(
                "synthetic-user",
                "a",
                vector,
                ["grch38"],
                project_id="p",
                embedding_model="new",
                min_similarity=0.5,
                vector_limit=1,
                keyword_limit=1,
            )
            assert [fact.id for fact in vectors] == [current.id]
            assert [fact.id for fact in keywords] == [old.id]
            maintenance = MemoryEmbeddingService(
                db, embedding_client=SimpleNamespace(embeddings=AsyncMock(return_value=vector))
            )
            assert (await maintenance.backfill(mode="mismatch"))["pending"] == 1
            result = await maintenance.backfill(mode="mismatch", dry_run=False)
            await db.commit()
            assert result["updated"] == 1 and result["after"]["pending"] == 0
            assert (await maintenance.backfill(mode="mismatch", dry_run=False))["updated"] == 0
            plan = await db.scalar(
                text("""EXPLAIN (FORMAT JSON)
                SELECT id FROM memory_facts
                WHERE user_id='synthetic-user' AND agent_id='a' AND status='active'
                  AND (project_id IS NULL OR project_id='p')
                  AND embedding IS NOT NULL AND embedding_model='new'
                ORDER BY embedding <=> CAST(:query AS vector) LIMIT 10"""),
                {"query": json.dumps(vector)},
            )
            record_property("synthetic_filtered_vector_plan", str(plan))
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
