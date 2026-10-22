"""Real SQL model filtering and bounded backfill, without a live Provider or PG index."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.application.services.memory_embedding_service import MemoryEmbeddingService
from cygnusx.infrastructure.database.models.agent_memory import AgentMemoryModel, MemoryFactModel
from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate, PostgresFactStore

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
_VECTOR = [1.0, *([0.0] * 1023)]
_OTHER_VECTOR = [0.0, 1.0, *([0.0] * 1022)]


async def _fact(db, content, *, model="old-model", vector=_VECTOR, owner="owner"):
    return await PostgresFactStore(db).insert(
        MemoryFactCreate(
            user_id=owner,
            agent_id="a",
            project_id="p",
            scope="project",
            content=content,
            embedding=vector,
            embedding_model=model,
        )
    )


async def test_same_dimension_old_models_are_excluded_from_vectors_but_keep_lexical_visibility(
    embedding_database,
    embedding_settings,
):
    session, db = embedding_database
    compatible = await _fact(db, "GRCh38 current", model="new-model")
    old = await _fact(db, "GRCh38 previous")
    missing = await _fact(db, "GRCh38 missing", vector=None)
    await _fact(db, "GRCh38 foreign", owner="other", model="new-model")
    hidden = await _fact(db, "GRCh38 archived", model="new-model")
    session.get(MemoryFactModel, hidden.id).status = "archived"
    # Simulate historical unknown-model vectors, which new writes can no longer produce.
    unknown = await _fact(db, "GRCh38 unknown", model="new-model")
    session.get(MemoryFactModel, unknown.id).embedding_model = None
    session.commit()
    store = PostgresFactStore(db)
    found = await store.search("owner", "a", _VECTOR, project_id="p", embedding_model="new-model")
    assert {fact.id for fact in found} == {compatible.id}
    assert {fact.id for fact in await store.search("owner", "a", _VECTOR, project_id="p")} == {
        compatible.id,
        old.id,
        unknown.id,
    }
    service = AgentMemoryService(db)
    merged = await service._search_facts_merged(
        "owner", "a", _VECTOR, limit=10, query="GRCh38", project_id="p"
    )
    assert {fact.id for fact in merged} == {compatible.id, old.id, missing.id, unknown.id}
    embedding_settings.memory_embedding_model_filter_enabled = False
    assert {
        fact.id
        for fact in await service._search_facts_merged(
            "owner", "a", _VECTOR, limit=10, query="GRCh38", project_id="p"
        )
    } == {compatible.id, old.id, unknown.id}


@pytest.mark.parametrize(
    "model,vector,paired",
    [
        (None, _VECTOR, False),
        ("", _VECTOR, False),
        ("new-model", None, False),
        ("new-model", [], False),
        (" new-model ", _VECTOR, True),
    ],
)
async def test_new_fact_embedding_and_identifier_are_always_paired(
    embedding_database, model, vector, paired
):
    session, db = embedding_database
    fact = await _fact(db, "paired", model=model, vector=vector)
    session.commit()
    row = session.get(MemoryFactModel, fact.id)
    assert (row.embedding is not None) is paired
    assert row.embedding_model == ("new-model" if paired else None)


@pytest.mark.parametrize("storage", ["facts", "legacy"])
async def test_backfill_dry_run_then_model_rebuild_coverage_and_replay(
    embedding_database,
    embedding_settings,
    storage,
):
    session, db = embedding_database
    if storage == "facts":
        old = await _fact(db, "old")
        missing = await _fact(db, "missing", vector=None)
        current = await _fact(db, "current", model="new-model")
        table = MemoryFactModel
    else:
        table = AgentMemoryModel
        values = []
        for content, model, vector in [
            ("old", "old-model", _VECTOR),
            ("missing", None, None),
            ("current", "new-model", _VECTOR),
        ]:
            row = table(
                id=uuid4(),
                user_id="owner",
                agent_id="a",
                project_id="p",
                scope="project",
                content=content,
                keywords=[],
                embedding=vector,
                embedding_model=model,
                status="active",
                confidence=1,
                use_count=0,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(row)
            values.append(row)
        old, missing, current = values
    session.commit()
    client = SimpleNamespace(embeddings=AsyncMock(side_effect=[_OTHER_VECTOR, []]))
    service = MemoryEmbeddingService(db, storage=storage, embedding_client=client)
    report = await service.backfill(2, mode="mismatch", dry_run=True)
    assert report["pending"] == 2 and report["before"]["active"] == 3
    assert report["before"]["coverage"] == pytest.approx(1 / 3)
    client.embeddings.assert_not_awaited()
    result = await service.backfill(2, mode="mismatch", dry_run=False)
    session.commit()
    session.expire_all()
    assert result["updated"] == 1 and result["failed"] == 1
    assert result["after"]["compatible"] == 2
    assert result["after"]["pending"] == 1
    unchanged = session.get(table, current.id)
    assert unchanged.embedding == _VECTOR and unchanged.embedding_model == "new-model"
    client.embeddings.side_effect = None
    client.embeddings.return_value = _OTHER_VECTOR
    result = await service.backfill(500, mode="mismatch", dry_run=False)
    session.commit()
    assert result["updated"] == 1 and result["after"]["pending"] == 0
    calls = client.embeddings.await_count
    assert (await service.backfill(500, mode="mismatch", dry_run=False))["updated"] == 0
    assert client.embeddings.await_count == calls
    assert all(call.kwargs["model"] == "new-model" for call in client.embeddings.await_args_list)


@pytest.mark.parametrize("mutation", ["archive", "content", "other_backfill"])
async def test_backfill_does_not_overwrite_concurrent_changes(
    embedding_database,
    embedding_settings,
    mutation,
):
    session, db = embedding_database
    source = await _fact(db, "original")
    session.commit()
    service = MemoryEmbeddingService(db)

    async def concurrent(*args, **kwargs):
        changes = (
            {"status": "archived"}
            if mutation == "archive"
            else {"content": "new text"}
            if mutation == "content"
            else {"embedding": _VECTOR, "embedding_model": "new-model"}
        )
        session.execute(
            update(MemoryFactModel).where(MemoryFactModel.id == source.id).values(**changes)
        )
        return _OTHER_VECTOR

    service.embedding_service._embed = concurrent
    result = await service.backfill(mode="mismatch", dry_run=False)
    session.commit()
    session.expire_all()
    assert result["updated"] == 0 and result["skipped"] == 1
    row = session.get(MemoryFactModel, source.id)
    if mutation == "archive":
        assert row.status == "archived" and row.embedding_model == "old-model"
    elif mutation == "content":
        assert row.content == "new text" and row.embedding_model == "old-model"
    else:
        assert row.embedding == _VECTOR and row.embedding_model == "new-model"


async def test_backfill_caps_rows_and_model_calls_at_500(embedding_database, embedding_settings):
    session, db = embedding_database
    session.execute(
        MemoryFactModel.__table__.insert(),
        [
            {
                "user_id": "owner",
                "agent_id": "a",
                "scope": "summary",
                "content": f"fact {number}",
                "content_hash": f"{number:064x}",
                "embedding": None,
                "embedding_model": None,
            }
            for number in range(501)
        ],
    )
    session.commit()
    client = SimpleNamespace(embeddings=AsyncMock(return_value=_VECTOR))
    result = await MemoryEmbeddingService(db, embedding_client=client).backfill(
        10_000, dry_run=False
    )
    session.commit()
    assert result["updated"] == result["scanned"] == client.embeddings.await_count == 500
    assert result["after"]["pending"] == 1
    assert len(session.scalars(select(MemoryFactModel)).all()) == 501


async def test_old_vector_is_kept_when_reembedding_fails_and_can_be_retried(
    embedding_database, embedding_settings
):
    session, db = embedding_database
    old = await _fact(db, "failed old model")
    session.commit()
    client = SimpleNamespace(embeddings=AsyncMock(return_value=[]))
    service = MemoryEmbeddingService(db, embedding_client=client)
    result = await service.backfill(mode="mismatch", dry_run=False)
    session.commit()
    session.expire_all()
    assert result["failed"] == 1 and result["after"]["pending"] == 1
    assert session.get(MemoryFactModel, old.id).embedding == _VECTOR
    assert session.get(MemoryFactModel, old.id).embedding_model == "old-model"
    client.embeddings.return_value = _OTHER_VECTOR
    assert (await service.backfill(mode="mismatch", dry_run=False))["updated"] == 1


async def test_empty_config_disables_reembedding_without_provider_or_sql(embedding_settings):
    embedding_settings.agent_memory_embedding_model = ""
    db = SimpleNamespace(execute=AsyncMock())
    client = SimpleNamespace(embeddings=AsyncMock())
    result = await MemoryEmbeddingService(db, embedding_client=client).backfill(
        mode="mismatch", dry_run=False
    )
    assert result["status"] == "disabled"
    db.execute.assert_not_awaited()
    client.embeddings.assert_not_awaited()


async def test_legacy_rank_never_compares_old_model_in_fallback(embedding_settings):
    embedding_settings.memory_embedding_model_filter_enabled = True
    now = datetime.now()
    current = AgentMemoryModel(
        id=uuid4(),
        user_id="owner",
        scope="summary",
        content="current",
        use_count=0,
        updated_at=now,
        embedding=_OTHER_VECTOR,
        embedding_model="new-model",
    )
    old = AgentMemoryModel(
        id=uuid4(),
        user_id="owner",
        scope="summary",
        content="GRCh38 old",
        use_count=0,
        updated_at=now,
        embedding=_VECTOR,
        embedding_model="old-model",
    )
    db = SimpleNamespace(scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
    service = AgentMemoryService(db, SimpleNamespace(embeddings=AsyncMock(return_value=_VECTOR)))
    ranked = await service._semantic_rank([current, old], "GRCh38", ["grch38"], 2)
    assert ranked[0] is old  # Lexical score; its perfect old-model cosine must not count.
    ranked = await service._semantic_rank([current, old], "unrelated", [], 2)
    assert ranked == [current, old]  # Both scores are zero; no old-model semantic boost.
    from sqlalchemy.dialects import postgresql

    statement = db.scalars.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "agent_memories.embedding_model =" in str(statement)
    assert "new-model" in statement.params.values()


async def test_rebuild_binds_model_snapshot_and_finishes_provider_calls_before_writes(
    embedding_database,
    embedding_settings,
    monkeypatch,
):
    session, db = embedding_database
    await _fact(db, "first")
    await _fact(db, "second")
    session.commit()
    original_scalar = db.scalar
    scalar = AsyncMock(side_effect=original_scalar)
    monkeypatch.setattr(db, "scalar", scalar)

    async def generate(content, *, model):
        assert model == "new-model"
        assert scalar.await_count == 0
        embedding_settings.agent_memory_embedding_model = "changed-during-call"
        return _VECTOR

    client = SimpleNamespace(embeddings=AsyncMock(side_effect=generate))
    service = MemoryEmbeddingService(db, embedding_client=client)
    result = await service.backfill(mode="mismatch", dry_run=False)
    session.commit()
    assert result["updated"] == 2 and client.embeddings.await_count == 2
    assert set(session.scalars(select(MemoryFactModel.embedding_model)).all()) == {"new-model"}


async def test_legacy_edit_without_embeddings_clears_stale_vector(embedding_settings):
    embedding_settings.agent_memory_semantic_retrieval_enabled = False
    memory = AgentMemoryModel(content="edited text", embedding=_VECTOR, embedding_model="old")
    await AgentMemoryService(SimpleNamespace())._populate_embedding(memory)
    assert memory.embedding is None and memory.embedding_model is None


async def test_explicit_inactive_backfill_preserves_states_and_active_coverage(
    embedding_database, embedding_settings
):
    session, db = embedding_database
    active = await _fact(db, "current active", model="new-model")
    archived = await _fact(db, "historic archived", vector=None)
    superseded = await _fact(db, "historic superseded", vector=None)
    session.get(MemoryFactModel, archived.id).status = "archived"
    session.get(MemoryFactModel, superseded.id).status = "superseded"
    session.commit()
    client = SimpleNamespace(embeddings=AsyncMock(return_value=_OTHER_VECTOR))
    service = MemoryEmbeddingService(db, embedding_client=client)
    assert (await service.backfill())["pending"] == 0
    statuses = ("archived", "superseded")
    plan = await service.backfill(statuses=statuses)
    assert plan["pending"] == 2 and plan["before"]["active"] == 1
    client.embeddings.assert_not_awaited()
    result = await service.backfill(statuses=statuses, dry_run=False)
    session.commit()
    session.expire_all()
    assert result["updated"] == 2 and result["remaining_pending"] == 0
    assert result["after"]["active"] == 1 and result["after"]["coverage"] == 1
    for fact, status in [(archived, "archived"), (superseded, "superseded")]:
        row = session.get(MemoryFactModel, fact.id)
        assert row.status == status and row.content == fact.content
        assert (row.user_id, row.agent_id, row.project_id) == ("owner", "a", "p")
        assert row.embedding == _OTHER_VECTOR and row.embedding_model == "new-model"
    assert session.get(MemoryFactModel, active.id).embedding == _VECTOR
    assert (await service.backfill(statuses=statuses, dry_run=False))["updated"] == 0
    assert client.embeddings.await_count == 2


@pytest.mark.parametrize("mutation", ["activate", "failure"])
async def test_inactive_backfill_skips_concurrent_status_change_and_failed_vectors(
    embedding_database, embedding_settings, mutation
):
    session, db = embedding_database
    fact = await _fact(db, "archived original", vector=None)
    session.get(MemoryFactModel, fact.id).status = "archived"
    session.commit()
    service = MemoryEmbeddingService(db)

    async def generate(*args, **kwargs):
        if mutation == "failure":
            return []
        session.execute(
            update(MemoryFactModel).where(MemoryFactModel.id == fact.id).values(status="active")
        )
        return _OTHER_VECTOR

    service.embedding_service._embed = generate
    result = await service.backfill(statuses=("archived",), dry_run=False)
    session.commit()
    session.expire_all()
    assert result["updated"] == 0
    assert result["skipped" if mutation == "activate" else "failed"] == 1
    row = session.get(MemoryFactModel, fact.id)
    assert row.status == ("active" if mutation == "activate" else "archived")
    assert row.embedding is None and row.embedding_model is None


@pytest.mark.parametrize("statuses", [(), ("deleted",)])
async def test_invalid_backfill_statuses_fail_before_sql_or_provider(embedding_settings, statuses):
    db = SimpleNamespace(execute=AsyncMock(), scalar=AsyncMock())
    client = SimpleNamespace(embeddings=AsyncMock())
    with pytest.raises(ValueError, match="statuses"):
        await MemoryEmbeddingService(db, embedding_client=client).backfill(statuses=statuses)
    db.execute.assert_not_awaited()
    db.scalar.assert_not_awaited()
    client.embeddings.assert_not_awaited()
