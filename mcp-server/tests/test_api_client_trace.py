"""MCP-to-platform bridge preserves a safe request correlation ID."""

from __future__ import annotations

import re

import httpx
import pytest
from client.api_client import CygnusXAPIClient

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_request_sends_and_logs_platform_request_id() -> None:
    request_ids: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        request_id = request.headers["x-request-id"]
        request_ids.append(request_id)
        return httpx.Response(
            200,
            json={"items": []},
            headers={"x-request-id": request_id},
            request=request,
        )

    api = CygnusXAPIClient()
    previous_client = api._client
    api._client = httpx.AsyncClient(
        base_url="http://platform.test/api/v1",
        transport=httpx.MockTransport(handler),
        headers={"X-API-Key": "test-only"},
    )
    try:
        result = await api.get("/flows")
    finally:
        await api._client.aclose()
        await previous_client.aclose()

    assert result == {"items": []}
    assert len(request_ids) == 1
    assert re.fullmatch(r"[0-9a-f]{32}", request_ids[0])
