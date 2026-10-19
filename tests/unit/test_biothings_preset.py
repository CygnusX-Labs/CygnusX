"""Contract checks for the internal BioThings builtin preset."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from urllib.parse import parse_qs

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


class _CountingByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.yielded = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


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
        "variant", "search", {"query": "rs123", "assembly": "hg38", "fields": "clinvar"}
    )

    assert result["success"] is True
    assert requests[0].url.host == "myvariant.info"
    assert requests[0].method == "GET"
    assert requests[0].url.params.get("assembly") == "hg38"
    assert requests[0].url.params.get("fields") == "clinvar,dbsnp.hg38"
    assert result["data"]["input_context"]["assembly"] == "hg38"
    await client.aclose()


@pytest.mark.unit
async def test_myvariant_resolve_uses_post_form_and_preserves_assembly(monkeypatch):
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json=[{"query": "rs699", "_id": "chr1:g.230710048A>G", "dbsnp": {"hg38": {}}}],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.biothings_service._provider_client", lambda: client
    )
    result = await execute_biothings(
        "variant",
        "resolve",
        {
            "identifiers": ["rs699"],
            "scopes": "dbsnp.rsid",
            "assembly": "hg38",
            "fields": "clinvar",
        },
    )

    assert result["success"] is True
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/v1/query"
    assert requests[0].headers["content-type"].startswith("application/x-www-form-urlencoded")
    form = parse_qs(requests[0].content.decode())
    assert form["q"] == ["rs699"]
    assert form["scopes"] == ["dbsnp.rsid"]
    assert form["assembly"] == ["hg38"]
    assert "dbsnp.hg38" in form["fields"][0].split(",")
    assert "assembly" not in requests[0].url.params
    assert result["data"]["assembly"] == "hg38"
    await client.aclose()


@pytest.mark.unit
async def test_biothings_stops_reading_when_provider_byte_budget_is_exceeded(monkeypatch):
    stream = _CountingByteStream([b"1234", b"5678", b"unused"])

    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.biothings_service._provider_client", lambda: client
    )
    monkeypatch.setattr("cygnusx.application.services.biothings_service._MAX_RESPONSE_BYTES", 6)

    result = await execute_biothings("gene", "get", {"identifier": "TP53"})

    assert result["success"] is False
    assert "exceeds the 2 MiB response budget" in result["summary"]
    assert stream.yielded == 2
    assert stream.closed is True
    await client.aclose()
