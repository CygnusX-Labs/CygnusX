"""管理员 v2 记忆查看接口的安全契约测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from cygnusx.api.v1.admin.users import (
    get_user_memory_overview,
    rollback_memory_consolidation,
)
from cygnusx.application.schemas.agent_memory import (
    MemoryConsolidationRollbackRequest,
    MemoryOverviewDTO,
)
from cygnusx.core.exceptions import NotFoundError


@pytest.mark.asyncio
async def test_admin_memory_overview_rejects_unknown_user() -> None:
    db = AsyncMock()
    db.get.return_value = None

    with pytest.raises(NotFoundError, match="用户不存在"):
        await get_user_memory_overview(
            uuid4(),
            _admin="admin",
            db=db,
        )


@pytest.mark.asyncio
async def test_admin_memory_overview_forwards_filters_and_returns_v2_data() -> None:
    user_id = uuid4()
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=user_id)
    overview = {
        "mode": "v2",
        "agent_ids": ["agent-general", "agent-rna"],
        "blocks": [],
        "facts": [],
        "legacy_memories": [],
    }

    with patch("cygnusx.api.v1.admin.users.AgentMemoryService") as service_type:
        service_type.return_value.get_memory_overview = AsyncMock(return_value=overview)

        result = await get_user_memory_overview(
            user_id,
            _admin="admin",
            db=db,
            agent_id="agent-rna",
            project_id="project-a",
            scope="project",
            include_archived=False,
        )

    assert isinstance(result, MemoryOverviewDTO)
    assert result.agent_ids == ["agent-general", "agent-rna"]
    service_type.return_value.get_memory_overview.assert_awaited_once_with(
        str(user_id),
        agent_id="agent-rna",
        project_id="project-a",
        scope="project",
        include_archived=False,
    )


@pytest.mark.asyncio
async def test_admin_consolidation_rollback_passes_authenticated_actor() -> None:
    db = AsyncMock()
    expected = {"status": "dry_run", "run_key": "run-1", "conflicts": []}
    with patch(
        "cygnusx.infrastructure.memory.consolidation.MemoryConsolidator.rollback_run",
        new=AsyncMock(return_value=expected),
    ) as rollback:
        result = await rollback_memory_consolidation(
            "run-1",
            MemoryConsolidationRollbackRequest(dry_run=True),
            current_user_id="admin-7",
            _admin=None,
            db=db,
        )

    assert result == expected
    rollback.assert_awaited_once_with("run-1", "admin-7", dry_run=True)
