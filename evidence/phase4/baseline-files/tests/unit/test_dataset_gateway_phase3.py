"""Dataset capabilities share the Phase2 authority and remain fail-closed."""

from __future__ import annotations

import pytest

from cygnusx.application.schemas.agent_tools import capability_catalog
from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
from cygnusx.core.exceptions import AuthorizationError
from tests.unit.test_agent_tools_phase2 import env as env

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_dataset_capabilities_opt_in_and_same_schema_for_both_agents(env):
    gateway = AgentToolGateway(env.db)
    left = await gateway.context(env.owner, "mouse")
    right = await gateway.context(env.owner, "assistant")
    assert not any(c["capability_id"].startswith("dataset.") for c in gateway.catalog(left))
    env.settings.dataset_discovery_readonly = True
    a = {c["capability_id"]: c for c in gateway.catalog(left)}
    b = {c["capability_id"]: c for c in gateway.catalog(right)}
    assert a["dataset.discover"]["input_schema"] == b["dataset.discover"]["input_schema"]
    assert "analysis.prepare_from_dataset" in a
    assert "dataset.execute_import" not in a
    for schema in (c.input_schema for c in capability_catalog(include_dataset=True)):
        assert not {"owner_id", "project_id", "user_confirmed", "internal_path"}.intersection(
            schema.get("properties", {})
        )


async def test_dataset_execute_source_gate_precedes_audit(env):
    gateway = AgentToolGateway(env.db)
    context = await gateway.context(env.owner, "mouse")
    with pytest.raises(AuthorizationError):
        await gateway.invoke(
            context,
            "dataset.execute_import",
            {"proposal_id": "00000000-0000-0000-0000-000000000001"},
        )
