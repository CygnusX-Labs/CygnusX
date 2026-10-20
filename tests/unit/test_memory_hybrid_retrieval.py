"""Bounded dual-lane SQL, rank fusion and unchanged request-level isolation/limits."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import text, update

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.core.config import Settings
from cygnusx.core.exceptions import BusinessError
from cygnusx.infrastructure.database.models.agent_memory import MemoryFactModel
from cygnusx.infrastructure.memory.fact_store import MemoryFact, MemoryFactCreate, PostgresFactStore
from cygnusx.infrastructure.memory.retrieval import reciprocal_rank_fusion

pytestmark = pytest.mark.unit
_VECTOR = [1.0, *([0.0] * 1023)]
_LOW = [-1.0, *([0.0] * 1023)]


def _candidate(identity, *, score=999.0):
    return MemoryFact(
        id=identity,
        user_id="owner",
        agent_id="a",
        scope="summary",
        content=f"fact {identity}",
        keywords=[],
        embedding=None,
        embedding_model=None,
        source_session_id=None,
        source_message_ids=[],
        confidence=1,
        status="active",
        created_at=datetime.now(UTC),
        last_recalled_at=None,
        similarity=score,
    )


async def _fact(
    db,
    content,
    *,
    agent="a",
    owner="owner",
    project="p",
    scope="summary",
    vector=_VECTOR,
    model="new-model",
):
    return await PostgresFactStore(db).insert(
        MemoryFactCreate(
            user_id=owner,
            agent_id=agent,
            project_id=project,
            scope=scope,
            content=content,
            embedding=vector,
            embedding_model=model,
        )
    )


def test_rrf_uses_unique_ranks_and_constant_normalization_without_mutating_raw_scores():
    a, b, c = [_candidate(number) for number in range(3)]
    result = reciprocal_rank_fusion([a, a, b], [b, c], k=60)
    assert [fact.id for fact in result] == [b.id, a.id, c.id]
    assert result[0].similarity == pytest.approx((1 / 61 + 1 / 62) / (2 / 61))
    assert result[1].similarity == 0.5
    assert all(0 < fact.similarity <= 1 for fact in result)
    assert a.similarity == b.similarity == c.similarity == 999.0
    assert reciprocal_rank_fusion([], [a])[0].similarity == 0.5
    assert reciprocal_rank_fusion([], []) == []


@pytest.mark.asyncio
async def test_single_sql_fetches_both_lanes_with_floor_model_and_partition_filters(
    embedding_database,
    hybrid_settings,
    monkeypatch,
):
    session, db = embedding_database
    high = await _fact(db, "semantic candidate")
    keyword = await _fact(db, "GSE123 exact keyword", vector=_LOW, model="old-model")
    both = await _fact(db, "GSE123 in both lanes")
    await _fact(db, "irrelevant below floor", vector=_LOW)
    await _fact(db, "GSE123 wrong project", project="q")
    await _fact(db, "GSE123 wrong agent", agent="b")
    await _fact(db, "GSE123 wrong owner", owner="other")
    archived = await _fact(db, "GSE123 archived")
    session.get(MemoryFactModel, archived.id).status = "archived"
    session.commit()
    execute = AsyncMock(side_effect=db.execute)
    monkeypatch.setattr(db, "execute", execute)
    vectors, keywords = await PostgresFactStore(db).hybrid_candidates(
        "owner",
        "a",
        _VECTOR,
        ["gse123"],
        project_id="p",
        embedding_model="new-model",
        min_similarity=0.5,
    )
    assert {fact.id for fact in vectors} == {high.id, both.id}
    assert {fact.id for fact in keywords} == {keyword.id, both.id}
    execute.assert_awaited_once()
    assert "UNION ALL" in str(execute.await_args.args[0])
    fused = reciprocal_rank_fusion(vectors, keywords)
    assert fused[0].id == both.id
    assert len({fact.id for fact in fused}) == len(fused) == 3


@pytest.mark.asyncio
async def test_each_lane_is_independently_bounded_and_empty_terms_do_not_recall_keywords(
    embedding_database,
    hybrid_settings,
):
    session, db = embedding_database
    for index in range(8):
        await _fact(db, f"GSE123 candidate {index}")
    session.commit()
    store = PostgresFactStore(db)
    vectors, keywords = await store.hybrid_candidates(
        "owner",
        "a",
        _VECTOR,
        ["gse123"],
        embedding_model="new-model",
        min_similarity=0.5,
        vector_limit=2,
        keyword_limit=3,
        project_id="p",
    )
    assert len(vectors) == 2 and len(keywords) == 3
    assert len(reciprocal_rank_fusion(vectors, keywords)) <= 5
    vectors, keywords = await store.hybrid_candidates(
        "owner",
        "a",
        _VECTOR,
        [],
        embedding_model="new-model",
        min_similarity=0.5,
        vector_limit=2,
        project_id="p",
    )
    assert len(vectors) == 2 and keywords == []


@pytest.mark.asyncio
async def test_tool_and_prompt_still_respect_limits_and_shared_ties(
    embedding_database,
    hybrid_settings,
):
    session, db = embedding_database
    own = await _fact(db, "GSE123 own")
    shared = await _fact(db, "GSE123 shared", agent="", scope="preference")
    now = datetime.now(UTC)
    session.execute(update(MemoryFactModel).values(created_at=now))
    session.commit()
    service = AgentMemoryService(db, SimpleNamespace(embeddings=AsyncMock(return_value=_VECTOR)))
    result = await service.search_memory(
        user_id="owner", agent_id="a", project_id="p", query="GSE123", limit=1
    )
    assert [item["id"] for item in result["memories"]] == [str(shared.id)]
    assert own.id != shared.id
    for index in range(15):
        await _fact(db, f"GSE123 more {index}")
    session.commit()
    assert (
        len(
            (
                await service.search_memory(
                    user_id="owner", agent_id="a", project_id="p", query="GSE123", limit=999
                )
            )["memories"]
        )
        == 10
    )
    prompt = await service.build_prompt_context_v2("owner", "a", "GSE123", project_id="p")
    assert prompt.count("（记于 ") == 5


@pytest.mark.asyncio
async def test_no_vector_or_model_uses_existing_keyword_scores(embedding_database, hybrid_settings):
    session, db = embedding_database
    fact = await _fact(db, "GSE123 keyword", vector=None)
    session.commit()
    service = AgentMemoryService(db)
    hybrid_settings.agent_memory_embedding_model = ""
    found = await service._search_facts_merged(
        "owner", "a", [], limit=5, query="GSE123", project_id="p"
    )
    assert [item.id for item in found] == [fact.id] and found[0].similarity == 1.0


@pytest.mark.asyncio
async def test_failed_hybrid_sql_savepoint_keeps_outer_state_and_falls_back_without_private_logs(
    embedding_database,
    hybrid_settings,
    monkeypatch,
):
    session, db = embedding_database
    fact = await _fact(db, "GSE123 original")
    session.commit()

    async def fail(*args, **kwargs):
        await db.execute(
            update(MemoryFactModel).where(MemoryFactModel.id == fact.id).values(content="tampered")
        )
        await db.execute(text("SELECT unavailable_column FROM memory_facts"))

    monkeypatch.setattr(PostgresFactStore, "hybrid_candidates", fail)
    warning = Mock()
    monkeypatch.setattr("cygnusx.application.services.agent_memory_service.logger.warning", warning)
    service = AgentMemoryService(db)
    found = await service._search_facts_merged(
        "owner", "a", _VECTOR, limit=5, query="GSE123", project_id="p"
    )
    session.commit()
    assert [item.id for item in found] == [fact.id]
    session.expire_all()
    assert session.get(MemoryFactModel, fact.id).content == "GSE123 original"
    assert "GSE123" not in str(warning.call_args) and "unavailable_column" not in str(
        warning.call_args
    )


@pytest.mark.parametrize("floor,filter_on", [(None, True), (0.3, False)])
@pytest.mark.asyncio
async def test_runtime_config_mutation_cannot_bypass_calibration_and_model_filter_gate(
    embedding_database,
    hybrid_settings,
    floor,
    filter_on,
):
    _, db = embedding_database
    hybrid_settings.memory_hybrid_min_similarity = floor
    hybrid_settings.memory_embedding_model_filter_enabled = filter_on
    with pytest.raises(BusinessError, match="基线"):
        await AgentMemoryService(db)._search_facts_merged(
            "owner", "a", _VECTOR, limit=5, query="GSE123"
        )


@pytest.mark.parametrize(
    "floor,filter_on", [(None, True), (0.3, False), (float("nan"), True), (2.0, True)]
)
def test_settings_reject_uncalibrated_hybrid_without_echoing_entire_secret_input(floor, filter_on):
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            memory_hybrid_retrieval_enabled=True,
            memory_embedding_model_filter_enabled=filter_on,
            agent_memory_embedding_model="new-model",
            memory_hybrid_min_similarity=floor,
            openai_api_key="synthetic-do-not-echo",
        )
    assert "synthetic-do-not-echo" not in str(error.value)


def test_settings_allow_keyword_only_and_blank_optional_floor(monkeypatch):
    monkeypatch.setenv("MEMORY_HYBRID_MIN_SIMILARITY", "")
    settings = Settings(
        _env_file=None,
        memory_hybrid_retrieval_enabled=True,
        agent_memory_embedding_model="",
        memory_embedding_model_filter_enabled=False,
    )
    assert settings.memory_hybrid_min_similarity is None
    calibrated = Settings(
        _env_file=None,
        memory_hybrid_retrieval_enabled=True,
        agent_memory_embedding_model="new-model",
        memory_embedding_model_filter_enabled=True,
        memory_hybrid_min_similarity=0.3,
    )
    assert calibrated.memory_hybrid_min_similarity == 0.3
