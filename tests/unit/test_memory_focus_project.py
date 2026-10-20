"""SQL-backed focus partition, fallback, lazy creation and CAS behavior.

SQLite lifecycle checks do not replace actual PostgreSQL migration/lock acceptance.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.core.exceptions import BusinessError
from cygnusx.infrastructure.database.models.agent_memory import MemoryBlockModel

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_focus_reads_exact_project_without_general_fallback(
    fact_database, project_focus_settings,
):
    session, adapter = fact_database
    service = AgentMemoryService(adapter)
    service._embed = AsyncMock(return_value=[])
    await service.update_memory_block("owner", "a", "profile", "shared background", 1)
    await service.update_memory_block("owner", "a", "current_focus", "general focus", 1)
    await service.update_memory_block("owner", "a", "current_focus", "alpha focus", 1, project_id="p")
    await service.update_memory_block("owner", "a", "current_focus", "beta focus", 1, project_id="q")
    await service.update_memory_block("other", "a", "current_focus", "foreign focus", 1, project_id="p")
    await service.update_memory_block("owner", "b", "current_focus", "other agent", 1, project_id="p")
    session.commit()
    count = len(session.scalars(select(MemoryBlockModel)).all())
    for project, included in [("p", "alpha focus"), ("q", "beta focus"), (None, "general focus"), ("new", None)]:
        prompt = await service.build_prompt_context_v2("owner", "a", "focus", project_id=project)
        assert "shared background" in prompt
        for text in ("alpha focus", "beta focus", "general focus", "foreign focus", "other agent"):
            assert (text in prompt) == (text == included)
    assert len(session.scalars(select(MemoryBlockModel)).all()) == count  # Reads cannot prebuild focus.
    assert not session.scalars(select(MemoryBlockModel).where(MemoryBlockModel.project_id == "new")).all()


async def test_disabling_project_focus_retains_project_rows_and_uses_general(
    fact_database, project_focus_settings,
):
    session, adapter = fact_database
    service = AgentMemoryService(adapter)
    service._embed = AsyncMock(return_value=[])
    saved = await service.update_memory_block("owner", "a", "current_focus", "project text", 1, project_id="p")
    project_focus_settings.memory_focus_per_project_enabled = False
    general = await service.update_memory_block("owner", "a", "current_focus", "compat text", 1, project_id="q")
    assert general["project_id"] is None
    prompt = await service.build_prompt_context_v2("owner", "a", "focus", project_id="p")
    assert "compat text" in prompt and "project text" not in prompt
    assert session.get(MemoryBlockModel, saved["id"]).content == "project text"
    project_focus_settings.memory_focus_per_project_enabled = True
    prompt = await service.build_prompt_context_v2("owner", "a", "focus", project_id="p")
    assert "project text" in prompt and "compat text" not in prompt


async def test_project_creation_idempotency_cas_and_shared_partition(
    fact_database, project_focus_settings,
):
    session, adapter = fact_database
    service = AgentMemoryService(adapter)
    await service.ensure_focus_block("owner", "a", "p")
    await service.ensure_focus_block("owner", "a", "p")
    saved = await service.update_memory_block("owner", "a", "current_focus", "first", 1, project_id="p")
    assert saved["version"] == 2 and saved["project_id"] == "p"
    with pytest.raises(BusinessError, match="并发修改"):
        await service.update_memory_block("owner", "a", "current_focus", "stale", 1, project_id="p")
    assert session.get(MemoryBlockModel, saved["id"]).content == "first"
    shared = await service.update_memory_block("owner", "a", "preferences", "English", 1, project_id="p")
    assert shared["agent_id"] == "" and shared["project_id"] is None
    assert len(session.scalars(select(MemoryBlockModel).where(MemoryBlockModel.project_id == "p")).all()) == 1
    session.commit()
    # SQL unique indexes must protect both NULL and non-NULL partitions.
    for project in (None, "p"):
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(MemoryBlockModel(user_id="owner", agent_id="a", block_name="current_focus", project_id=project))
            session.flush()


async def test_overview_project_filter_returns_shared_and_exact_focus(
    fact_database, project_focus_settings,
):
    _, adapter = fact_database
    service = AgentMemoryService(adapter)
    await service.update_memory_block("owner", "a", "current_focus", "general", 1)
    target = await service.update_memory_block("owner", "a", "current_focus", "alpha", 1, project_id="p")
    await service.update_memory_block("owner", "a", "current_focus", "beta", 1, project_id="q")
    result = await service.get_memory_overview("owner", agent_id="a", project_id="p")
    assert result["focus_per_project_enabled"] is True
    assert [block["id"] for block in result["blocks"] if block["block_name"] == "current_focus"] == [target["id"]]
    assert {block["project_id"] for block in result["blocks"]} == {None, "p"}
