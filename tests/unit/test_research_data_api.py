"""Tests for the authenticated research-data REST bridge."""

from __future__ import annotations

import pytest

from cygnusx.api.v1 import research_data


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
