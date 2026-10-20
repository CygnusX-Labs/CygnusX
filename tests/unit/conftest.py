"""Disposable SQL adapters for memory lifecycle tests; no live service connections."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from cygnusx.infrastructure.database.models.agent_memory import (
    MemoryBlockModel,
    MemoryConsolidationBudgetModel,
)


@pytest.fixture
def fact_database():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        MemoryBlockModel.__table__.create(connection)
        connection.execute(
            text("""CREATE TABLE memory_facts (
            id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, agent_id TEXT NOT NULL,
            project_id TEXT, scope TEXT NOT NULL, content TEXT NOT NULL,
            content_hash TEXT NOT NULL, keywords JSON, embedding VECTOR,
            embedding_model TEXT, source_session_id TEXT, source_message_ids JSON,
            confidence FLOAT NOT NULL DEFAULT 0.8, importance INTEGER NOT NULL DEFAULT 5,
            recall_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active',
            superseded_by INTEGER, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_recalled_at DATETIME,
            UNIQUE(user_id, agent_id, content_hash)
        )""")
        )
    with Session(engine, expire_on_commit=False) as session:

        async def scalar(statement):
            return session.scalar(statement)

        async def execute(statement):
            return session.execute(statement)

        async def flush():
            session.flush()

        async def commit():
            session.commit()

        async def rollback():
            session.rollback()

        async def scalars(statement):
            return session.scalars(statement)

        @asynccontextmanager
        async def begin_nested():
            with session.begin_nested():
                yield

        yield (
            session,
            SimpleNamespace(
                scalar=scalar,
                scalars=scalars,
                execute=execute,
                flush=flush,
                add=session.add,
                begin_nested=begin_nested,
                commit=commit,
                rollback=rollback,
            ),
        )
    engine.dispose()


@pytest.fixture
def consolidation_database(fact_database, monkeypatch):
    session, adapter = fact_database
    MemoryConsolidationBudgetModel.__table__.create(session.connection())
    session.execute(
        text("""CREATE TABLE memory_consolidation_runs (
        run_key TEXT PRIMARY KEY, kind TEXT NOT NULL, week TEXT NOT NULL,
        user_id TEXT NOT NULL, agent_id TEXT NOT NULL, project_id TEXT,
        watermark INTEGER NOT NULL, decisions JSON NOT NULL, created_at DATETIME NOT NULL,
        rolled_back_at DATETIME
    )""")
    )
    session.commit()
    settings = SimpleNamespace(
        memory_consolidation_enabled=True,
        memory_consolidation_max_calls=2,
        memory_consolidation_max_groups=20,
        memory_consolidation_lookback_days=30,
        memory_consolidation_candidate_limit=30,
        memory_consolidation_max_chars=18000,
        memory_consolidation_min_episodes=2,
        memory_consolidation_timeout_seconds=1,
        memory_cold_after_days=90,
        memory_cold_max_importance=3,
        memory_cold_batch_limit=500,
        memory_extraction_model="test-model",
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.memory.consolidation.get_settings", lambda: settings
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.memory.consolidation.is_memory_runtime_enabled",
        AsyncMock(return_value=True),
    )
    return session, adapter, settings


@pytest.fixture
def project_focus_settings(monkeypatch):
    settings = SimpleNamespace(
        agent_memory_embedding_model="current-model",
        memory_embedding_model_filter_enabled=False,
        memory_hybrid_retrieval_enabled=False,
        memory_v2_enabled=True, memory_focus_per_project_enabled=True,
        memory_recall_tracking_enabled=False, memory_prompt_max_bytes=6000,
        memory_prompt_blocks_max_bytes=2800, memory_prompt_episode_max_bytes=3200,
        memory_fact_time_decay_lambda=0.02, memory_importance_weight=0.5,
        memory_recall_weight=0.25, memory_recall_boost_scale=20,
    )
    monkeypatch.setattr("cygnusx.application.services.agent_memory_service.get_settings", lambda: settings)
    return settings


@pytest.fixture
def residual_settings(project_focus_settings, monkeypatch):
    settings = project_focus_settings
    settings.memory_forget_residual_scan_enabled = True
    settings.memory_forget_residual_limit = 20
    monkeypatch.setattr("cygnusx.application.services.memory_residual_service.get_settings", lambda: settings)
    return settings


@pytest.fixture
def embedding_settings(project_focus_settings, monkeypatch):
    settings = project_focus_settings
    settings.memory_embedding_model_filter_enabled = True
    settings.memory_embedding_coverage_enabled = True
    settings.agent_memory_embedding_model = "new-model"
    monkeypatch.setattr("cygnusx.application.services.memory_embedding_service.get_settings", lambda: settings)
    return settings


@pytest.fixture
def embedding_database(fact_database, monkeypatch):
    """Execute model predicates in SQLite with a test-only cosine SQL function.

    This tests actual WHERE/UPDATE behavior, not PostgreSQL HNSW implementation.
    """
    import json
    import math

    from sqlalchemy import func, literal

    from cygnusx.infrastructure.database.vector import Vector

    session, adapter = fact_database
    session.execute(text("""CREATE TABLE agent_memories (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, agent_id TEXT,
        scope TEXT NOT NULL, content TEXT NOT NULL, keywords JSON NOT NULL,
        embedding VECTOR, embedding_model TEXT, source_session TEXT,
        confidence FLOAT NOT NULL, use_count INTEGER NOT NULL, last_used_at DATETIME,
        status TEXT NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )"""))

    def distance(left, right):
        if left is None or right is None:
            return None
        a, b = json.loads(left), json.loads(right)
        scale = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
        return 1 - sum(x * y for x, y in zip(a, b, strict=True)) / scale if scale else 1.0

    session.connection().connection.driver_connection.create_function("memory_test_cosine", 2, distance)
    monkeypatch.setattr(Vector.comparator_factory, "cosine_distance",
                        lambda self, value: func.memory_test_cosine(self.expr, literal(value, type_=Vector(1024))))
    yield session, adapter


@pytest.fixture
def hybrid_settings(embedding_settings):
    # Synthetic test floor only; this is not a production calibration result.
    settings = embedding_settings
    settings.memory_hybrid_retrieval_enabled = True
    settings.memory_hybrid_vector_limit = 20
    settings.memory_hybrid_keyword_limit = 20
    settings.memory_hybrid_rrf_k = 60
    settings.memory_hybrid_min_similarity = 0.5
    return settings
