import httpx
import pytest
from fastmcp import FastMCP
from tools import research_resources as resources
from tools.research_common import close_provider_clients, provider_client


@pytest.mark.asyncio
async def test_fixed_provider_tool_groups_register_expected_names():
    mcp = FastMCP("research-resource-test")
    resources.register_genome(mcp, None)
    resources.register_plant_te(mcp, None)
    resources.register_expression(mcp, None)
    resources.register_pathways(mcp, None)
    resources.register_protein(mcp, None)
    resources.register_clinical_literature(mcp, None)
    resources.register_string(mcp, None)

    names = {tool.name for tool in await mcp.list_tools()}
    assert len(names) == 28
    assert "cygnusx_literature_annotations" in names
    assert "cygnusx_string_resolve" in names
    assert "cygnusx_te_asset" not in names
    assert "cygnusx_expression_query" not in names
    assert "cygnusx_pathway_analyze" not in names

    string_mcp = FastMCP("string-resource-group-test")
    resources.register_string(string_mcp, None)
    string_names = {tool.name for tool in await string_mcp.list_tools()}
    assert string_names == {"cygnusx_string_resolve", "cygnusx_string_network"}


@pytest.mark.asyncio
async def test_provider_transport_rejects_unregistered_hosts_and_paths():
    with pytest.raises(ValueError, match="unknown provider"):
        await resources._request_json("https://attacker.example")
    with pytest.raises(ValueError, match="relative and fixed"):
        await resources._request_json("gramene", "../proxy")
    with pytest.raises(ValueError, match="relative and fixed"):
        await resources._request_json("gramene", "/search")


def test_clinvar_xml_projection_is_bounded_and_keeps_distinct_assertions():
    import xml.etree.ElementTree as ET

    root = ET.fromstring(
        "<VariationArchive><GermlineClassification>Pathogenic</GermlineClassification>"
        "<Oncogenicity>Uncertain</Oncogenicity></VariationArchive>"
    )
    facts = resources._xml_projection(root)
    assert [fact["element"] for fact in facts] == ["GermlineClassification", "Oncogenicity"]
    assert [fact["text"] for fact in facts] == ["Pathogenic", "Uncertain"]


@pytest.mark.asyncio
async def test_clinvar_xml_request_rejects_dtd_and_entity_declarations(monkeypatch):
    async def response(_request):
        return httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            content=b'<!DOCTYPE x [<!ENTITY leak "unsafe">]><x>&leak;</x>',
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    monkeypatch.setattr(resources, "provider_client", lambda *_args: client)
    with pytest.raises(ValueError, match="DTD and entity"):
        await resources._request_xml("clinvar", "efetch.fcgi", {"id": "VCV000000001"})
    await client.aclose()


@pytest.mark.asyncio
async def test_external_clinvar_adapter_routes_typed_ids_and_rejects_allele(monkeypatch):
    calls = []

    async def request_xml(provider, path, params):
        calls.append((provider, path, params))
        if params.get("rettype") == "clinvarset":
            return resources.ET.fromstring(
                '<ClinVarResult-Set><ClinVarSet><ClinVarAccession Acc="RCV000000123" '
                'Version="7" Type="RCV" /></ClinVarSet></ClinVarResult-Set>'
            )
        return resources.ET.fromstring(
            '<ClinVarResult-Set><VariationArchive Accession="VCV000000123" Version="3" '
            'VariationID="14206"><ClinVarAccession Accession="SCV000000456" '
            'Version="2" Type="SCV" /></VariationArchive></ClinVarResult-Set>'
        )

    async def request_json(provider, path, params=None, **_kwargs):
        calls.append((provider, path, params))
        return {"esearchresult": {"idlist": ["14206"]}}

    monkeypatch.setattr(resources, "_request_xml", request_xml)
    monkeypatch.setattr(resources, "_request_json", request_json)
    mcp = FastMCP("clinvar-typed-id-test")
    resources.register_clinical_literature(mcp, None)

    rcv = await mcp.call_tool(
        "cygnusx_clinvar_get", {"identifier": "RCV000000123.7", "identifier_type": "RCV"}
    )
    assert rcv.structured_content["success"] is True
    assert calls[-1][2]["rettype"] == "clinvarset"

    scv = await mcp.call_tool(
        "cygnusx_clinvar_get", {"identifier": "SCV000000456.2", "identifier_type": "SCV"}
    )
    assert scv.structured_content["success"] is True
    assert calls[-2][2]["term"] == "SCV000000456[clv_acc]"
    assert calls[-1][2]["id"] == "14206"

    variation = await mcp.call_tool(
        "cygnusx_clinvar_get", {"identifier": "14206", "identifier_type": "VariationID"}
    )
    assert variation.structured_content["success"] is True
    assert calls[-1][2]["is_variationid"] == "true"

    allele = await mcp.call_tool(
        "cygnusx_clinvar_get", {"identifier": "12345", "identifier_type": "AlleleID"}
    )
    assert allele.structured_content["success"] is False


