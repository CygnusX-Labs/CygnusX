"""Contract and boundary tests for the internal research-data preset."""

from __future__ import annotations

import httpx
import pytest

from cygnusx.application.services.research_data_service import execute_research
from cygnusx.infrastructure.mcp.presets import get_preset_by_name
from cygnusx.infrastructure.mcp.research_preset import (
    CYGNUSX_RESEARCH_SERVER_NAME,
    RESEARCH_HANDLERS,
    RESEARCH_TOOLS,
)


@pytest.mark.unit
def test_research_preset_has_fixed_verified_read_only_contract():
    preset = get_preset_by_name(CYGNUSX_RESEARCH_SERVER_NAME)

    assert preset is not None
    assert preset["transport"] == "builtin"
    assert len(RESEARCH_TOOLS) == 26
    assert set(RESEARCH_HANDLERS) == {tool["name"] for tool in RESEARCH_TOOLS}


@pytest.mark.unit
async def test_research_service_rejects_unbounded_inputs_before_http(monkeypatch):
    async def fail_request(*_args, **_kwargs):
        pytest.fail("invalid provider input must fail before HTTP")

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request", fail_request
    )
    result = await execute_research("cygnusx_pathway_get", {"pathway_id": "not-a-pathway"})
    assert result["success"] is False
    assert "pathway_id" in result["summary"]


@pytest.mark.unit
async def test_research_service_uses_fixed_rcsb_endpoint(monkeypatch):
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"total_count": 1, "result_set": [{"identifier": "1ABC_1"}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )
    result = await execute_research("cygnusx_structure_search", {"accession": "P04637"})

    assert result["success"] is True
    assert requests[0].url.host == "search.rcsb.org"
    assert requests[0].method == "POST"
    await client.aclose()
