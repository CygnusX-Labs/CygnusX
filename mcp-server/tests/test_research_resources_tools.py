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

    names = {tool.name for tool in await mcp.list_tools()}
    assert len(names) == 26
    assert "cygnusx_te_asset" not in names
    assert "cygnusx_expression_query" not in names
    assert "cygnusx_pathway_analyze" not in names


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