def test_fixed_provider_registry_uses_https_only():
    assert all(url.startswith("https://") for url in resources.PROVIDERS.values())


def test_result_envelopes_obey_3000_utf8_byte_budget():
    from tools.research_common import MAX_TOOL_RESULT_BYTES, envelope

    result = envelope(True, "检索结果", {"hits": [{"text": "基因" * 5000} for _ in range(20)]})
    import json

    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(payload) <= MAX_TOOL_RESULT_BYTES
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_provider_client_is_reused_and_closed_by_lifespan_hook():
    first = provider_client(resources.TIMEOUT)
    second = provider_client(resources.TIMEOUT)
    assert first is second
    await close_provider_clients()
    assert first.is_closed


@pytest.mark.asyncio
async def test_research_tools_use_authenticated_platform_bridge_when_api_is_present():
    class FakeAPI:
        async def research_data(self, tool_name, arguments):
            return {"success": True, "tool": tool_name, "arguments": arguments}

    mcp = FastMCP("research-bridge-test")
    resources.register_pathways(mcp, FakeAPI())
    result = await mcp.call_tool("cygnusx_pathway_get", {"pathway_id": "R-HSA-1"})
    assert result.structured_content == {
        "success": True,
        "tool": "cygnusx_pathway_get",
        "arguments": {"pathway_id": "R-HSA-1"},
    }


@pytest.mark.asyncio
async def test_research_bridge_omits_unset_optional_arguments():
    class FakeAPI:
        async def research_data(self, tool_name, arguments):
            return {"success": True, "tool": tool_name, "arguments": arguments}

    mcp = FastMCP("research-optional-bridge-test")
    resources.register_clinical_literature(mcp, FakeAPI())
    result = await mcp.call_tool("cygnusx_clinvar_get", {"vcv_accession": "VCV000014206"})

    assert result.structured_content == {
        "success": True,
        "tool": "cygnusx_clinvar_get",
        "arguments": {"vcv_accession": "VCV000014206"},
    }


@pytest.mark.asyncio
async def test_string_external_tools_bridge_to_platform_with_fixed_signatures():
    calls = []

    class FakeAPI:
        async def research_data(self, tool_name, arguments):
            calls.append((tool_name, arguments))
            return {"success": True, "tool": tool_name, "arguments": arguments}

    mcp = FastMCP("string-bridge-test")
    resources.register_string(mcp, FakeAPI())
    resolved = await mcp.call_tool(
        "cygnusx_string_resolve", {"identifier": "TP53", "taxon_id": 9606, "limit": 5}
    )
    network = await mcp.call_tool(
        "cygnusx_string_network",
        {
            "string_id": "9606.ENSP00000269305",
            "taxon_id": 9606,
            "network_type": "physical",
            "limit": 3,
        },
    )

    assert resolved.structured_content["success"] is True
    assert network.structured_content["success"] is True
    assert calls == [
        (
            "cygnusx_string_resolve",
            {"identifier": "TP53", "taxon_id": 9606, "limit": 5},
        ),
        (
            "cygnusx_string_network",
            {
                "string_id": "9606.ENSP00000269305",
                "taxon_id": 9606,
                "network_type": "physical",
                "required_score": 400,
                "limit": 3,
            },
        ),
    ]


@pytest.mark.asyncio
async def test_string_external_resolve_keeps_candidates_and_filters_wrong_taxon(monkeypatch):
    async def request_tsv(method, params):
        assert method == "get_string_ids"
        assert params["species"] == 9606
        return [
            {"stringId": "9606.ENSP00000269305", "ncbiTaxonId": "9606", "preferredName": "TP53"},
            {"stringId": "10090.ENSMUSP00000000001", "ncbiTaxonId": "10090", "preferredName": "Trp53"},
        ]

    monkeypatch.setattr(resources, "_request_string_tsv", request_tsv)
    mcp = FastMCP("string-direct-resolution-test")
    resources.register_string(mcp, None)
    result = await mcp.call_tool(
        "cygnusx_string_resolve", {"identifier": "TP53", "taxon_id": 9606}
    )

    assert result.structured_content["success"] is True
    payload = result.structured_content["data"]
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["string_id"] == "9606.ENSP00000269305"


