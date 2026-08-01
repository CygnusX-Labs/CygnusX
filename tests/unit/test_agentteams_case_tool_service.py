"""聊天协作 Case 工具的安全边界测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from omichub.application.services.agent_service import AgentService
from omichub.application.services.agentteams_case_tool_service import AgentTeamsCaseToolService
from omichub.core.exceptions import BusinessError


def test_case_tool_contract_is_confirmed_and_idempotent() -> None:
    from omichub.tools.schema_loader import schema_loader

    schema = schema_loader.get_tool("create_agentteams_case")

    assert schema is not None
    assert schema.requires_confirm is True
    assert schema.annotations.idempotent is True
    assert schema.extra["control_tool"] == "agentteams_case"
    assert schema.input_schema["required"] == ["objective", "project_id", "flow_id"]


def test_session_project_ownership_accepts_only_bound_project() -> None:
    service = AgentTeamsCaseToolService()

    assert service._session_owns_project({"project_ref": {"kind": "project", "id": "p-1"}}, "p-1")
    assert not service._session_owns_project({"project_ref": {"kind": "project", "id": "p-1"}}, "p-2")


def test_idempotency_record_reuses_recent_case_without_objective_storage() -> None:
    service = AgentTeamsCaseToolService()
    meta: dict[str, object] = {}
    service._bind_case(meta, "hash", "case-1", "交付目标", "received")

    reused = service._get_recent_case(meta, "hash")

    assert reused == {"case_id": "case-1", "title": "交付目标", "status": "received"}
    idempotency = meta["agentteams_case_idempotency"]
    assert isinstance(idempotency, dict)
    record: dict[str, Any] = idempotency["hash"]
    assert "objective" not in record


def test_sample_context_references_reject_raw_like_missing_reference() -> None:
    with pytest.raises(BusinessError, match="kind 和 id"):
        AgentTeamsCaseToolService._safe_refs([{"kind": "sample"}])

    assert AgentTeamsCaseToolService._safe_refs([{"kind": "sample", "id": "sample-1"}]) == [
        {"kind": "sample", "id": "sample-1"}
    ]


def test_chat_entry_switch_hides_case_tool_from_model() -> None:
    tools = [
        {"function": {"name": "workspace_read"}},
        {"function": {"name": "create_agentteams_case"}},
    ]

    filtered = AgentService._filter_runtime_builtin_tools(
        tools, agentteams_chat_entry_enabled=False
    )

    assert [tool["function"]["name"] for tool in filtered] == ["workspace_read"]


def test_case_tool_system_prompt_suffix_is_only_added_when_available() -> None:
    tools = [{"function": {"name": "create_agentteams_case"}}]

    assert AgentService._has_builtin_tool(tools, "create_agentteams_case")
    assert not AgentService._has_builtin_tool(tools, "parallel_subagents")


def test_chat_case_flow_whitelist_defaults_and_parsing() -> None:
    assert AgentTeamsCaseToolService._allowed_flows("rna_seq, atac_seq, rna_seq") == {
        "rna_seq",
        "atac_seq",
    }


@pytest.mark.asyncio
async def test_case_creation_requires_a_user_confirmation_after_card() -> None:
    class FakeDb:
        async def scalar(self, _query):
            return None

    context = SimpleNamespace(db=FakeDb(), session_id="session-1")
    meta = {
        "agentteams_case_confirmation": {
            "key": {"requested_at": datetime.now(UTC).isoformat()}
        }
    }

    with pytest.raises(BusinessError, match="用户在确认卡上确认"):
        await AgentTeamsCaseToolService._require_pending_confirmation(context, meta, "key")
