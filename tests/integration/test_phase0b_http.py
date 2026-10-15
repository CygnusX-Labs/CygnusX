"""Real ASGI routes and JWT verification; only persistence and business effects are stubs."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from cygnusx.api import deps
from cygnusx.api.v1 import ai, downloads, tasks
from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.services import tool_confirmation_service as confirmations
from cygnusx.core import security
from cygnusx.core.exceptions import CygnusXError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def boundary(monkeypatch):
    # This fixture isolates the pre-existing approval lifecycle, not Phase 2's
    # release gate. New test_agent_tools_phase2.py asserts the real gate stays shut.
    from cygnusx.application.services import agent_tool_gateway

    monkeypatch.setattr(agent_tool_gateway, "require_agent_write_gate", lambda operation: None)
    owner, other = str(uuid4()), str(uuid4())
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(status="active", token_version=1)

    @asynccontextmanager
    async def session_factory():
        yield session

    monkeypatch.setattr(deps, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(
        jwt_secret_key="isolated-phase0b-test-secret-never-production",
        jwt_algorithm="HS256", access_token_expire_minutes=5,
    ))
    monkeypatch.setattr(deps, "_authenticate_api_key", AsyncMock(return_value=owner))
    store = confirmations._MemoryStore()
    service = confirmations.ToolConfirmationService(store)
    monkeypatch.setattr(confirmations, "_confirmation_service", service)
    business = SimpleNamespace(submit=AsyncMock(side_effect=RuntimeError("effect boundary reached")))
    app = FastAPI()
    app.include_router(ai.router, prefix="/ai")
    app.include_router(tasks.router, prefix="/tasks")
    app.include_router(downloads.router, prefix="/downloads")
    async def isolated_business():
        return business

    async def isolated_db():
        return session

    app.dependency_overrides[tasks.get_task_service] = isolated_business
    app.dependency_overrides[downloads.get_download_service] = isolated_business
    app.dependency_overrides[deps.get_db] = isolated_db
    monkeypatch.setattr(downloads, "_ensure_enabled", lambda _: None)

    @app.exception_handler(CygnusXError)
    async def handle_error(request, error):
        return JSONResponse({"code": error.code, "detail": error.detail}, status_code=error.status_code)

    @app.exception_handler(RuntimeError)
    async def handle_effect(request, error):
        return JSONResponse({"effect": True}, status_code=202)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://isolated") as client:
        yield SimpleNamespace(
            client=client, owner=owner, other=other, business=business, service=service,
            store=store, jwt={"Authorization": "Bearer " + security.create_access_token(owner, 1)},
            other_jwt={"Authorization": "Bearer " + security.create_access_token(other, 1)},
        )


@pytest.mark.parametrize("route,submission,tool", [
    ("/tasks", TaskSubmitRequest(flow_id="rna_seq", name="isolated"), "cygnusx_submit_analysis"),
    ("/downloads", DownloadRequest(accession="SRR123"), "cygnusx_submit_download"),
])
async def test_real_http_confirmation_lifecycle(boundary, route, submission, tool):
    b = boundary
    payload = submission.model_dump()
    headers = {"X-API-Key": "isolated-test-key", "X-User-Id": b.other}
    assert (await b.client.post(route, json=payload, headers=headers)).status_code == 403
    assert (await b.client.post(route, json={**payload, "user_confirmed": True}, headers=headers)).status_code >= 400
    assert (await b.client.post(route, json={**payload, "confirmation_id": str(uuid4())}, headers=headers)).status_code == 422
    b.business.submit.assert_not_awaited()
    created = await b.client.post("/ai/tool-invocations", json={"tool_name": tool, "arguments": payload}, headers=headers)
    assert created.status_code == 200, created.text
    cid = created.json()["confirmation_id"]
    approved_route = f"/ai/tool-invocations/{cid}/approve"
    assert (await b.client.post(approved_route, headers=headers)).status_code == 401
    assert (await b.client.post(approved_route, headers=b.other_jwt)).status_code == 400
    assert (await b.client.post(route, json={**payload, "confirmation_id": cid}, headers=headers)).status_code == 422
    b.business.submit.assert_not_awaited()
    assert (await b.client.post(approved_route, headers=b.jwt)).status_code == 200
    results = await asyncio.gather(*(
        b.client.post(route, json={**payload, "confirmation_id": cid}, headers=headers) for _ in range(2)
    ))
    assert sorted(result.status_code for result in results) == [202, 422]
    b.business.submit.assert_awaited_once()
    assert b.business.submit.call_args.args[0] == b.owner
    assert (await b.client.post(route, json={**payload, "confirmation_id": cid}, headers=headers)).status_code == 422


@pytest.mark.parametrize("negative", ["tamper", "expiry", "wrong_owner", "bad_jwt"])
async def test_rejection_has_no_business_side_effect(boundary, negative):
    b = boundary
    request = DownloadRequest(accession="SRR123")
    payload = request.model_dump()
    record = await b.service.create_for_tool(b.owner, "cygnusx_submit_download", payload)
    await b.service.approve_by_human(user_id=b.owner, confirmation_id=record.confirmation_id)
    headers = {"X-API-Key": "isolated-test-key"}
    if negative == "tamper":
        payload["accession"] = "SRR456"
    elif negative == "expiry":
        record.status = "APPROVED"
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await b.store.save(record)
    elif negative == "wrong_owner":
        headers = b.other_jwt
    else:
        headers = {"Authorization": "Bearer forged", "X-User-Id": b.owner}
    result = await b.client.post("/downloads", json={**payload, "confirmation_id": record.confirmation_id}, headers=headers)
    assert result.status_code in {401, 422}
    b.business.submit.assert_not_awaited()