@pytest.mark.asyncio
async def test_string_external_regulatory_rows_name_directional_partner(monkeypatch):
    async def request_tsv(method, params):
        assert method == "interaction_partners"
        assert params["network_type"] == "regulatory"
        return [
            {
                "source_string_id": "9606.ENSP00000269305",
                "source_preferred_name": "TP53",
                "target_string_id": "9606.ENSP00000258149",
                "target_preferred_name": "MDM2",
                "combined_score": "0.996",
            }
        ]

    monkeypatch.setattr(resources, "_request_string_tsv", request_tsv)
    mcp = FastMCP("string-regulatory-projection-test")
    resources.register_string(mcp, None)
    result = await mcp.call_tool(
        "cygnusx_string_network",
        {
            "string_id": "9606.ENSP00000269305",
            "taxon_id": 9606,
            "network_type": "regulatory",
        },
    )

    assert result.structured_content["success"] is True
    partner = result.structured_content["data"]["partners"][0]
    assert partner["partner_string_id"] == "9606.ENSP00000258149"
    assert partner["partner_preferred_name"] == "MDM2"
    assert partner["source_string_id"] == "9606.ENSP00000269305"
    assert partner["target_string_id"] == "9606.ENSP00000258149"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "body", "error"),
    [
        ("text/html", b"<html>upstream error</html>", "non-TSV"),
        (
            "text/tab-separated-values",
            b"header\n" + b"x" * (resources.MAX_RESPONSE_BYTES + 1),
            "exceeds 2 MiB",
        ),
    ],
)
async def test_string_direct_adapter_rejects_html_and_oversized_bodies(
    monkeypatch, content_type, body, error
):
    async def response(_request):
        return httpx.Response(200, headers={"content-type": content_type}, content=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    monkeypatch.setattr(resources, "provider_client", lambda *_args: client)
    monkeypatch.setattr(resources, "_STRING_LAST_REQUEST", 0.0)
    with pytest.raises(ValueError, match=error):
        await resources._request_string_tsv("get_string_ids", {"identifiers": "TP53"})
    await client.aclose()


@pytest.mark.asyncio
async def test_reactome_external_adapter_uses_text_version_endpoint(monkeypatch):
    calls = []

    async def request_text(provider, path, *, accept="text/plain"):
        calls.append(("text", provider, path, accept))
        return "93"

    async def request_json(provider, path="", **kwargs):
        calls.append(("json", provider, path, kwargs))
        return {"stId": "R-HSA-1"}

    monkeypatch.setattr(resources, "_request_text", request_text)
    monkeypatch.setattr(resources, "_request_json", request_json)
    mcp = FastMCP("reactome-route-test")
    resources.register_pathways(mcp, None)

    result = await mcp.call_tool("cygnusx_pathway_get", {"pathway_id": "R-HSA-1"})

    assert result.structured_content["success"] is True
    assert result.structured_content["data"]["release"] == "93"
    assert calls[0] == ("text", "reactome", "database/version", "text/plain")
    assert calls[1][0:3] == ("json", "reactome", "query/R-HSA-1")


@pytest.mark.asyncio
async def test_reactome_text_request_overrides_shared_json_accept_header(monkeypatch):
    requests = []

    async def handle(request):
        requests.append(request)
        return httpx.Response(200, text="93")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(resources, "provider_client", lambda *_args: client)

    result = await resources._request_text("reactome", "database/version")

    assert result == "93"
    assert requests[0].headers["accept"] == "text/plain"
    await client.aclose()


@pytest.mark.asyncio
async def test_europe_pmc_external_adapter_uses_article_core_endpoint(monkeypatch):
    calls = []

    async def request_json(provider, path="", **kwargs):
        calls.append((provider, path, kwargs))
        return {"id": "29972563", "source": "MED", "title": "Example"}

    monkeypatch.setattr(resources, "_request_json", request_json)
    mcp = FastMCP("europe-pmc-route-test")
    resources.register_clinical_literature(mcp, None)

    result = await mcp.call_tool(
        "cygnusx_literature_get", {"source": "MED", "article_id": "29972563"}
    )

    assert result.structured_content["success"] is True
    assert calls == [
        (
            "europepmc",
            "article/MED/29972563",
            {"params": {"format": "json", "resultType": "core"}},
        )
    ]
