"""Authenticated bridge for the fixed read-only research-data adapters."""

from typing import Any

from fastapi import APIRouter

from cygnusx.api.deps import CurrentUserId
from cygnusx.application.services.research_data_service import execute_research
from cygnusx.infrastructure.mcp.research_preset import (
    RESEARCH_TOOLS,
    validate_research_arguments,
)

router = APIRouter()

_RESEARCH_TOOLS = frozenset(tool["name"] for tool in RESEARCH_TOOLS)


@router.post("/{tool_name}", summary="Run a fixed read-only research-data adapter")
async def query_research_data(
    _user_id: CurrentUserId,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Keep provider selection and paths server-owned; no arbitrary URL is accepted."""
    if tool_name not in _RESEARCH_TOOLS:
        return {"success": False, "summary": "Research tool is not enabled", "data": None}
    error = validate_research_arguments(tool_name, arguments)
    if error:
        return {"success": False, "summary": error, "data": None}
    return await execute_research(tool_name, arguments)
