"""HTTP validation for shared block editing without a real network socket."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from cygnusx.api import deps
from cygnusx.api.v1 import users
from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.core.exceptions import BusinessError

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_http_allows_empty_agent_and_explicitly_cleared_shared_block(monkeypatch):
    app = FastAPI()
    app.include_router(users.router, prefix="/users")
    async def current_user():
        return "owner"

    async def database():
        return object()

    app.dependency_overrides[deps.get_current_user_id] = current_user
    app.dependency_overrides[deps.get_db] = database
    update = AsyncMock(return_value={
        "id": 1, "agent_id": "", "block_name": "profile", "content": "",
        "char_limit": 1500, "version": 2, "status": "active", "superseded_by": None,
    })
    monkeypatch.setattr(users, "AgentMemoryService", lambda _db: SimpleNamespace(update_memory_block=update))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://memory-test") as client:
        response = await asyncio.wait_for(client.patch(
            "/users/me/memory-blocks/profile", params={"agent_id": ""},
            json={"content": "", "expected_version": 1},
        ), timeout=5)
    assert response.status_code == 200
    assert response.json()["content"] == "" and response.json()["agent_id"] == ""
    update.assert_awaited_once_with("owner", "", "profile", "", 1, project_id=None)


@pytest.mark.parametrize("name,agent,content", [
    ("current_focus", "", "focus"), ("profile", "", "API_KEY=sk-placeholder-secret-value"),
])
async def test_block_validation_rejects_missing_focus_context_or_credentials(name, agent, content):
    with pytest.raises(BusinessError):
        await AgentMemoryService(None).update_memory_block("owner", agent, name, content, 1)


@pytest.mark.parametrize("owned,enabled", [(True, True), (False, True), (True, False)])
async def test_project_focus_api_checks_owner_and_feature_gate(monkeypatch, owned, enabled):
    from uuid import uuid4

    from cygnusx.core.exceptions import NotFoundError

    owner, project = uuid4(), uuid4()
    update = AsyncMock(return_value={"id": 9, "agent_id": "a", "project_id": str(project),
                                     "block_name": "current_focus", "content": "focus", "version": 2, "char_limit": 2000})
    db = SimpleNamespace(scalar=AsyncMock(return_value=project if owned else None))
    monkeypatch.setattr(users, "get_settings", lambda: SimpleNamespace(memory_focus_per_project_enabled=enabled))
    monkeypatch.setattr(users, "AgentMemoryService", lambda _db: SimpleNamespace(update_memory_block=update))
    request = users.MemoryBlockUpdateRequest(content="focus", expected_version=1)
    if owned and enabled:
        response = await users.update_my_memory_block("current_focus", request, str(owner), db, "a", project)
        assert response.project_id == str(project)
        update.assert_awaited_once_with(str(owner), "a", "current_focus", "focus", 1, project_id=str(project))
    else:
        with pytest.raises(NotFoundError if enabled else BusinessError):
            await users.update_my_memory_block("current_focus", request, str(owner), db, "a", project)
        update.assert_not_awaited()
    if not enabled:
        db.scalar.assert_not_awaited()
    else:
        from sqlalchemy.dialects import postgresql

        query = db.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
        assert owner in query.params.values() and project in query.params.values()
