"""AgentTeams user proxy tests: browser-facing access stays requester-scoped."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from omichub.api.v1.agentteams import (
    AgentTeamsCaseCreateRequest,
    _is_chat_case_flow_allowed,
    create_case,
)
from omichub.application.services.agentteams_service import AgentTeamsService
from omichub.application.services.project_service import ProjectService
from omichub.core.config import Settings
from omichub.core.exceptions import BusinessError, NotFoundError


@pytest.fixture
def service() -> AgentTeamsService:
    return AgentTeamsService(
        Settings(
            agentteams_bridge_enabled=True,
            agentteams_bridge_url="http://bridge.test",
            agentteams_bridge_manager_token="manager-token",
            agentteams_bridge_data_steward_token="steward-token",
            agentteams_bridge_approval_token="approval-token",
            agentteams_bridge_workflow_operator_token="operator-token",
            # 显式置空：避免仓库 .env 中的 AGENTTEAMS_ELEMENT_URL 污染"未配置"语义
            agentteams_element_url="",
        )
    )


def test_direct_case_api_flow_guard_uses_configured_and_registry_flows(monkeypatch) -> None:
    monkeypatch.setattr(
        "omichub.api.v1.agentteams.get_settings",
        lambda: Settings(agentteams_chat_flow_whitelist="approved-flow"),
    )
    monkeypatch.setattr(
        "omichub.api.v1.agentteams.get_flow_registry",
        lambda: type("Registry", (), {"bridge_flow_ids": lambda self: {"registry-flow"}})(),
    )

    assert _is_chat_case_flow_allowed("approved-flow")
    assert _is_chat_case_flow_allowed("registry-flow")
    assert not _is_chat_case_flow_allowed("unapproved-flow")


@pytest.mark.asyncio
async def test_direct_case_api_rejects_project_not_owned_by_requester(monkeypatch) -> None:
    request = AgentTeamsCaseCreateRequest(
        project_id=str(uuid4()),
        intent="bulk_rnaseq_delivery",
        flow_id="approved-flow",
        sample_sheet=[{"sample": "S01"}],
    )
    service = SimpleNamespace(create_case=AsyncMock())

    monkeypatch.setattr("omichub.api.v1.agentteams._is_chat_case_flow_allowed", lambda _flow: True)

    async def reject_project(*_args, **_kwargs):
        raise NotFoundError("项目不存在")

    monkeypatch.setattr(ProjectService, "get_project", reject_project)

    with pytest.raises(NotFoundError, match="项目不存在"):
        await create_case(request, str(uuid4()), service, SimpleNamespace())
    service.create_case.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_case_api_rejects_non_whitelisted_flow_before_project_lookup(
    monkeypatch,
) -> None:
    request = AgentTeamsCaseCreateRequest(
        project_id=str(uuid4()),
        intent="bulk_rnaseq_delivery",
        flow_id="not-allowed",
        sample_sheet=[{"sample": "S01"}],
    )
    service = SimpleNamespace(create_case=AsyncMock())
    get_project = AsyncMock()
    monkeypatch.setattr(ProjectService, "get_project", get_project)
    monkeypatch.setattr("omichub.api.v1.agentteams._is_chat_case_flow_allowed", lambda _flow: False)

    with pytest.raises(BusinessError, match="白名单"):
        await create_case(request, str(uuid4()), service, SimpleNamespace())
    get_project.assert_not_awaited()
    service.create_case.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_case_api_creates_case_for_owned_project(monkeypatch) -> None:
    user_id = uuid4()
    project_id = uuid4()
    request = AgentTeamsCaseCreateRequest(
        project_id=str(project_id),
        intent="bulk_rnaseq_delivery",
        flow_id="approved-flow",
        sample_sheet=[{"sample": "S01"}],
        comparisons=[{"control": "control", "treatment": "treatment"}],
    )
    service = SimpleNamespace(create_case=AsyncMock(return_value={"case_id": "bioops_001"}))
    get_project = AsyncMock(return_value={"id": str(project_id)})
    monkeypatch.setattr(ProjectService, "get_project", get_project)
    monkeypatch.setattr("omichub.api.v1.agentteams._is_chat_case_flow_allowed", lambda _flow: True)

    response = await create_case(request, str(user_id), service, SimpleNamespace())

    assert response == {"case_id": "bioops_001"}
    get_project.assert_awaited_once_with(user_id, project_id)
    service.create_case.assert_awaited_once()
    assert service.create_case.await_args.kwargs["project_id"] == str(project_id)
    assert service.create_case.await_args.kwargs["requester_ref"] == str(user_id)


@pytest.mark.asyncio
async def test_direct_case_api_allows_general_workspace_case(monkeypatch) -> None:
    user_id = uuid4()
    project_id = uuid4()
    request = AgentTeamsCaseCreateRequest(
        project_id=str(project_id), intent="build a treeplot from fasta files"
    )
    service = SimpleNamespace(create_case=AsyncMock(return_value={"case_id": "general_001"}))
    monkeypatch.setattr(ProjectService, "get_project", AsyncMock(return_value={"id": str(project_id)}))

    response = await create_case(request, str(user_id), service, SimpleNamespace())

    assert response == {"case_id": "general_001"}
    assert service.create_case.await_args.kwargs["flow_id"] is None
    assert service.create_case.await_args.kwargs["sample_sheet"] is None


@pytest.mark.asyncio
async def test_get_case_rejects_other_requester(service: AgentTeamsService, monkeypatch) -> None:
    async def fake_request(path: str, **kwargs):
        assert path == "/v1/cases/case-other"
        return {"case_id": "case-other", "requester_ref": "other-user"}

    monkeypatch.setattr(service, "_request", fake_request)

    with pytest.raises(BusinessError, match="无权查看"):
        await service.get_case("case-other", "current-user")


@pytest.mark.asyncio
async def test_create_case_starts_planning_with_the_selected_flow(
    service: AgentTeamsService, monkeypatch
) -> None:
    captured: list[tuple[str, dict]] = []

    async def fake_request(path: str, **kwargs):
        captured.append((path, kwargs))
        return {"case_id": "bioops_001", "requester_ref": "current-user"}

    monkeypatch.setattr(service, "_request", fake_request)

    response = await service.create_case(
        case_id="bioops_001",
        project_id="project-1",
        intent="bulk_rnaseq_delivery",
        requester_ref="current-user",
        flow_id="rna_seq",
        sample_sheet=[{"sample": "S01", "group": "control"}],
        comparisons=[{"control": "control", "treatment": "treatment"}],
    )

    assert response["requester_ref"] == "current-user"
    assert captured == [
        (
            "/v1/cases",
            {
                "method": "POST",
                "json": {
                    "case_id": "bioops_001",
                    "project_ref": {"kind": "project", "id": "project-1"},
                    "intent": "bulk_rnaseq_delivery",
                    "requester_ref": "current-user",
                    "execution_mode": "cluster_case",
                    "flow_id": "rna_seq",
                },
            },
        ),
    ]


@pytest.mark.asyncio
async def test_list_cases_forwards_scoped_filters(service: AgentTeamsService, monkeypatch) -> None:
    captured = {}

    async def fake_request(path: str, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return {"items": [], "total": 0, "next_cursor": None}

    monkeypatch.setattr(service, "_request", fake_request)

    await service.list_cases(
        "current-user",
        case_status="approval_pending",
        project_id="project-1",
        cursor="case-previous",
        limit=10,
    )

    assert captured == {
        "path": "/v1/cases",
        "params": {
            "requester_ref": "current-user",
            "limit": 10,
            "status": "approval_pending",
            "project_id": "project-1",
            "cursor": "case-previous",
        },
    }


@pytest.mark.asyncio
async def test_case_event_stream_checks_owner_before_connecting_to_bridge(
    service: AgentTeamsService, monkeypatch
) -> None:
    async def fake_owner(case_id: str, requester_ref: str):
        assert (case_id, requester_ref) == ("bioops_001", "current-user")
        return {"case_id": case_id, "requester_ref": requester_ref}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self):
            yield 'data: {"event_id":"evt-1","event_type":"case.created"}'

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == "http://bridge.test"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, method: str, path: str, **kwargs):
            assert method == "GET"
            assert path == "/v1/cases/bioops_001/events/stream"
            assert kwargs["params"] == {"watch_seconds": 1, "cursor": "evt-0"}
            assert kwargs["headers"]["X-Bridge-Identity"] == "bioops-manager"
            return FakeStream()

    monkeypatch.setattr(service, "_get_case_for_requester", fake_owner)
    monkeypatch.setattr(
        "omichub.application.services.agentteams_service.httpx.AsyncClient", FakeClient
    )

    events = [
        event
        async for event in service.stream_case_events(
            "bioops_001", "current-user", cursor="evt-0", watch_seconds=1
        )
    ]

    assert events == [{"event_id": "evt-1", "event_type": "case.created"}]


@pytest.mark.asyncio
async def test_admin_resource_snapshot_groups_cases_by_team(
    service: AgentTeamsService, monkeypatch
) -> None:
    async def fake_health():
        return {"connection": {"connected": True}, "workers": []}

    async def fake_request(path: str, **kwargs):
        assert path == "/v1/cases"
        assert kwargs == {"params": {"limit": 100}}
        return {
            "items": [
                {"case_id": "case-a", "team_id": "team-red", "preflight_input": {}},
                {"case_id": "case-b", "team_id": "team-red", "task_specs": {}},
                {"case_id": "case-c", "team_id": "team-blue"},
            ],
            "total": 3,
        }

    monkeypatch.setattr(service, "health_check", fake_health)
    monkeypatch.setattr(service, "_request", fake_request)

    snapshot = await service.admin_resource_snapshot()

    assert snapshot["total_cases"] == 3
    assert snapshot["teams"] == [
        {"team_id": "team-blue", "case_count": 1},
        {"team_id": "team-red", "case_count": 2},
    ]
    assert "preflight_input" not in snapshot["cases"][0]
    assert "task_specs" not in snapshot["cases"][1]


@pytest.mark.asyncio
async def test_case_owner_approval_submits_with_separate_bridge_identities(
    service: AgentTeamsService, monkeypatch
) -> None:
    requests: list[tuple[str, dict]] = []

    async def fake_request(path: str, **kwargs):
        requests.append((path, kwargs))
        if path == "/v1/cases/bioops_001":
            return {
                "case_id": "bioops_001",
                "requester_ref": "current-user",
                "status": "approval_pending",
                "flow_id": "rna_seq",
                "project_ref": {"kind": "project", "id": "project-1"},
                "preflight_input": {
                    "flow_id": "rna_seq",
                    "sample_sheet": [{"sample": "S01", "group": "control"}],
                    "comparisons": [{"control": "control", "treatment": "treatment"}],
                },
            }
        return {"case_id": "bioops_001"}

    async def fake_request_as(identity: str, token: str, path: str, **kwargs):
        requests.append((path, {"identity": identity, "token": token, **kwargs}))
        if path == "/v1/approvals":
            return {"token": "short-lived-approval-token"}
        return {"work_item_id": "submit-01", "status": "queued"}

    monkeypatch.setattr(service, "_request", fake_request)
    monkeypatch.setattr(service, "_request_as", fake_request_as)

    result = await service.approve_and_submit_task(
        case_id="bioops_001",
        requester_ref="current-user",
        task_name="RNA delivery",
    )

    assert result == {"work_item_id": "submit-01", "status": "queued"}
    assert requests[1][0] == "/v1/cases/bioops_001/work-items"
    assert requests[2] == (
        "/v1/approvals",
        {
            "identity": "approval-authority",
            "token": "approval-token",
            "method": "POST",
            "json": {
                "case_id": "bioops_001",
                "work_item_id": "submit-01",
                "action": "submit_task",
                "flow_id": "rna_seq",
            },
        },
    )
    assert requests[3] == (
        "/v1/approved-submissions",
        {
            "identity": "approval-authority",
            "token": "approval-token",
            "method": "POST",
            "json": {
                "case_id": "bioops_001",
                "work_item_id": "submit-01",
                "idempotency_key": "bioops_001-submit-v1",
                "approval_token": "short-lived-approval-token",
                "task": {
                    "flow_id": "rna_seq",
                    "name": "RNA delivery",
                    "sample_sheet": [{"sample": "S01", "group": "control"}],
                    "comparisons": [{"control": "control", "treatment": "treatment"}],
                    "execution_mode": "cluster",
                },
            },
        },
    )


@pytest.mark.asyncio
async def test_case_owner_approval_executes_frozen_general_plan(
    service: AgentTeamsService, monkeypatch
) -> None:
    requests: list[tuple[str, dict]] = []

    async def fake_request(path: str, **kwargs):
        requests.append((path, kwargs))
        return {"case_id": "general_001", "requester_ref": "current-user", "status": "approval_pending", "plan_hash": "abc"}

    async def fake_request_as(identity: str, token: str, path: str, **kwargs):
        requests.append((path, {"identity": identity, "token": token, **kwargs}))
        return {"token": "general-approval"} if path == "/v1/approvals" else {"status": "approved"}

    monkeypatch.setattr(service, "_request", fake_request)
    monkeypatch.setattr(service, "_request_as", fake_request_as)

    result = await service.approve_and_submit_task(case_id="general_001", requester_ref="current-user", task_name="ignored")

    assert result == {"status": "approved"}
    assert requests[1][0] == "/v1/approvals"
    assert requests[1][1]["json"] == {"case_id": "general_001", "action": "execute_plan"}
    assert requests[2][0] == "/v1/general-plans/execute"


@pytest.mark.asyncio
async def test_submit_rejects_case_without_passed_preflight(
    service: AgentTeamsService, monkeypatch
) -> None:
    async def fake_request(path: str, **kwargs):
        if path == "/v1/cases/bioops_001":
            return {
                "case_id": "bioops_001",
                "requester_ref": "current-user",
                "status": "preflight_blocked",
            }
        raise AssertionError(f"Unexpected request: {path}")

    monkeypatch.setattr(service, "_request", fake_request)

    with pytest.raises(BusinessError, match="尚未满足人工审批"):
        await service.approve_and_submit_task(
            case_id="bioops_001",
            requester_ref="current-user",
            task_name="RNA delivery",
        )


@pytest.mark.asyncio
async def test_public_case_view_strips_internal_preflight_input(
    service: AgentTeamsService, monkeypatch
) -> None:
    async def fake_request(path: str, **kwargs):
        return {
            "case_id": "bioops_001",
            "requester_ref": "current-user",
            "preflight_input": {"sample_sheet": [{"sample": "S01"}]},
            "task_specs": [{"sample_sheet": [{"sample": "S01"}]}],
        }

    monkeypatch.setattr(service, "_request", fake_request)

    case = await service.get_case("bioops_001", "current-user")

    assert "preflight_input" not in case
    assert "task_specs" not in case


@pytest.fixture
def element_settings() -> Settings:
    return Settings(
        agentteams_bridge_enabled=True,
        agentteams_bridge_url="http://bridge.test",
        agentteams_bridge_manager_token="manager-token",
        agentteams_bridge_data_steward_token="steward-token",
        agentteams_bridge_approval_token="approval-token",
        agentteams_bridge_workflow_operator_token="operator-token",
        agentteams_element_url="https://element.example/#/room/!global:example.org",
    )


@pytest.mark.asyncio
async def test_chat_room_without_case_id_uses_global_room(element_settings: Settings) -> None:
    service = AgentTeamsService(element_settings)

    result = await service.chat_room(None, "current-user")

    assert result == {
        "available": True,
        "element_url": "https://element.example/#/room/!global:example.org",
        "reason": None,
        "case_id": None,
        "source": "global",
    }


@pytest.mark.asyncio
async def test_chat_room_without_case_id_reports_not_configured(service: AgentTeamsService) -> None:
    result = await service.chat_room(None, "current-user")

    assert result == {
        "available": False,
        "element_url": "",
        "reason": "not_configured",
        "case_id": None,
        "source": "global",
    }


@pytest.mark.asyncio
async def test_chat_room_prefers_case_room_url(element_settings: Settings, monkeypatch) -> None:
    service = AgentTeamsService(element_settings)

    async def fake_request(path: str, **kwargs):
        assert path == "/v1/cases/bioops_001"
        return {
            "case_id": "bioops_001",
            "requester_ref": "current-user",
            "element_room_url": "https://element.example/#/room/!case:example.org",
            "preflight_input": {"sample_sheet": [{"sample": "S01"}]},
        }

    monkeypatch.setattr(service, "_request", fake_request)

    result = await service.chat_room("bioops_001", "current-user")

    assert result == {
        "available": True,
        "element_url": "https://element.example/#/room/!case:example.org",
        "reason": None,
        "case_id": "bioops_001",
        "source": "case",
    }


@pytest.mark.asyncio
async def test_chat_room_falls_back_to_global_when_case_has_no_room(
    element_settings: Settings, monkeypatch
) -> None:
    service = AgentTeamsService(element_settings)

    async def fake_request(path: str, **kwargs):
        return {"case_id": "bioops_001", "requester_ref": "current-user", "element_room_url": ""}

    monkeypatch.setattr(service, "_request", fake_request)

    result = await service.chat_room("bioops_001", "current-user")

    assert result["element_url"] == "https://element.example/#/room/!global:example.org"
    assert result["source"] == "global"
    assert result["case_id"] == "bioops_001"


@pytest.mark.asyncio
async def test_chat_room_rejects_case_room_url_with_access_token(
    element_settings: Settings, monkeypatch
) -> None:
    service = AgentTeamsService(element_settings)

    async def fake_request(path: str, **kwargs):
        return {
            "case_id": "bioops_001",
            "requester_ref": "current-user",
            "element_room_url": "https://element.example/#/room/!case:example.org?access_token=secret",
        }

    monkeypatch.setattr(service, "_request", fake_request)

    result = await service.chat_room("bioops_001", "current-user")

    assert result["element_url"] == "https://element.example/#/room/!global:example.org"
    assert result["source"] == "global"


@pytest.mark.asyncio
async def test_chat_room_propagates_case_access_errors(
    element_settings: Settings, monkeypatch
) -> None:
    service = AgentTeamsService(element_settings)

    async def fake_request(path: str, **kwargs):
        return {"case_id": "bioops_001", "requester_ref": "other-user"}

    monkeypatch.setattr(service, "_request", fake_request)

    with pytest.raises(BusinessError, match="无权查看"):
        await service.chat_room("bioops_001", "current-user")


def test_bridge_proxy_is_unavailable_without_all_server_settings() -> None:
    assert (
        AgentTeamsService(
            Settings(
                agentteams_bridge_enabled=False,
                agentteams_bridge_url="",
                agentteams_bridge_manager_token="",
                agentteams_bridge_data_steward_token="",
                agentteams_bridge_approval_token="",
                agentteams_bridge_workflow_operator_token="",
            )
        ).available
        is False
    )
    assert (
        AgentTeamsService(
            Settings(
                agentteams_bridge_enabled=True,
                agentteams_bridge_url="",
                agentteams_bridge_manager_token="",
                agentteams_bridge_data_steward_token="",
                agentteams_bridge_approval_token="",
                agentteams_bridge_workflow_operator_token="",
            )
        ).available
        is False
    )


def test_production_rejects_incomplete_agentteams_bridge_settings() -> None:
    with pytest.raises(ValueError, match="AgentTeams Bridge"):
        Settings(
            app_env="production",
            app_secret_key="app-secret",
            jwt_secret_key="jwt-secret",
            redis_password="redis-secret",
            ai_provider_key_encryption_key="encryption-secret",
            workflow_monitor_enabled=False,
            agentteams_bridge_enabled=True,
            agentteams_bridge_url="",
            agentteams_bridge_manager_token="",
            agentteams_bridge_data_steward_token="",
            agentteams_bridge_approval_token="",
            agentteams_bridge_workflow_operator_token="",
        )


def test_production_rejects_template_agentteams_manager_token() -> None:
    with pytest.raises(ValueError, match="AgentTeams Bridge"):
        Settings(
            app_env="production",
            app_secret_key="app-secret",
            jwt_secret_key="jwt-secret",
            redis_password="redis-secret",
            ai_provider_key_encryption_key="encryption-secret",
            workflow_monitor_enabled=False,
            agentteams_bridge_enabled=True,
            agentteams_bridge_url="http://bridge.test",
            agentteams_bridge_manager_token="replace-with-bioops-manager-token",
            agentteams_bridge_data_steward_token="steward-token",
            agentteams_bridge_approval_token="approval-token",
            agentteams_bridge_workflow_operator_token="operator-token",
        )


@pytest.mark.asyncio
async def test_refresh_case_reconciles_only_after_owner_check(
    service: AgentTeamsService, monkeypatch
) -> None:
    requests: list[tuple[str, dict]] = []

    async def fake_request(path: str, **kwargs):
        requests.append((path, kwargs))
        if path == "/v1/cases/bioops_001" and kwargs.get("method", "GET") == "GET":
            return {
                "case_id": "bioops_001",
                "requester_ref": "current-user",
                "status": "executing",
                "preflight_input": {"sample_sheet": [{"sample": "S01"}]},
                "task_specs": [{"sample_sheet": [{"sample": "S01"}]}],
            }
        if path == "/v1/cases/bioops_001/reconcile":
            assert kwargs["method"] == "POST"
            return {
                "case_id": "bioops_001",
                "requester_ref": "current-user",
                "status": "quality_running",
                "preflight_input": {"sample_sheet": [{"sample": "S01"}]},
                "task_specs": [{"sample_sheet": [{"sample": "S01"}]}],
            }
        raise AssertionError(f"Unexpected request: {path}")

    monkeypatch.setattr(service, "_request", fake_request)

    case = await service.refresh_case("bioops_001", "current-user")

    assert case["status"] == "quality_running"
    assert "preflight_input" not in case
    assert "task_specs" not in case
    assert [path for path, _ in requests] == [
        "/v1/cases/bioops_001",
        "/v1/cases/bioops_001/reconcile",
    ]


@pytest.mark.asyncio
async def test_status_uses_bridge_health_not_only_configuration(
    service: AgentTeamsService, monkeypatch
) -> None:
    async def healthy_request(path: str, **kwargs):
        assert path == "/healthz"
        return {"status": "ok"}

    monkeypatch.setattr(service, "_request", healthy_request)
    assert await service.is_connected() is True

    async def failed_request(path: str, **kwargs):
        raise BusinessError("Agent 协作中心暂时不可用")

    monkeypatch.setattr(service, "_request", failed_request)
    assert await service.is_connected() is False


@pytest.mark.asyncio
async def test_connection_status_distinguishes_missing_configuration_from_unreachable_bridge(
    service: AgentTeamsService, monkeypatch
) -> None:
    async def failed_request(path: str, **kwargs):
        assert path == "/healthz"
        raise BusinessError("Agent 协作中心暂时不可用")

    monkeypatch.setattr(service, "_request", failed_request)
    assert await service.connection_status() == {
        "available": False,
        "enabled": True,
        "configured": True,
        "connected": False,
        "configuration_source": "environment",
        "reason": "bridge_unreachable",
    }

    unconfigured = AgentTeamsService(
        Settings(
            agentteams_bridge_enabled=False,
            agentteams_bridge_url="",
            agentteams_bridge_manager_token="",
            agentteams_bridge_data_steward_token="",
            agentteams_bridge_approval_token="",
            agentteams_bridge_workflow_operator_token="",
        )
    )
    assert await unconfigured.connection_status() == {
        "available": False,
        "enabled": False,
        "configured": False,
        "connected": False,
        "configuration_source": "environment",
        "reason": "disabled",
    }


@pytest.mark.asyncio
async def test_connection_status_reports_enabled_but_incomplete_configuration() -> None:
    service = AgentTeamsService(
        Settings(
            agentteams_bridge_enabled=True,
            agentteams_bridge_url="http://bridge.test",
            agentteams_bridge_manager_token="",
            agentteams_bridge_data_steward_token="",
            agentteams_bridge_approval_token="",
            agentteams_bridge_workflow_operator_token="",
        )
    )

    assert await service.connection_status() == {
        "available": False,
        "enabled": True,
        "configured": False,
        "connected": False,
        "configuration_source": "environment",
        "reason": "incomplete_configuration",
    }
