"""Existing Case contracts reuse the Matrix room bound to a chat session."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from omichub.application.services.agentteams_service import AgentTeamsService


@pytest.mark.asyncio
async def test_create_case_forwards_bound_element_room_url(monkeypatch) -> None:
    service = AgentTeamsService(
        SimpleNamespace(),
        SimpleNamespace(
            enabled=True,
            configured=True,
            bridge_url="http://bridge.test",
            manager_token="secret",
            data_steward_token="steward-secret",
        ),
    )
    requests: list[dict] = []

    async def fake_request(_path: str, *, method: str = "GET", **kwargs):
        requests.append({"method": method, **kwargs})
        return {"case_id": "case-1", "status": "received"}

    async def fake_request_as(*_args, **_kwargs):
        return {"status": "passed"}

    monkeypatch.setattr(service, "_request", fake_request)
    monkeypatch.setattr(service, "_request_as", fake_request_as)
    await service.create_case(
        case_id="case-1",
        project_id="project-1",
        intent="交付",
        requester_ref="user-1",
        flow_id="rna_seq",
        sample_sheet=[{"sample_id": "s1"}],
        element_room_url="https://element.example/#/room/!room:example",
    )

    assert requests[0]["json"]["element_room_url"] == "https://element.example/#/room/!room:example"
