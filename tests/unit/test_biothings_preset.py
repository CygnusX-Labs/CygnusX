"""Contract checks for the internal BioThings builtin preset."""

from __future__ import annotations

import json

import httpx
import pytest

from cygnusx.application.services.biothings_service import _bound_result, execute_biothings
from cygnusx.infrastructure.mcp.biothings_preset import (
    BIOTHINGS_HANDLERS,
    BIOTHINGS_TOOLS,
    CYGNUSX_BIOTHINGS_SERVER_ID,
    CYGNUSX_BIOTHINGS_SERVER_NAME,
)
from cygnusx.infrastructure.mcp.presets import get_preset_by_name


@pytest.mark.unit
def test_biothings_preset_has_fixed_ten_tool_contract():
    preset = get_preset_by_name(CYGNUSX_BIOTHINGS_SERVER_NAME)

    assert preset is not None
    assert preset["transport"] == "builtin"
    assert preset["tools"] == BIOTHINGS_TOOLS
    assert set(BIOTHINGS_HANDLERS) == {tool["name"] for tool in BIOTHINGS_TOOLS}
    assert len(BIOTHINGS_TOOLS) == 10
    assert CYGNUSX_BIOTHINGS_SERVER_ID.int != 0


@pytest.mark.unit
async def test_biothings_preset_rejects_ambiguous_species_and_assembly(monkeypatch):
    async def fail_if_requested(*_args, **_kwargs):
        pytest.fail("invalid arguments must be rejected before provider access")

    monkeypatch.setattr(
        "cygnusx.application.services.biothings_service._request", fail_if_requested
    )
    gene = await BIOTHINGS_HANDLERS["cygnusx_gene_search"](
        {"query": "At5g12345", "limit": 1, "offset": 0},
        tool_name="cygnusx_gene_search",
    )
    variant = await BIOTHINGS_HANDLERS["cygnusx_variant_get"](
        {"identifier": "rs123"},
        tool_name="cygnusx_variant_get",
    )

    assert gene["success"] is False
    assert "species is required" in gene["summary"]
    assert variant["success"] is False
    assert "assembly is required" in variant["summary"]


@pytest.mark.unit
async def test_biothings_preset_validates_species_before_provider_access(monkeypatch):
    async def fail_if_requested(*_args, **_kwargs):
        pytest.fail("invalid arguments must be rejected before provider access")

    monkeypatch.setattr(
        "cygnusx.application.services.biothings_service._request", fail_if_requested
    )
    result = await BIOTHINGS_HANDLERS["cygnusx_gene_resolve"](
        {"identifiers": ["AT5G12345"], "scopes": "symbol"},
        tool_name="cygnusx_gene_resolve",
    )

    assert result["success"] is False
    assert "species is required" in result["summary"]


@pytest.mark.unit
def test_biothings_result_stays_within_utf8_model_budget():
    result = _bound_result(
        {
            "success": True,
            "summary": "query completed",
            "data": {
                "provider": "https://mygene.info/v3",
                "input_context": {"query": "gene"},
                "result": {"hits": [{"description": "基因描述" * 5000}]},
            },
        }
    )

    assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= 3000
    assert result["truncated"] is True


@pytest.mark.unit
async def test_shared_service_uses_fixed_provider_and_explicit_assembly(monkeypatch):
    requests = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"hits": [{"_id": "rs123"}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.biothings_service._provider_client", lambda: client
    )
    result = await execute_biothings(
        "variant", "search", {"query": "rs123", "assembly": "hg38"}
    )

    assert result["success"] is True
    assert requests[0].url.host == "myvariant.info"
    assert requests[0].url.params.get("assembly") == "hg38"
    await client.aclose()
