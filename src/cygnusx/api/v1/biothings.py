"""Authenticated API bridge to the shared read-only BioThings service."""

from typing import Any

from fastapi import APIRouter

from cygnusx.api.deps import CurrentUserId
from cygnusx.application.services.biothings_service import (
    describe_biothings,
    execute_biothings,
)

router = APIRouter()


@router.post("/{database}/describe", summary="Describe a BioThings provider")
async def describe_biothings_provider(
    _user_id: CurrentUserId, database: str
) -> dict[str, Any]:
    return await describe_biothings(database)


@router.post("/{database}/{action}", summary="Query a supported BioThings provider")
async def query_biothings(
    _user_id: CurrentUserId,
    database: str,
    action: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """The provider and path are selected by server code; caller-supplied URLs are rejected."""
    return await execute_biothings(database, action, arguments)
