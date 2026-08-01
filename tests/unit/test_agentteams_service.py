"""AgentTeams user proxy tests: browser-facing access stays requester-scoped."""

from __future__ import annotations

import pytest

from omichub.application.services.agentteams_service import AgentTeamsService
from omichub.core.config import Settings
from omichub.core.exceptions import BusinessError


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


@pytest.mark.asyncio
async def test_get_case_rejects_other_requester(service: AgentTeamsService, monkeypatch) -> None:
    async def fake_request(path: str, **kwargs):
        assert path == "/v1/cases/case-other"
        return {"case_id": "case-other", "requester_ref": "other-user"}

    monkeypatch.setattr(service, "_request", fake_request)

    with pytest.raises(BusinessError, match="无权查看"):
        await service.get_case("case-other", "current-user")


@pytest.mark.asyncio
async def test_create_case_assigns_and_runs_read_only_preflight(
    service: AgentTeamsService, monkeypatch
) -> None:
    captured: list[tuple[str, dict]] = []

    async def fake_request(path: str, **kwargs):
        captured.append((path, kwargs))
        return {"case_id": "bioops_001", "requester_ref": "current-user"}

    async def fake_request_as(identity: str, token: str, path: str, **kwargs):
        captured.append((path, {"identity": identity, "token": token, **kwargs}))
        return {"case_id": "bioops_001", "status": "passed"}

    monkeypatch.setattr(service, "_request", fake_request)
    monkeypatch.setattr(service, "_request_as", fake_request_as)

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
                },
            },
        ),
        (
            "/v1/cases/bioops_001/work-items",
            {
                "method": "POST",
                "json": {
                    "work_item_id": "preflight-01",
                    "target": "data-steward",
                    "objective": "核验项目输入、样本表和分组对比，决定是否进入人工审批。",
                    "skill_name": "project-preflight",
                    "context_refs": [{"kind": "project", "id": "project-1"}],
                    "read_only": True,
                },
            },
        ),
        (
            "/v1/projects/project-1/preflight",
            {
                "identity": "data-steward",
                "token": "steward-token",
                "method": "POST",
                "json": {
                    "case_id": "bioops_001",
                    "work_item_id": "preflight-01",
                    "flow_id": "rna_seq",
                    "sample_sheet": [{"sample": "S01", "group": "control"}],
                    "comparisons": [{"control": "control", "treatment": "treatment"}],
                    "context_refs": [{"kind": "project", "id": "project-1"}],
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
        return {"omic_task_id": "task-001", "status": "queued"}

    monkeypatch.setattr(service, "_request", fake_request)
    monkeypatch.setattr(service, "_request_as", fake_request_as)

    result = await service.approve_and_submit_task(
        case_id="bioops_001",
        requester_ref="current-user",
        task_name="RNA delivery",
    )

    assert result == {"omic_task_id": "task-001", "status": "queued"}
    assert requests[1] == (
        "/v1/approvals",
        {
            "identity": "approval-authority",
            "token": "approval-token",
            "method": "POST",
            "json": {"case_id": "bioops_001", "action": "submit_task", "flow_id": "rna_seq"},
        },
    )
    assert requests[2][0] == "/v1/cases/bioops_001/work-items"
    assert requests[3] == (
        "/v1/tasks",
        {
            "identity": "workflow-operator",
            "token": "operator-token",
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
                    "execution_mode": "local",
                },
            },
        },
    )


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
async def test_chat_room_prefers_case_room_url(
    element_settings: Settings, monkeypatch
) -> None:
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
