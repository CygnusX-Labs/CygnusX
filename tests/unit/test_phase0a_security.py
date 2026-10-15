"""Phase 0A 安全边界单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from cygnusx.application.services.tool_confirmation_service import (
    ConfirmationError,
    ToolConfirmationService,
    _MemoryStore,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_confirmation_requires_human_approval_and_is_single_use() -> None:
    service = ToolConfirmationService(_MemoryStore())
    arguments = {"task_id": "task-1", "mode": "cancel"}
    record = await service.create_for_tool("user-1", "cygnusx_cancel_task", arguments)

    with pytest.raises(ConfirmationError, match="等待用户") as pending:
        await service.consume_tool_confirmation(
            "user-1", record.confirmation_id, "cygnusx_cancel_task", arguments
        )
    assert pending.value.code == "CONFIRMATION_REQUIRED"

    await service.approve_by_human(user_id="user-1", confirmation_id=record.confirmation_id)
    consumed = await service.consume_tool_confirmation(
        "user-1", record.confirmation_id, "cygnusx_cancel_task", arguments
    )
    assert consumed.status == "CONSUMED"

    with pytest.raises(ConfirmationError) as reused:
        await service.consume_tool_confirmation(
            "user-1", record.confirmation_id, "cygnusx_cancel_task", arguments
        )
    assert reused.value.code == "ALREADY_CONSUMED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_confirmation_rejects_changed_arguments_and_wrong_owner() -> None:
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create_for_tool("user-1", "cygnusx_cancel_task", {"task_id": "task-1"})

    with pytest.raises(ConfirmationError) as owner_error:
        await service.consume_tool_confirmation(
            "user-2", record.confirmation_id, "cygnusx_cancel_task", {"task_id": "task-1"}
        )
    assert owner_error.value.code == "ACCESS_DENIED"

    await service.approve_by_human(user_id="user-1", confirmation_id=record.confirmation_id)
    with pytest.raises(ConfirmationError) as args_error:
        await service.consume_tool_confirmation(
            "user-1", record.confirmation_id, "cygnusx_cancel_task", {"task_id": "task-2"}
        )
    assert args_error.value.code == "ARGS_CHANGED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_confirmation_concurrent_consumption_is_atomic() -> None:
    service = ToolConfirmationService(_MemoryStore())
    arguments = {"task_id": "task-1"}
    record = await service.create_for_tool("user-1", "cygnusx_cancel_task", arguments)
    await service.approve_by_human(user_id="user-1", confirmation_id=record.confirmation_id)

    results = await asyncio.gather(
        service.consume_tool_confirmation(
            "user-1", record.confirmation_id, "cygnusx_cancel_task", arguments
        ),
        service.consume_tool_confirmation(
            "user-1", record.confirmation_id, "cygnusx_cancel_task", arguments
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(result, Exception) for result in results) == 1
    assert sum(getattr(result, "status", None) == "CONSUMED" for result in results) == 1
    errors = [result for result in results if isinstance(result, ConfirmationError)]
    assert errors[0].code == "ALREADY_CONSUMED"

