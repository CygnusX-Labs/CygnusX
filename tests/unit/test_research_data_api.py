"""Tests for the authenticated research-data REST bridge."""

from __future__ import annotations

import pytest

from cygnusx.api.v1 import research_data
from cygnusx.infrastructure.mcp.research_preset import RESEARCH_TOOLS


@pytest.mark.unit
def test_research_rest_bridge_allowlist_matches_builtin_preset():
    assert {tool["name"] for tool in RESEARCH_TOOLS} == research_data._RESEARCH_TOOLS
    assert len(RESEARCH_TOOLS) == 28


@pytest.mark.unit
async def test_research_data_bridge_rejects_unregistered_tool(monkeypatch):
    async def fail(*_args, **_kwargs):
        pytest.fail("unregistered tools must not reach the provider service")

    monkeypatch.setattr(research_data, "execute_research", fail)
    result = await research_data.query_research_data("user-1", "arbitrary_url", {})
    assert result == {"success": False, "summary": "Research tool is not enabled", "data": None}


@pytest.mark.unit
async def test_research_data_bridge_delegates_fixed_tool(monkeypatch):
    calls = []

    async def execute(tool_name, arguments):
        calls.append((tool_name, arguments))
        return {"success": True, "data": {"ok": True}}

    monkeypatch.setattr(research_data, "execute_research", execute)
    result = await research_data.query_research_data(
        "user-1", "cygnusx_pathway_get", {"pathway_id": "R-HSA-1"}
    )
    assert result["success"] is True
    assert calls == [("cygnusx_pathway_get", {"pathway_id": "R-HSA-1"})]


@pytest.mark.unit
async def test_research_data_bridge_rejects_arguments_outside_tool_schema(monkeypatch):
    async def fail(*_args, **_kwargs):
        pytest.fail("invalid arguments must not reach the provider service")

    monkeypatch.setattr(research_data, "execute_research", fail)

    result = await research_data.query_research_data(
        "user-1",
        "cygnusx_pathway_get",
        {"pathway_id": "R-HSA-1", "upstream_url": "https://attacker.invalid"},
    )

    assert result == {
        "success": False,
        "summary": "Unknown arguments: upstream_url",
        "data": None,
    }


@pytest.mark.unit
async def test_research_data_bridge_allows_fixed_string_tools_and_rejects_unknown_network(
    monkeypatch,
):
    calls = []

    async def execute(tool_name, arguments):
        calls.append((tool_name, arguments))
        return {"success": True, "data": {"ok": True}}

    monkeypatch.setattr(research_data, "execute_research", execute)
    resolved = await research_data.query_research_data(
        "user-1", "cygnusx_string_resolve", {"identifier": "TP53", "taxon_id": 9606}
    )
    network = await research_data.query_research_data(
        "user-1",
        "cygnusx_string_network",
        {
            "string_id": "9606.ENSP00000269305",
            "taxon_id": 9606,
            "network_type": "physical",
        },
    )
    invalid = await research_data.query_research_data(
        "user-1",
        "cygnusx_string_network",
        {
            "string_id": "9606.ENSP00000269305",
            "taxon_id": 9606,
            "network_type": "unrestricted",
        },
    )

    assert resolved["success"] is True
    assert network["success"] is True
    assert "network_type" in invalid["summary"]
    assert calls == [
        ("cygnusx_string_resolve", {"identifier": "TP53", "taxon_id": 9606}),
        (
            "cygnusx_string_network",
            {
                "string_id": "9606.ENSP00000269305",
                "taxon_id": 9606,
                "network_type": "physical",
            },
        ),
    ]
