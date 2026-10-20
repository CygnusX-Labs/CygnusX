"""SQL boundary contracts for keyword memory recall."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from cygnusx.infrastructure.memory.fact_store import PostgresFactStore

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_keyword_query_keeps_partition_and_status_filters_and_escapes_wildcards() -> None:
    db = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    assert await PostgresFactStore(db).search_keywords("owner", "agent-b", ["gene_%"]) == []
    compiled = db.scalars.await_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "memory_facts.user_id =" in sql
    assert "memory_facts.agent_id =" in sql
    assert "memory_facts.status =" in sql
    values = list(compiled.params.values())
    assert "owner" in values and "agent-b" in values and "active" in values
    assert "gene/_/%" in values
    assert "ESCAPE '/'" in sql


@pytest.mark.asyncio
async def test_empty_keyword_query_does_not_read_unrelated_memories() -> None:
    db = SimpleNamespace(scalars=AsyncMock())
    assert await PostgresFactStore(db).search_keywords("owner", "agent-b", []) == []
    db.scalars.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("project", [None, "project-a", "project-b"])
async def test_vector_and_keyword_queries_apply_identical_project_boundary(project) -> None:
    db = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
        execute=AsyncMock(return_value=[]),
    )
    store = PostgresFactStore(db)
    await store.search("owner", "agent-b", [0.1], project_id=project)
    await store.search_keywords("owner", "agent-b", ["gene"], project_id=project)
    for statement in (db.execute.await_args.args[0], db.scalars.await_args.args[0]):
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert "memory_facts.project_id IS NULL" in sql
        if project:
            assert "OR memory_facts.project_id =" in sql
            assert project in compiled.params.values()
        else:
            assert "memory_facts.project_id =" not in sql


@pytest.mark.asyncio
async def test_equal_content_is_distinct_across_projects_but_profiles_remain_shared() -> None:
    from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate

    models = []
    db = SimpleNamespace(scalar=AsyncMock(return_value=None), add=models.append, flush=AsyncMock())
    store = PostgresFactStore(db)
    for project in ("project-a", "project-b"):
        await store.insert(MemoryFactCreate(
            user_id="owner", agent_id="agent-b", scope="project", content="same", project_id=project
        ))
    assert models[0].content_hash != models[1].content_hash
    assert [model.project_id for model in models] == ["project-a", "project-b"]
    await store.insert(MemoryFactCreate(
        user_id="owner", agent_id="agent-b", scope="profile", content="same", project_id="project-a"
    ))
    assert models[-1].project_id is None
    assert models[-1].agent_id == ""


@pytest.mark.asyncio
async def test_recent_episode_query_is_active_and_exactly_project_scoped() -> None:
    db = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    await PostgresFactStore(db).recent_episodes("owner", "agent-b", project_id="project-a")
    query = db.scalars.await_args.args[0].compile(dialect=postgresql.dialect())
    assert {"owner", "agent-b", "project-a", "active", "episode"}.issubset(set(query.params.values()))
    assert "memory_facts.project_id IS NULL" not in str(query)
    assert "ORDER BY memory_facts.created_at DESC" in str(query)


@pytest.mark.asyncio
async def test_recall_counter_update_is_one_batch_owned_active_and_deduplicated() -> None:
    db = SimpleNamespace(execute=AsyncMock())
    await PostgresFactStore(db).touch_recalled([1, 1, 2], user_id="owner")
    db.execute.assert_awaited_once()
    query = db.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "memory_facts.recall_count +" in str(query)
    assert "owner" in query.params.values() and "active" in query.params.values()
    assert [1, 2] in query.params.values()


@pytest.mark.asyncio
async def test_arbitration_candidates_are_bounded_owned_active_and_scope_partitioned() -> None:
    db = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    await PostgresFactStore(db).settlement_candidates("owner", "agent-b", project_id="p", limit=30)
    query = db.scalars.await_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(query)
    assert "memory_facts.user_id =" in sql and "memory_facts.status =" in sql
    assert "memory_facts.project_id IS NULL" in sql and "memory_facts.project_id =" in sql
    assert {"owner", "agent-b", "active", "p", 30}.issubset(
        {value for value in query.params.values() if not isinstance(value, list)}
    )
    assert ["profile", "preference"] in query.params.values()
    assert ["project", "summary"] in query.params.values()


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [True, False])
async def test_supersede_requires_active_target_in_same_partition(monkeypatch, stale) -> None:
    from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate

    db = SimpleNamespace(scalar=AsyncMock(return_value=None if stale else 7))
    store = PostgresFactStore(db)
    monkeypatch.setattr(store, "insert", AsyncMock(return_value=SimpleNamespace(
        id=8, status="active", agent_id="agent-b", project_id="p",
    )))
    new = MemoryFactCreate(user_id="owner", agent_id="agent-b", project_id="p",
                           scope="project", content="updated")
    if stale:
        with pytest.raises(ValueError, match="target changed"):
            await store.supersede(7, new)
    else:
        assert (await store.supersede(7, new)).id == 8
    query = db.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
    for column in ("user_id", "agent_id", "project_id", "scope", "status"):
        assert f"memory_facts.{column} =" in str(query)
    assert "RETURNING memory_facts.id" in str(query)


@pytest.mark.asyncio
async def test_explicit_recreation_rejects_changed_inactive_slot() -> None:
    from unittest.mock import Mock

    from cygnusx.core.exceptions import BusinessError
    from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate

    db = SimpleNamespace(
        scalar=AsyncMock(side_effect=[SimpleNamespace(id=7, status="archived"), None]),
        add=Mock(), flush=AsyncMock(),
    )
    with pytest.raises(BusinessError, match="状态已变化"):
        await PostgresFactStore(db).insert(MemoryFactCreate(
            user_id="owner", agent_id="agent-b", scope="project", project_id="p", content="fact"
        ), allow_recreate=True)
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_recall_cannot_expose_mispartitioned_project_facts() -> None:
    db = SimpleNamespace(
        execute=AsyncMock(return_value=[]),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
    )
    store = PostgresFactStore(db)
    await store.search("owner", "", [0.1], project_id="p")
    await store.search_keywords("owner", "", ["project"], project_id="p")
    for statement in (db.execute.await_args.args[0], db.scalars.await_args.args[0]):
        query = statement.compile(dialect=postgresql.dialect())
        assert ["profile", "preference"] in query.params.values()
        assert "memory_facts.scope IN" in str(query)


@pytest.mark.asyncio
async def test_project_fact_write_requires_agent_partition() -> None:
    from cygnusx.core.exceptions import BusinessError
    from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate

    db = SimpleNamespace(scalar=AsyncMock())
    with pytest.raises(BusinessError, match="Agent 上下文"):
        await PostgresFactStore(db).insert(MemoryFactCreate(
            user_id="owner", agent_id="", project_id="p", scope="project", content="fact"
        ))
    db.scalar.assert_not_awaited()
