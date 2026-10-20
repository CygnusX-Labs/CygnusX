"""SQL-backed consolidation budgets, lifecycle, evidence and rollback contracts."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from cygnusx.core.exceptions import ConflictError
from cygnusx.infrastructure.database.models.agent_memory import (
    MemoryBlockModel,
    MemoryConsolidationBudgetModel,
    MemoryConsolidationRunModel,
    MemoryFactModel,
)
from cygnusx.infrastructure.memory.consolidation import MemoryConsolidator
from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate, PostgresFactStore

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _response(plan):
    return {"choices": [{"message": {"content": json.dumps(plan)}}]}


async def _fact(
    adapter, content, *, user="owner", agent="a", scope="project", source=None, importance=5
):
    return await PostgresFactStore(adapter).insert(
        MemoryFactCreate(
            user_id=user,
            agent_id=agent,
            scope=scope,
            content=content,
            source_session_id=source,
            importance=importance,
        )
    )


async def test_consolidation_supersedes_duplicates_and_replay_does_not_call_model(
    consolidation_database,
):
    session, adapter, _ = consolidation_database
    first = await _fact(adapter, "图用英文", agent="", scope="preference")
    second = await _fact(adapter, "图中使用英文", agent="", scope="preference")
    session.commit()
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=_response(
                {
                    "pairs": [{"old_id": first.id, "new_id": second.id, "relation": "duplicate"}],
                    "blocks": {},
                }
            )
        )
    )
    worker = MemoryConsolidator(adapter, provider)
    result = await worker.run()
    assert result["groups"] == 1 and result["calls"] == 1 and result["failed"] == 0
    assert session.get(MemoryFactModel, first.id).superseded_by == second.id
    assert session.get(MemoryFactModel, first.id).status == "superseded"
    assert (await worker.run())["calls"] == 0
    provider.chat.assert_awaited_once()
    assert session.scalars(select(MemoryConsolidationBudgetModel)).one().calls == 1


async def test_weekly_call_cap_survives_reruns_and_counts_failure(consolidation_database):
    session, adapter, settings = consolidation_database
    await _fact(adapter, "fact")
    session.commit()
    provider = SimpleNamespace(chat=AsyncMock(side_effect=RuntimeError("provider down")))
    worker = MemoryConsolidator(adapter, provider)
    assert (await worker.run())["failed"] == 1
    assert (await worker.run())["failed"] == 1
    assert (await worker.run())["calls"] == 0
    assert provider.chat.await_count == settings.memory_consolidation_max_calls == 2
    assert session.scalars(select(MemoryConsolidationBudgetModel)).one().calls == 2
    assert not session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "group")
    ).all()


async def test_repeated_episode_evidence_distills_shared_profile(consolidation_database):
    session, adapter, _ = consolidation_database
    episodes = [
        await _fact(adapter, content, scope="episode", source=source)
        for content, source in [
            ("用户连续研究 RNA", "session-1"),
            ("用户明确持续 RNA 研究", "session-2"),
        ]
    ]
    session.commit()
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=_response(
                {
                    "pairs": [],
                    "blocks": {
                        "profile": {
                            "content": "用户研究 RNA",
                            "source_ids": [f.id for f in episodes],
                        }
                    },
                }
            )
        )
    )
    result = await MemoryConsolidator(adapter, provider).run()
    assert result["groups"] == 1 and result["failed"] == 0
    block = session.scalars(
        select(MemoryBlockModel).where(MemoryBlockModel.block_name == "profile")
    ).one()
    assert block.agent_id == "" and block.content == "用户研究 RNA" and block.version == 2
    receipt = session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "group")
    ).one()
    assert receipt.decisions["source_ids"] == [f.id for f in episodes]


async def test_manually_cleared_profile_is_not_repopulated(consolidation_database):
    session, adapter, _ = consolidation_database
    source = await _fact(adapter, "用户研究 RNA", agent="", scope="profile")
    session.add(
        MemoryBlockModel(user_id="owner", agent_id="", block_name="profile", content="", version=3)
    )
    session.commit()
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=_response(
                {
                    "pairs": [],
                    "blocks": {"profile": {"content": "用户研究 RNA", "source_ids": [source.id]}},
                }
            )
        )
    )
    result = await MemoryConsolidator(adapter, provider).run()
    assert result["failed"] == 1
    block = session.scalars(select(MemoryBlockModel)).one()
    assert block.content == "" and block.version == 3
    assert not session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "group")
    ).all()


async def test_cold_archive_preserves_important_recalled_and_personal_facts(consolidation_database):
    session, adapter, _ = consolidation_database
    low = await _fact(adapter, "old low importance", importance=2)
    important = await _fact(adapter, "old important", importance=9)
    recalled = await _fact(adapter, "old recalled", importance=2)
    personal = await _fact(adapter, "old personal", agent="", scope="preference", importance=2)
    for item in (low, important, recalled, personal):
        session.get(MemoryFactModel, item.id).created_at = datetime.now(UTC) - timedelta(days=100)
    session.get(MemoryFactModel, recalled.id).recall_count = 1
    session.get(MemoryFactModel, recalled.id).last_recalled_at = datetime.now(UTC)
    session.commit()
    provider = SimpleNamespace(chat=AsyncMock())
    result = await MemoryConsolidator(adapter, provider).run()
    assert result["archived"] == 1
    assert session.get(MemoryFactModel, low.id).status == "archived"
    for item in (important, recalled, personal):
        assert session.get(MemoryFactModel, item.id).status == "active"
    provider.chat.assert_not_awaited()
    assert len(session.scalars(select(MemoryFactModel)).all()) == 4


async def test_partial_batches_advance_only_processed_watermark(consolidation_database):
    session, adapter, settings = consolidation_database
    settings.memory_consolidation_candidate_limit = 1
    facts = [await _fact(adapter, str(index)) for index in range(3)]
    session.commit()
    provider = SimpleNamespace(chat=AsyncMock(return_value=_response({"pairs": [], "blocks": {}})))
    worker = MemoryConsolidator(adapter, provider)
    assert (await worker.run())["groups"] == 1
    receipt = session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "group")
    ).one()
    assert receipt.watermark == facts[0].id
    assert (await worker.run())["groups"] == 1
    assert max(session.scalars(select(MemoryConsolidationRunModel.watermark)).all()) == facts[1].id


async def test_cross_user_reference_rejected_without_mutation(consolidation_database):
    session, adapter, _ = consolidation_database
    owned = await _fact(adapter, "owned")
    foreign = await _fact(adapter, "foreign", user="other")
    session.commit()
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=_response(
                {
                    "pairs": [{"old_id": owned.id, "new_id": foreign.id, "relation": "duplicate"}],
                    "blocks": {},
                }
            )
        )
    )
    result = await MemoryConsolidator(adapter, provider).run()
    assert result["failed"] == 2 and result["groups"] == 0
    assert all(fact.status == "active" for fact in session.scalars(select(MemoryFactModel)))


async def test_withdrawn_evidence_rolls_back_receipt(consolidation_database):
    session, adapter, _ = consolidation_database
    fact = await _fact(adapter, "withdrawn")
    session.commit()

    async def withdraw(*args, **kwargs):
        session.get(MemoryFactModel, fact.id).status = "archived"
        session.commit()
        return _response({"pairs": [], "blocks": {}})

    result = await MemoryConsolidator(adapter, SimpleNamespace(chat=withdraw)).run()
    assert result["failed"] == 1 and result["groups"] == 0
    assert not session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "group")
    ).all()


async def test_rollback_is_dry_run_then_atomic_and_idempotent(consolidation_database):
    session, adapter, _ = consolidation_database
    first = await _fact(adapter, "图用英文", agent="", scope="preference")
    second = await _fact(adapter, "图中使用英文", agent="", scope="preference")
    session.commit()
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=_response(
                {
                    "pairs": [{"old_id": first.id, "new_id": second.id, "relation": "duplicate"}],
                    "blocks": {},
                }
            )
        )
    )
    worker = MemoryConsolidator(adapter, provider)
    assert (await worker.run())["groups"] == 1
    run = session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "group")
    ).one()

    preview = await worker.rollback_run(run.run_key, "admin-1", dry_run=True)
    assert preview == {
        "status": "dry_run",
        "run_key": run.run_key,
        "facts": 1,
        "blocks": 0,
        "conflicts": [],
    }
    assert session.get(MemoryFactModel, first.id).status == "superseded"
    assert run.rolled_back_at is None

    result = await worker.rollback_run(run.run_key, "admin-1")
    assert result["status"] == "rolled_back"
    assert session.get(MemoryFactModel, first.id).status == "active"
    assert session.get(MemoryFactModel, first.id).superseded_by is None
    assert run.rolled_back_at is not None
    audit = session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "rollback")
    ).one()
    assert audit.decisions["original_run_key"] == run.run_key
    with pytest.raises(ConflictError):
        await worker.rollback_run(run.run_key, "admin-1")


async def test_rollback_conflict_does_not_mutate_later_fact_change(consolidation_database):
    session, adapter, _ = consolidation_database
    first = await _fact(adapter, "旧偏好", agent="", scope="preference")
    second = await _fact(adapter, "新偏好", agent="", scope="preference")
    session.commit()
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=_response(
                {
                    "pairs": [{"old_id": first.id, "new_id": second.id, "relation": "conflict"}],
                    "blocks": {},
                }
            )
        )
    )
    worker = MemoryConsolidator(adapter, provider)
    await worker.run()
    run = session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "group")
    ).one()
    session.get(MemoryFactModel, first.id).status = "archived"
    session.commit()

    result = await worker.rollback_run(run.run_key, "admin-1")
    assert result["status"] == "conflict"
    assert result["conflicts"] == [{"kind": "fact", "id": first.id, "reason": "changed"}]
    assert run.rolled_back_at is None
    assert not session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "rollback")
    ).all()


async def test_rollback_restores_block_snapshot_with_monotonic_version(consolidation_database):
    session, adapter, _ = consolidation_database
    source = await _fact(adapter, "用户长期研究 RNA", agent="", scope="profile")
    session.commit()
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=_response(
                {
                    "pairs": [],
                    "blocks": {
                        "profile": {"content": "用户研究 RNA", "source_ids": [source.id]}
                    },
                }
            )
        )
    )
    worker = MemoryConsolidator(adapter, provider)
    assert (await worker.run())["groups"] == 1
    run = session.scalars(
        select(MemoryConsolidationRunModel).where(MemoryConsolidationRunModel.kind == "group")
    ).one()
    block = session.scalars(
        select(MemoryBlockModel).where(MemoryBlockModel.block_name == "profile")
    ).one()
    assert (block.content, block.version) == ("用户研究 RNA", 2)

    result = await worker.rollback_run(run.run_key, "admin-1")

    assert result["status"] == "rolled_back"
    assert (block.content, block.version) == ("", 3)
