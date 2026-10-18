"""契约漂移防线（R5）测试：prepare 冻结流程版本，submit 比对，漂移即拒绝。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.tool_confirmation_service import (
    ConfirmationError,
    ConfirmationRecord,
    ToolConfirmationService,
    _MemoryStore,
)


class _FakeAsyncSession(AsyncSession):
    def __init__(self):
        pass


def _context(*, human: bool = False) -> ToolInvocationContext:
    return ToolInvocationContext(
        user_id="u1",
        session_id="s-test",
        db=_FakeAsyncSession(),
        extra={"human_confirmed": True} if human else {},
    )


def _request() -> TaskSubmitRequest:
    return TaskSubmitRequest(
        flow_id="rna_seq",
        name="demo",
        parameters={"species": "Homo sapiens"},
        sample_sheet=[{"sample": "S1", "group": "ctrl"}],
        comparisons=None,
        execution_mode="local",
    )


def _task_service() -> MagicMock:
    task_service = MagicMock()
    task_service.submit = AsyncMock(
        return_value=MagicMock(id=uuid4(), flow_id="rna_seq", status="queued", progress=0)
    )
    return task_service


@pytest.mark.asyncio
async def test_create_freezes_flow_version() -> None:
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create(
        context=_context(),
        flow_id="rna_seq",
        flow_name="RNA-seq",
        normalized_request=_request(),
        flow_version="2.3.0",
    )
    assert record.flow_version == "2.3.0"


@pytest.mark.asyncio
async def test_legacy_record_without_flow_version_not_blocked() -> None:
    """存量确认记录（无 flow_version 字段）不受漂移防线影响。"""
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create(
        context=_context(), flow_id="rna_seq", flow_name="RNA-seq", normalized_request=_request()
    )
    assert record.flow_version == ""

    task_service = _task_service()
    with patch(
        "cygnusx.application.services.flow_service.FlowService"
    ) as flow_service_type:
        # 防御性 mock：存量记录不应触达 FlowService
        flow_service_type.return_value.get_flow_config.side_effect = AssertionError(
            "legacy record must not trigger drift check"
        )
        result = await service.approve(
            _context(human=True), record.confirmation_id, task_service
        )
    assert result.status == "SUBMITTED"


@pytest.mark.asyncio
async def test_submit_rejects_when_flow_definition_changed() -> None:
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create(
        context=_context(),
        flow_id="rna_seq",
        flow_name="RNA-seq",
        normalized_request=_request(),
        flow_version="2.3.0",
    )
    task_service = _task_service()

    changed_config = MagicMock()
    changed_config.meta.version = "2.4.0"
    with patch(
        "cygnusx.application.services.flow_service.FlowService"
    ) as flow_service_type:
        flow_service_type.return_value.get_flow_config.return_value = changed_config
        with pytest.raises(ConfirmationError) as exc_info:
            await service.approve(_context(human=True), record.confirmation_id, task_service)

    assert exc_info.value.code == "FLOW_CONTRACT_CHANGED"
    assert "2.3.0" in exc_info.value.message and "2.4.0" in exc_info.value.message
    task_service.submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_passes_when_flow_version_matches() -> None:
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create(
        context=_context(),
        flow_id="rna_seq",
        flow_name="RNA-seq",
        normalized_request=_request(),
        flow_version="2.3.0",
    )
    task_service = _task_service()

    current_config = MagicMock()
    current_config.meta.version = "2.3.0"
    with patch(
        "cygnusx.application.services.flow_service.FlowService"
    ) as flow_service_type:
        flow_service_type.return_value.get_flow_config.return_value = current_config
        result = await service.approve(_context(human=True), record.confirmation_id, task_service)
    assert result.status == "SUBMITTED"
    task_service.submit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_json_roundtrip_preserves_flow_version() -> None:
    service = ToolConfirmationService(_MemoryStore())
    record = await service.create(
        context=_context(),
        flow_id="rna_seq",
        flow_name="RNA-seq",
        normalized_request=_request(),
        flow_version="2.3.0",
    )
    restored = ConfirmationRecord.from_json(record.to_json())
    assert restored.flow_version == "2.3.0"
    assert restored.confirmation_id == record.confirmation_id
