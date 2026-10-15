"""Authenticated shared tools; no browser/model identity fields are accepted."""

from typing import Any

from fastapi import APIRouter, Header
from pydantic import ValidationError as SchemaError

from cygnusx.api.deps import CurrentJwtUserId, CurrentUserId, DbSession
from cygnusx.application.schemas.agent_tools import AgentToolCall
from cygnusx.application.services.agent_tool_delegation import verify_delegation
from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
from cygnusx.application.services.tool_confirmation_service import ConfirmationError
from cygnusx.core.exceptions import AuthenticationError, ConflictError, ValidationError

router = APIRouter()


@router.post("/delegated/invoke")
async def delegated_invoke(
    request: AgentToolCall,
    db: DbSession,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise AuthenticationError("缺少有限委托")
    context = await verify_delegation(db, authorization[7:], request.capability_id, request.call_id)
    try:
        return await AgentToolGateway(db).invoke(context, request.capability_id, request.arguments)
    except SchemaError as exc:
        raise ValidationError("参数不符合工具契约", code="VALIDATION_ERROR") from exc


@router.get("/sessions/{session_id}/capabilities")
async def capabilities(session_id: str, user: CurrentUserId, db: DbSession) -> dict[str, Any]:
    gateway = AgentToolGateway(db)
    context = await gateway.context(user, session_id)
    return {
        "schema_version": "1.0",
        "tools": gateway.catalog(context),
        "write_enabled": False,
        "gate": "WRITE_GATE_BLOCKED",
    }


@router.post("/sessions/{session_id}/invoke")
async def invoke(
    session_id: str,
    request: AgentToolCall,
    user: CurrentUserId,
    db: DbSession,
) -> dict[str, Any]:
    gateway = AgentToolGateway(db)
    context = await gateway.context(user, session_id)
    try:
        return await gateway.invoke(context, request.capability_id, request.arguments)
    except SchemaError as exc:
        raise ValidationError("参数不符合工具契约", code="VALIDATION_ERROR") from exc


@router.get("/sessions/{session_id}/related")
async def related(session_id: str, user: CurrentUserId, db: DbSession) -> list[dict[str, Any]]:
    gateway = AgentToolGateway(db)
    return await gateway.related(await gateway.context(user, session_id))


@router.post("/sessions/{session_id}/proposals/{proposal_id}/approve")
async def approve(
    session_id: str,
    proposal_id: str,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, Any]:
    gateway = AgentToolGateway(db)
    try:
        return await gateway.decide(
            await gateway.context(user, session_id), proposal_id, approve=True
        )
    except ConfirmationError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc


@router.post("/sessions/{session_id}/proposals/{proposal_id}/reject")
async def reject(
    session_id: str,
    proposal_id: str,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, Any]:
    gateway = AgentToolGateway(db)
    try:
        return await gateway.decide(
            await gateway.context(user, session_id), proposal_id, approve=False
        )
    except ConfirmationError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc


@router.post("/sessions/{session_id}/proposals/{proposal_id}/execute")
async def execute(
    session_id: str,
    proposal_id: str,
    user: CurrentUserId,
    db: DbSession,
) -> dict[str, Any]:
    gateway = AgentToolGateway(db)
    return await gateway.execute(await gateway.context(user, session_id), proposal_id)
