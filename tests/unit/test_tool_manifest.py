"""Contract tests for the provider-bound tool manifest."""

from types import SimpleNamespace

import pytest

from cygnusx.application.services.tool_manifest import build_tool_manifest


@pytest.mark.unit
def test_manifest_is_ordered_and_attributes_mcp_source() -> None:
    servers = [
        SimpleNamespace(
            id="server-1",
            name="cygnusx-research-data",
            tools=[SimpleNamespace(tool_name="cygnusx_gene_search")],
        )
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "cygnusx_gene_search",
                "description": "read-only gene search",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "runtime_tool",
                "description": "runtime-only",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    manifest = build_tool_manifest(tools, servers)

    assert manifest["tool_count"] == 2
    assert manifest["tools"][0]["server"] == "cygnusx-research-data"
    assert manifest["tools"][1]["server"] == "runtime"
    assert len(manifest["manifest_sha256"]) == 64
    assert all("secret" not in item for item in manifest["tools"])


@pytest.mark.unit
def test_manifest_ignores_non_function_payload() -> None:
    result = build_tool_manifest(
        [{"type": "function", "function": {"name": "ok"}}, {"secret": "x"}]
    )

    assert [item["name"] for item in result["tools"]] == ["ok"]


@pytest.mark.unit
def test_manifest_matches_provider_first_definition_after_name_deduplication() -> None:
    result = build_tool_manifest(
        [
            {"function": {"name": "same", "description": "first"}},
            {"function": {"name": "same", "description": "duplicate"}},
        ]
    )

    assert result["tool_count"] == 1
    assert result["tools"][0]["description"] == "first"
