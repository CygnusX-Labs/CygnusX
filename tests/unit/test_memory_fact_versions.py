"""SQL-backed explicit re-remembering without reviving old fact rows.

SQLite checks lifecycle transactions; PostgreSQL/pgvector still require staging.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from cygnusx.infrastructure.database.models.agent_memory import MemoryBlockModel, MemoryFactModel
from cygnusx.infrastructure.memory.fact_store import MemoryFactCreate, PostgresFactStore

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]




@pytest.mark.parametrize("old_status", ["archived", "superseded"])
async def test_explicit_save_creates_new_active_version_and_preserves_old_history(fact_database, old_status) -> None:
    session, adapter = fact_database
    store = PostgresFactStore(adapter)
    fact = MemoryFactCreate(user_id="owner", agent_id="a", scope="project", project_id="p",
                            content="常用 GRCh38", source_session_id="original")
    old = await store.insert(fact)
    old_model = session.get(MemoryFactModel, old.id)
    old_model.status = old_status
    successor_id = None
    if old_status == "superseded":
        successor = await store.insert(MemoryFactCreate(
            user_id="owner", agent_id="a", scope="project", project_id="p", content="常用 GRCm39"
        ))
        successor_id = successor.id
        old_model.superseded_by = successor_id
    session.commit()
    assert (await store.insert(fact)).status == old_status  # Automatic settlement cannot revive it.
    fact.source_session_id = "new-consent"
    current = await store.insert(fact, allow_recreate=True)
    session.commit()
    assert current.id != old.id and current.status == "active"
    assert current.source_session_id == "new-consent"
    assert session.get(MemoryFactModel, old.id).status == old_status
    assert session.get(MemoryFactModel, old.id).source_session_id == "original"
    assert session.get(MemoryFactModel, old.id).superseded_by == successor_id
    assert (await store.insert(fact, allow_recreate=True)).id == current.id
    assert len(session.scalars(select(MemoryFactModel)).all()) == (3 if successor_id else 2)


async def test_failed_recreation_rolls_back_retired_dedup_slot(fact_database, monkeypatch) -> None:
    session, adapter = fact_database
    store = PostgresFactStore(adapter)
    fact = MemoryFactCreate(user_id="owner", agent_id="a", scope="project", content="remember")
    old = await store.insert(fact)
    session.get(MemoryFactModel, old.id).status = "archived"
    session.commit()
    old_hash = session.get(MemoryFactModel, old.id).content_hash
    monkeypatch.setattr(adapter, "flush", AsyncMock(side_effect=RuntimeError("write failure")))
    with pytest.raises(RuntimeError, match="write failure"):
        await store.insert(fact, allow_recreate=True)
    session.rollback()
    assert session.get(MemoryFactModel, old.id).content_hash == old_hash
    assert session.get(MemoryFactModel, old.id).status == "archived"
    assert len(session.scalars(select(MemoryFactModel)).all()) == 1


async def test_service_returns_active_new_version_after_explicit_save(fact_database, monkeypatch) -> None:
    from cygnusx.application.services.agent_memory_service import AgentMemoryService

    session, adapter = fact_database
    store = PostgresFactStore(adapter)
    old = await store.insert(MemoryFactCreate(
        user_id="owner", agent_id="a", scope="project", project_id="p", content="常用 GRCh38"
    ))
    session.get(MemoryFactModel, old.id).status = "archived"
    session.commit()
    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: SimpleNamespace(memory_v2_enabled=True, memory_focus_per_project_enabled=False, agent_memory_embedding_model="test",
                                memory_write_arbitration_enabled=True, memory_settle_candidate_limit=30),
    )
    service = AgentMemoryService(adapter)
    monkeypatch.setattr(service, "ensure_memory_blocks", AsyncMock())
    monkeypatch.setattr(service, "_embed", AsyncMock(return_value=[]))
    result = await service.save_memory(user_id="owner", agent_id="a", project_id="p",
                                       scope="project", content="常用 GRCh38", source_session="new-consent")
    session.commit()
    assert result["memory"]["status"] == "active"
    assert result["memory"]["id"] != str(old.id)
    assert session.get(MemoryFactModel, old.id).status == "archived"

    new_model = session.get(MemoryFactModel, int(result["memory"]["id"]))
    assert new_model.embedding is None and new_model.embedding_model is None



def _arbitrating_service(adapter, monkeypatch, provider):
    from cygnusx.application.services.agent_memory_service import AgentMemoryService

    monkeypatch.setattr(
        "cygnusx.application.services.agent_memory_service.get_settings",
        lambda: SimpleNamespace(
            memory_v2_enabled=True, memory_focus_per_project_enabled=False, agent_memory_embedding_model="test",
            memory_write_arbitration_enabled=True, memory_settle_candidate_limit=30,
            memory_extraction_model="memory-test",
        ),
    )
    service = AgentMemoryService(adapter, embedding_client=provider)
    monkeypatch.setattr(service, "ensure_memory_blocks", AsyncMock())
    return service


@pytest.mark.parametrize("replace", [True, False])
async def test_explicit_save_arbitrates_before_atomic_revision(fact_database, monkeypatch, replace) -> None:
    import json

    session, adapter = fact_database
    old = await PostgresFactStore(adapter).insert(MemoryFactCreate(
        user_id="owner", agent_id="a", scope="project", project_id="p",
        content="常用 GRCh37" if replace else "小鼠使用 GRCm39",
    ))
    session.commit()
    provider = SimpleNamespace(embeddings=AsyncMock(return_value=[]), chat=AsyncMock(return_value={
        "choices": [{"message": {"content": json.dumps({"supersede_ids": [old.id] if replace else []})}}]
    }))
    service = _arbitrating_service(adapter, monkeypatch, provider)
    result = await service.save_memory(user_id="owner", agent_id="a", project_id="p",
                                       scope="project", content="人类使用 GRCh38")
    session.commit()
    provider.chat.assert_awaited_once()
    assert result["memory"]["status"] == "active"
    assert result["action"] == ("updated" if replace else "created")
    previous = session.get(MemoryFactModel, old.id)
    assert previous.status == ("superseded" if replace else "active")
    if replace:
        assert previous.superseded_by == int(result["memory"]["id"])


@pytest.mark.parametrize("response", ['{"supersede_ids":[999]}', '{"supersede_ids":[true]}', 'invalid'])
async def test_invalid_explicit_arbitration_does_not_write(fact_database, monkeypatch, response) -> None:
    from cygnusx.core.exceptions import BusinessError

    session, adapter = fact_database
    old = await PostgresFactStore(adapter).insert(MemoryFactCreate(
        user_id="owner", agent_id="a", scope="project", project_id="p", content="old fact"
    ))
    session.commit()
    provider = SimpleNamespace(embeddings=AsyncMock(return_value=[]), chat=AsyncMock(return_value={
        "choices": [{"message": {"content": response}}]
    }))
    service = _arbitrating_service(adapter, monkeypatch, provider)
    with pytest.raises(BusinessError, match="校验失败"):
        await service.save_memory(user_id="owner", agent_id="a", project_id="p",
                                  scope="project", content="new fact")
    assert session.get(MemoryFactModel, old.id).status == "active"
    assert len(session.scalars(select(MemoryFactModel)).all()) == 1
    service.ensure_memory_blocks.assert_not_awaited()


async def test_stale_second_target_rolls_back_all_explicit_revisions(fact_database, monkeypatch) -> None:
    import json

    from cygnusx.core.exceptions import BusinessError

    session, adapter = fact_database
    store = PostgresFactStore(adapter)
    old = [await store.insert(MemoryFactCreate(
        user_id="owner", agent_id="a", scope="project", project_id="p", content=content
    )) for content in ("first old fact", "second old fact")]
    session.commit()

    async def adjudicate(*args, **kwargs):
        # Simulate another committed owner action while the model was running.
        session.get(MemoryFactModel, old[1].id).status = "archived"
        session.commit()
        return {"choices": [{"message": {"content": json.dumps({
            "supersede_ids": [fact.id for fact in old]
        })}}]}

    provider = SimpleNamespace(embeddings=AsyncMock(return_value=[]), chat=adjudicate)
    service = _arbitrating_service(adapter, monkeypatch, provider)
    with pytest.raises(BusinessError, match="并发修改"):
        await service.save_memory(user_id="owner", agent_id="a", project_id="p",
                                  scope="project", content="replacement")
    session.commit()
    assert session.get(MemoryFactModel, old[0].id).status == "active"
    assert session.get(MemoryFactModel, old[0].id).superseded_by is None
    assert session.get(MemoryFactModel, old[1].id).status == "archived"
    assert len(session.scalars(select(MemoryFactModel)).all()) == 2


async def test_agent_overview_includes_shared_memory_and_hides_archived_blocks(fact_database, monkeypatch) -> None:
    from cygnusx.application.services.agent_memory_service import AgentMemoryService

    session, adapter = fact_database
    canonical = MemoryBlockModel(user_id="owner", agent_id="", block_name="profile", content="shared")
    focus = MemoryBlockModel(user_id="owner", agent_id="a", block_name="current_focus", content="focus")
    session.add_all([canonical, focus])
    session.flush()
    old = MemoryBlockModel(user_id="owner", agent_id="a", block_name="profile", content="old",
                           status="archived", superseded_by=canonical.id)
    session.add(old)
    store = PostgresFactStore(adapter)
    shared = await store.insert(MemoryFactCreate(user_id="owner", agent_id="", scope="preference", content="shared preference"))
    own = await store.insert(MemoryFactCreate(user_id="owner", agent_id="a", scope="project", project_id="p", content="own"))
    await store.insert(MemoryFactCreate(user_id="owner", agent_id="b", scope="project", project_id="p", content="other agent"))
    await store.insert(MemoryFactCreate(user_id="other", agent_id="", scope="preference", content="other user"))
    session.commit()
    monkeypatch.setattr("cygnusx.application.services.agent_memory_service.get_settings",
                        lambda: SimpleNamespace(memory_v2_enabled=True, memory_focus_per_project_enabled=False))
    service = AgentMemoryService(adapter)
    overview = await service.get_memory_overview("owner", agent_id="a", project_id="p")
    assert {block["id"] for block in overview["blocks"]} == {canonical.id, focus.id}
    assert {fact["id"] for fact in overview["facts"]} == {shared.id, own.id}
    audit = await service.get_memory_overview("owner", agent_id="a", include_archived=True)
    archived = next(block for block in audit["blocks"] if block["id"] == old.id)
    assert archived["status"] == "archived" and archived["superseded_by"] == canonical.id
