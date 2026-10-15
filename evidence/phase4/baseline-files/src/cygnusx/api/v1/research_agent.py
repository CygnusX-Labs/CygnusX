"""科研寻宝鼠原生只读发现 API。

浏览器只接触本路由；Node/TS Agent 不作为公开认证入口。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from cygnusx.api.deps import CurrentUserId, DbSession
from cygnusx.application.schemas.research_agent import (
    ResearchAgentCapabilities,
    ResearchAgentMessageRequest,
    ResearchAgentSessionCreate,
)
from cygnusx.application.services.research_treasure_service import ResearchTreasureService
from cygnusx.core.config import get_settings

router = APIRouter()
def _service(db: DbSession) -> ResearchTreasureService:
    return ResearchTreasureService(db)


@router.get("/capabilities", response_model=ResearchAgentCapabilities)
async def capabilities(_: CurrentUserId) -> ResearchAgentCapabilities:
    settings = get_settings()
    return ResearchAgentCapabilities(
        native_ui_enabled=settings.treasure_native_ui_enabled,
        write_tools_enabled=False,
    )


@router.post("/sessions")
async def create_session(
    request: ResearchAgentSessionCreate,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> object:
    service = _service(db)
    service.ensure_enabled()
    return await service.create_session(
        current_user_id,
        str(request.project_id) if request.project_id else None,
        request.title,
        request.model_id,
    )


@router.get("/sessions")
async def list_sessions(
    current_user_id: CurrentUserId,
    db: DbSession,
    project_id: UUID | None = None,
) -> list[object]:
    service = _service(db)
    service.ensure_enabled()
    return await service.list_sessions(current_user_id, str(project_id) if project_id else None)


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, current_user_id: CurrentUserId, db: DbSession) -> list[object]:
    service = _service(db)
    service.ensure_enabled()
    return await service.messages(current_user_id, session_id)


@router.post("/sessions/{session_id}/messages:stream")
async def stream_message(
    session_id: str,
    request: ResearchAgentMessageRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> StreamingResponse:
    service = _service(db)
    service.ensure_enabled()

    async def generate() -> AsyncIterator[str]:
        async for event in service.stream_message(
            current_user_id,
            session_id,
            request.content,
            request.model_id,
            request.lang,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str, current_user_id: CurrentUserId, db: DbSession) -> dict[str, bool]:
    service = _service(db)
    service.ensure_enabled()
    return {"cancelled": await service.cancel(current_user_id, session_id)}
