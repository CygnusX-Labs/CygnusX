"""固定分析工具（cygnusx_prepare / cygnusx_submit）API 契约测试。"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.api.v1.ai import (
    FlowPrepareRequest,
    prepare_analysis_flow,
    submit_analysis_flow,
)
from cygnusx.application.services.analysis_flow_tool_service import FlowAIError
from cygnusx.application.services.tool_confirmation_service import ConfirmationError
from cygnusx.core.exceptions import NotFoundError


class _FakeAsyncSession(AsyncSession):
    def __init__(self):
        pass


def _db() -> _FakeAsyncSession:
    return _FakeAsyncSession()


@pytest.mark.asyncio
async def test_prepare_forwards_arguments_and_returns_result() -> None:
    db = _db()
    with patch("cygnusx.api.v1.ai.AnalysisFlowToolService") as service_type:
        instance = service_type.return_value
        instance.prepare = AsyncMock(
            return_value={"valid": True, "flow_id": "rna_seq", "confirmation_id": "c-1"}
        )
        result = await prepare_analysis_flow(
            "rna_seq",
            FlowPrepareRequest(arguments={"task_name": "demo"}),
            current_user_id="u1",
            db=db,
        )
    instance.prepare.assert_awaited_once_with("rna_seq", {"task_name": "demo"})
    assert result["valid"] is True
    assert result["confirmation_id"] == "c-1"


@pytest.mark.asyncio
async def test_prepare_maps_not_found_to_404() -> None:
    db = _db()
    with patch("cygnusx.api.v1.ai.AnalysisFlowToolService") as service_type:
        service_type.return_value.prepare = AsyncMock(
            side_effect=NotFoundError("流程 'counts_deg' 不存在")
        )
        with pytest.raises(HTTPException) as exc_info:
            await prepare_analysis_flow(
                "counts_deg", FlowPrepareRequest(arguments={}), current_user_id="u1", db=db
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_prepare_maps_flow_ai_error_to_400() -> None:
    db = _db()
    with patch("cygnusx.api.v1.ai.AnalysisFlowToolService") as service_type:
        service_type.return_value.prepare = AsyncMock(
            side_effect=FlowAIError("AI_DISABLED", "流程未启用 AI 助手接入")
        )
        with pytest.raises(HTTPException) as exc_info:
            await prepare_analysis_flow(
                "scrna", FlowPrepareRequest(arguments={}), current_user_id="u1", db=db
            )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "AI_DISABLED"


@pytest.mark.asyncio
async def test_submit_consumes_confirmation_via_service() -> None:
    db = _db()
    confirmation_id = uuid4()
    with patch("cygnusx.api.v1.ai.AnalysisFlowToolService") as service_type:
        instance = service_type.return_value
        instance.confirm_and_submit = AsyncMock(
            return_value={"task_id": "t-1", "status": "QUEUED", "task_url": "/tasks/t-1"}
        )
        result = await submit_analysis_flow(
            current_user_id="u1", db=db, confirmation_id=confirmation_id
        )
    instance.confirm_and_submit.assert_awaited_once_with(str(confirmation_id))
    assert result == {"success": True, "task_id": "t-1", "status": "QUEUED", "task_url": "/tasks/t-1"}


@pytest.mark.asyncio
async def test_submit_maps_confirmation_error_to_400() -> None:
    db = _db()
    with patch("cygnusx.api.v1.ai.AnalysisFlowToolService") as service_type:
        service_type.return_value.confirm_and_submit = AsyncMock(
            side_effect=ConfirmationError("CONFIRMATION_REQUIRED", "等待用户确认")
        )
        with pytest.raises(HTTPException) as exc_info:
            await submit_analysis_flow(
                current_user_id="u1", db=db, confirmation_id=uuid4()
            )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "CONFIRMATION_REQUIRED"
