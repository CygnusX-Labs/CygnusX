from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from omichub_agent_gateway.app import create_app
from omichub_agent_gateway.client import OmicHubConsultationClient
from omichub_agent_gateway.config import GatewaySettings


def headers() -> dict[str, str]:
    return {"X-Gateway-Identity": "bioops-manager", "X-Gateway-Token": "manager-secret"}


@pytest.fixture
def settings(tmp_path: Path) -> GatewaySettings:
    return GatewaySettings(
        omichub_base_url="http://omic.test",
        audit_log_path=str(tmp_path / "gateway-audit.jsonl"),
        request_timeout_seconds=0.05,
    )


def make_client(
    settings: GatewaySettings, handler: httpx.MockTransport
) -> tuple[httpx.AsyncClient, httpx.AsyncClient]:
    upstream = httpx.AsyncClient(transport=handler, base_url="http://omic.test")
    app = create_app(settings, OmicHubConsultationClient(settings, upstream))
    api = httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://gateway.test")
    return api, upstream


def read_audit_log(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_allowlisted_agent_returns_fixed_schema_and_strips_raw_response(
    settings: GatewaySettings,
) -> None:
    asyncio.run(_test_allowlisted_agent_returns_fixed_schema_and_strips_raw_response(settings))


async def _test_allowlisted_agent_returns_fixed_schema_and_strips_raw_response(
    settings: GatewaySettings,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "conclusion": "QC supports the stated interpretation.",
                "recommendations": ["Review dispersion diagnostics."],
                "evidence_refs": ["omic://reports/qc-1"],
                "risks": ["Small sample size."],
                "token_usage": 120,
            },
        )

    api, upstream = make_client(settings, httpx.MockTransport(handler))
    try:
        response = await api.post(
            "/v1/scientific-interpretation",
            headers=headers(),
            json={
                "case_id": "case-1",
                "agent_id": "agent-rnaseq",
                "question": "Interpret RNA-seq QC results.",
                "capability": "qc_advice",
                "evidence_refs": ["omic://reports/qc-1"],
                "requested_tools": ["ensembl.lookup_gene"],
            },
        )
    finally:
        await api.aclose()
        await upstream.aclose()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "schema_version",
        "status",
        "conclusion",
        "recommendations",
        "evidence_refs",
        "risks",
        "agent_id",
        "schema_ver",
        "duration_ms",
        "token_usage",
        "error",
    }
    assert body["status"] == "completed"
    assert body["schema_version"] == "1.0"
    assert calls[0].url.path == "/api/v1/agent-teams/consultations/scientific-interpretation"
    upstream_payload = json.loads(calls[0].content)
    assert upstream_payload["read_only"] is True
    assert upstream_payload["allow_task_actions"] is False
    assert upstream_payload["allow_file_write"] is False
    assert upstream_payload["allow_database_access"] is False
    assert upstream_payload["allow_shell"] is False


def test_disallowed_tool_is_rejected_and_audited(settings: GatewaySettings) -> None:
    asyncio.run(_test_disallowed_tool_is_rejected_and_audited(settings))


async def _test_disallowed_tool_is_rejected_and_audited(settings: GatewaySettings) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={"unexpected": True})

    api, upstream = make_client(settings, httpx.MockTransport(handler))
    try:
        response = await api.post(
            "/v1/scientific-interpretation",
            headers=headers(),
            json={
                "case_id": "case-2",
                "agent_id": "agent-rnaseq",
                "question": "Please submit a task after interpreting this result.",
                "capability": "result_interpretation",
                "requested_tools": ["tasks.submit"],
            },
        )
    finally:
        await api.aclose()
        await upstream.aclose()

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["error"]["code"] == "TOOL_NOT_ALLOWED"
    assert calls == []
    audit_text = read_audit_log(settings.audit_log_path)
    event = json.loads(audit_text.splitlines()[-1])
    assert event["event_type"] == "agent.consultation"
    assert event["payload"]["error_code"] == "TOOL_NOT_ALLOWED"
    assert "submit a task" in event["payload"]["question_summary"]


def test_call_and_token_limits_return_structured_rejections(tmp_path: Path) -> None:
    asyncio.run(_test_call_and_token_limits_return_structured_rejections(tmp_path))


async def _test_call_and_token_limits_return_structured_rejections(tmp_path: Path) -> None:
    settings = GatewaySettings(
        omichub_base_url="http://omic.test",
        audit_log_path=str(tmp_path / "gateway-audit.jsonl"),
        max_calls_per_case=1,
        max_tokens_per_case=100,
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"conclusion": "Result.", "token_usage": 101})

    api, upstream = make_client(settings, httpx.MockTransport(handler))
    payload = {
        "case_id": "case-3",
        "agent_id": "agent-rnaseq",
        "question": "Interpret results.",
        "capability": "interpretation",
    }
    try:
        token_limited = await api.post(
            "/v1/scientific-interpretation", headers=headers(), json=payload
        )
        call_limited = await api.post(
            "/v1/scientific-interpretation", headers=headers(), json=payload
        )
    finally:
        await api.aclose()
        await upstream.aclose()

    assert token_limited.json()["status"] == "rejected"
    assert token_limited.json()["error"]["code"] == "CASE_TOKEN_LIMIT_EXCEEDED"
    assert call_limited.json()["status"] == "rejected"
    assert call_limited.json()["error"]["code"] == "CASE_CALL_LIMIT_EXCEEDED"


def test_timeout_returns_manual_review_and_audit_event(settings: GatewaySettings) -> None:
    asyncio.run(_test_timeout_returns_manual_review_and_audit_event(settings))


def test_code_agent_is_allowlisted_for_read_only_consultation(settings: GatewaySettings) -> None:
    policy = settings.agent_policy_map()["agent-code"]

    assert "interpretation" in policy[0]
    assert "ensembl.lookup_gene" in policy[1]


async def _test_timeout_returns_manual_review_and_audit_event(settings: GatewaySettings) -> None:
    async def slow_handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)
        return httpx.Response(200, json={"conclusion": "Too late.", "token_usage": 1})

    api, upstream = make_client(settings, httpx.MockTransport(slow_handler))
    try:
        response = await api.post(
            "/v1/scientific-interpretation",
            headers=headers(),
            json={
                "case_id": "case-4",
                "agent_id": "agent-rnaseq",
                "question": "Interpret results.",
                "capability": "interpretation",
            },
        )
    finally:
        await api.aclose()
        await upstream.aclose()

    assert response.json()["status"] == "manual_review"
    assert response.json()["error"]["code"] == "UPSTREAM_TIMEOUT"
    audit_text = read_audit_log(settings.audit_log_path)
    event = json.loads(audit_text.splitlines()[-1])
    assert event["payload"]["status"] == "manual_review"
