"""Contract tests for secret-free assembled Agent tool snapshots."""

from types import SimpleNamespace

import pytest

from cygnusx.application.services.agent_tool_snapshot import build_agent_tool_snapshot


@pytest.mark.unit
def test_snapshot_contains_final_schema_and_filter_reasons_without_prompt() -> None:
    context = SimpleNamespace(
        agent=SimpleNamespace(agent_id="agent-test", name="Test Agent"),
        user_capabilities_customized=True,
        mcp_servers=[
            SimpleNamespace(
                id="server-1",
                name="cygnusx-research-data",
                is_enabled=True,
                tools=[SimpleNamespace(tool_name="cygnusx_gene_search")],
            )
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "cygnusx_gene_search",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        tool_filter_decisions=[
            {
                "tool_name": "cygnusx_hidden",
                "server": "cygnusx-research-data",
                "server_id": "server-1",
                "included": False,
                "reason": "pack_disabled",
            }
        ],
        system_prompt="do not export this",
    )

    snapshot = build_agent_tool_snapshot(context)

    assert snapshot["agent_id"] == "agent-test"
    assert snapshot["research_data_count"] == 1
    assert snapshot["final_tool_manifest"]["tool_count"] == 1
    assert snapshot["tool_filter_decisions"][0]["reason"] == "pack_disabled"
    assert "system_prompt" not in snapshot
    assert "do not export this" not in str(snapshot)

