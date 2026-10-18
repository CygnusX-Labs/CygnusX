"""Real Gateway/ASGI/builtin dispatch with isolated SQL and Redis/metadata doubles."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import select

from cygnusx.api import deps
from cygnusx.api.v1 import agent_tools
from cygnusx.application.services import agent_tool_delegation as delegation
from cygnusx.core.exceptions import CygnusXError
from cygnusx.infrastructure.database.models.chat import ChatSessionModel
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.user import UserModel
from tests.unit.test_agent_tools_phase2 import env as env

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def callback(env, monkeypatch):
    used = set()

    async def claim(key, *args, **kwargs):
        if key in used:
            return False
        used.add(key)
        return True

    monkeypatch.setattr(delegation, "get_redis", lambda: SimpleNamespace(set=claim))
    app = FastAPI()
    app.include_router(agent_tools.router, prefix="/agent-tools")

    async def db():
        yield env.db

    app.dependency_overrides[deps.get_db] = db

    @app.exception_handler(CygnusXError)
    async def error(request, exc):
        return JSONResponse({"code": exc.code}, status_code=exc.status_code)

    return app


async def signed(env):
    return await delegation.issue_delegation(await env.gateway.context(env.owner, "mouse"))


async def test_stale_context_cannot_silently_adopt_another_owned_project(env):
    from cygnusx.core.exceptions import AuthorizationError

    old = await env.gateway.context(env.owner, "mouse")
    session = env.db.sync.scalar(
        select(ChatSessionModel).where(ChatSessionModel.session_id == "mouse")
    )
    session.project_id = env.project2
    await env.db.flush()
    with pytest.raises(AuthorizationError):
        await env.gateway.invoke(old, "downloads.describe_capabilities", {})
    fresh = await env.gateway.context(env.owner, "mouse")
    assert (await env.gateway.invoke(fresh, "downloads.describe_capabilities", {}))["result"][
        "runtime_status"
    ] == "BLOCKED"


async def post(
    client, token, capability="downloads.describe_capabilities", args=None, call_id=None
):
    return await client.post(
        "/agent-tools/delegated/invoke",
        headers={"Authorization": "Bearer " + token},
        json={
            "capability_id": capability,
            "arguments": args or {},
            "call_id": call_id or str(uuid4()),
        },
    )


async def test_delegated_callback_dispatches_catalog_and_builtin_matches(
    env, callback, monkeypatch
):
    from cygnusx.core import config

    settings = config.get_settings().model_copy(update=vars(env.settings))
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    from cygnusx.domain.mcp.entities import MCPServer
    from cygnusx.domain.mcp.value_objects import Transport
    from cygnusx.infrastructure.mcp.client import MCPClient

    token = await signed(env)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=callback), base_url="http://isolated"
    ) as client:
        node = await post(client, token)
        assert node.status_code == 200
        invalid = await post(client, token, args={"owner_id": env.other})
        assert invalid.status_code == 422
        nonce = str(uuid4())
        assert (await post(client, token, call_id=nonce)).status_code == 200
        assert (await post(client, token, call_id=nonce)).status_code == 409
    context = await env.gateway.context(env.owner, "assistant")
    builtin = await MCPClient()._call_tool_inner(
        MCPServer(id=uuid4(), name="cygnusx-tools", transport=Transport.BUILTIN),
        "bioops_downloads_describe_capabilities",
        {},
        user_id=env.owner,
        context=context,
    )
    assert builtin["success"] and builtin["result"]["success"]
    assert builtin["result"]["llm_payload"]["result"] == node.json()["result"]
    assert builtin["result"]["ui_payload"]["bioops"] == builtin["result"]["llm_payload"]
    env.download.assert_not_called()


@pytest.mark.parametrize(
    "change", ["expired", "token_version", "module", "project", "archived", "scope"]
)
async def test_callback_revalidates_delegation_and_live_state(env, callback, change):
    token = await signed(env)
    if change in {"expired", "scope"}:
        claims = jwt.decode(
            token, delegation._key(), algorithms=["HS256"], audience=delegation.AUDIENCE
        )
        if change == "expired":
            claims["exp"] = 1
        else:
            claims["scopes"] = ["read:tasks"]
        token = jwt.encode(claims, delegation._key(), algorithm="HS256")
    elif change == "token_version":
        (await env.db.get(UserModel, UUID(env.owner))).token_version += 1
    elif change == "module":
        (await env.db.get(UserModel, UUID(env.owner))).disabled_modules = ["downloads"]
    elif change == "project":
        (await env.db.get(ProjectModel, UUID(env.project))).user_id = UUID(env.other)
    else:
        session = env.db.sync.scalar(
            select(ChatSessionModel).where(ChatSessionModel.session_id == "mouse")
        )
        session.status = "archived"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=callback), base_url="http://isolated"
    ) as client:
        response = await post(client, token)
    assert response.status_code in {401, 403, 404}
    env.download.assert_not_called()


@pytest.fixture
def research_pack():
    from pathlib import Path

    import yaml

    return yaml.safe_load(Path("data/ai/tools/research.yaml").read_text())


async def test_model_tool_assembly_uses_same_schema_and_filters_modules(
    env, monkeypatch, research_pack
):

    from cygnusx.application.services import agent_service as module
    from cygnusx.core import config
    from cygnusx.core.config import get_settings
    from cygnusx.infrastructure.database.models.agent import AgentTemplateModel

    settings = get_settings().model_copy(
        update={**vars(env.settings), "dataset_discovery_readonly": True}
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    env.settings.dataset_discovery_readonly = True
    service = module.AgentService(env.db)
    agent = AgentTemplateModel(
        agent_id="fixture",
        name="fixture",
        is_active=True,
        features={},
        mcp_ids=[],
        skill_ids=[],
        system_prompt="fixture",
        temperature=0.7,
        max_tokens=1000,
    )
    # Consume the actual research tool pack; a generic empty pack must not gain tools.
    agent.features = {"tool_packs": [research_pack]}
    monkeypatch.setattr(service, "_reconcile_model_bindings", AsyncMock())
    monkeypatch.setattr(service, "get_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(service, "_get_user_capability", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_resolve_model", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(service, "_agentteams_chat_entry_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(service, "_load_skills", AsyncMock(return_value=[]))
    context = await service.assemble_context("fixture", user_id=env.owner)
    assert context
    tools = {t["function"]["name"]: t["function"] for t in context.tools}
    catalog = env.gateway.catalog(await env.gateway.context(env.owner, "mouse"))
    for capability in catalog:
        if capability["capability_id"].startswith(("downloads.", "dataset.", "tasks.")):
            assert tools[capability["tool_name"]]["parameters"] == capability["input_schema"]
            # Same lookup used by Legacy and LangGraph runtime server resolution.
            assert any(
                t.tool_name == capability["tool_name"]
                for server in context.mcp_servers
                for t in server.tools
            )
    from cygnusx.infrastructure.mcp.client import MCPClient

    name = "bioops_downloads_describe_capabilities"
    server = next(s for s in context.mcp_servers if any(t.tool_name == name for t in s.tools))
    dispatched = await MCPClient()._call_tool_inner(
        server,
        name,
        {},
        user_id=env.owner,
        context=await env.gateway.context(env.owner, "assistant"),
    )
    assert dispatched["success"] and dispatched["result"]["success"]
    assert dispatched["result"]["llm_payload"]["result"]["runtime_status"] == "BLOCKED"
    (await env.db.get(UserModel, UUID(env.owner))).disabled_modules = ["downloads"]
    restricted = await service.assemble_context("fixture", user_id=env.owner)
    names = {t["function"]["name"] for t in restricted.tools}
    assert "bioops_dataset_discover" not in names
    assert "bioops_downloads_describe_capabilities" not in names


async def test_delegated_metadata_prepare_and_task_dispatch_remain_scoped(
    env, callback, monkeypatch
):
    from cygnusx.application.services import dataset_import_service as imports

    env.settings.dataset_discovery_readonly = True
    monkeypatch.setattr(imports, "get_settings", lambda: env.settings)
    geo = AsyncMock()
    geo.resolve.return_value = {
        "primary_accession": "GSE1",
        "runs": [],
        "files": [],
        "samples": [],
        "source_evidence": [],
        "confidence_flags": ["raw_runs_not_resolved"],
    }
    monkeypatch.setattr(imports, "metadata_adapter", lambda: geo)
    token = await signed(env)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=callback), base_url="http://isolated"
    ) as client:
        metadata = await post(client, token, "dataset.discover", {"accession": "GSE1"})
        assert metadata.status_code == 200
        assert metadata.json()["result"]["raw"]["runtime_verified"] is False
        prepared = await post(client, token, "downloads.prepare", {"accession": "SRR123"})
        assert prepared.status_code == 200
        assert prepared.json()["result"]["state"] != "APPROVED"
        forbidden_task = await post(
            client, token, "tasks.get_status", {"task_id": str(uuid4()), "owner_id": env.other}
        )
        assert forbidden_task.status_code == 422
    env.download.assert_not_called()
    assert len(env.gateway.confirmations._store._records) == 1


@pytest.mark.parametrize(
    "case",
    [
        "normal",
        "limited",
        "owner",
        "project_hint",
        "revoked",
        "missing",
        "archived",
        "module",
        "kind",
        "history",
        "changed",
    ],
)
async def test_bridge_context_contract(env: Any, case: str) -> None:
    from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
    from cygnusx.application.services.tool_bridge_service import ToolBridgeService

    context = ToolInvocationContext(user_id=env.owner, session_id="assistant", db=env.db)
    session = env.db.sync.scalar(
        select(ChatSessionModel).where(ChatSessionModel.session_id == "assistant")
    )
    if case in {"limited", "history", "changed"}:
        context = await env.gateway.context(env.owner, "assistant")
    if case == "limited":
        context.extra["scopes"] = ["read:tasks"]
    elif case == "owner":
        context.user_id = env.other
    elif case == "project_hint":
        context.extra["project_id"] = env.project2
    elif case == "revoked":
        (await env.db.get(ProjectModel, UUID(env.project))).user_id = UUID(env.other)
    elif case == "missing":
        context.session_id = "missing"
    elif case == "archived":
        session.status = "archived"
    elif case == "module":
        (await env.db.get(UserModel, UUID(env.owner))).disabled_modules = ["downloads"]
    elif case == "kind":
        context.session_id = "mouse"
    elif case == "changed":
        session.project_id = env.project2
    result = await ToolBridgeService().execute(
        env.owner, "bioops_downloads_describe_capabilities", {}, context=context
    )
    assert result["success"] is (case in {"normal", "history"})
    if result["success"]:
        assert result["llm_payload"]["result"]["runtime_status"] == "BLOCKED"
    env.download.assert_not_called()


@pytest.mark.parametrize("engine", ["legacy", "langgraph"])
@pytest.mark.parametrize("invalid", [False, True])
async def test_full_shared_tool_round(
    env: Any, monkeypatch: pytest.MonkeyPatch, research_pack: Any, engine: str, invalid: bool
) -> None:
    from cygnusx.application.services import agent_service, chat_service
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.application.services.chat.request_preparation import PreparedAgentRequest
    from cygnusx.application.services.chat.runtimes import langgraph_runtime
    from cygnusx.core import config
    from cygnusx.infrastructure.ai_provider import openai_compatible
    from cygnusx.infrastructure.ai_provider.openai_compatible import provider_manager
    from cygnusx.infrastructure.database.models.agent import AgentTemplateModel

    invoke = AsyncMock(side_effect=AgentToolGateway.invoke)

    async def counted_invoke(self: Any, *args: Any, **kwargs: Any) -> Any:
        return await invoke(self, *args, **kwargs)

    monkeypatch.setattr(AgentToolGateway, "invoke", counted_invoke)

    settings = config.get_settings().model_copy(
        update={
            **vars(env.settings),
            "app_env": "acceptance",
            "deterministic_test_provider_enabled": True,
            "dynamic_model_routing_enabled": False,
            "chat_force_legacy_runtime": engine == "legacy",
            "mas_enabled": False,
        }
    )
    for module in (config, agent_service, chat_service, langgraph_runtime):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(openai_compatible, "get_settings", lambda: settings)
    agent = AgentTemplateModel(
        agent_id="fixture",
        name="fixture",
        is_active=True,
        features={"tool_packs": [research_pack], "engine": engine, "enable_web_search": False},
        mcp_ids=[],
        skill_ids=[],
        system_prompt="fixture",
        temperature=0.7,
        max_tokens=1000,
    )
    model = SimpleNamespace(
        id=uuid4(),
        name="isolated",
        model="isolated",
        api_key="unused",
        provider_type="deterministic_test",
        extra_params={
            "deterministic_test_script": {
                "call_id": "catalog-call",
                "name": "bioops_downloads_describe_capabilities",
                "arguments": {"owner_id": env.other} if invalid else {},
            }
        },
        max_tokens=1000,
    )
    provider_manager.clear_cache(str(model.id))
    from cygnusx.infrastructure.database.models.site_settings import SiteSettingModel

    site_table: Any = SiteSettingModel.__table__
    site_table.create(env.db.sync.get_bind())
    env.db.add(SiteSettingModel(id=1, agent_memory_enabled=False))
    await env.db.flush()
    assembler = agent_service.AgentService(env.db)
    bindings: dict[str, Any] = {
        "_reconcile_model_bindings": None,
        "get_agent": agent,
        "_get_user_capability": None,
        "_resolve_model": model,
        "_agentteams_chat_entry_enabled": False,
        "_load_skills": [],
    }
    for name, value in bindings.items():
        monkeypatch.setattr(assembler, name, AsyncMock(return_value=value))
    assembled = await assembler.assemble_context("fixture", user_id=env.owner)
    assert assembled
    monkeypatch.setattr(
        chat_service,
        "prepare_agent_request",
        AsyncMock(return_value=PreparedAgentRequest(assembled, model, [], 1000)),
    )
    service: Any = chat_service.ChatService(env.db)
    session = env.db.sync.scalar(
        select(ChatSessionModel).where(ChatSessionModel.session_id == "assistant")
    )
    session.agent_id = "fixture"
    session.mode = "chat"
    for name, value in {
        "_ensure_cookie_balance": None,
        "_admin_subagent_fanout_enabled": False,
        "_maybe_emit_agentteams_upgrade_suggestion": None,
        "_record_user_message_anchor": None,
        "add_message": SimpleNamespace(message_id="message"),
        "_collect_session_file_context": "",
        "update_message_content": None,
        "_apply_usage_to_session": None,
        "_flush_deferred_compaction_audit": None,
    }.items():
        monkeypatch.setattr(service, name, AsyncMock(return_value=value))
    monkeypatch.setattr(service, "get_session", AsyncMock(return_value=session))
    service._sessions.get_messages = AsyncMock(return_value=[])
    service._last_context_compaction = None

    async def compress(messages: Any, *args: Any, **kwargs: Any) -> tuple[Any, bool, int]:
        return messages, False, 0

    monkeypatch.setattr(service, "_compress_context_if_needed", compress)
    chunks = [
        c
        async for c in service._stream_agent_chat_inner(
            env.owner,
            "fixture",
            [{"role": "user", "content": "read catalog"}],
            session_id="assistant",
        )
    ]
    provider = provider_manager._providers[str(model.id)]
    assert provider.calls == 2
    assert chunks[-1].type == "done", [(c.type, c.content) for c in chunks]
    results = [c for c in chunks if c.type == "tool_result"]
    assert len(results) == 1
    assert results[0].metadata["success"] is (not invalid)
    response_marker = "runtime_status" if not invalid else "success"
    assert any(
        c.type == "text" and response_marker in c.content
        for c in chunks
    )
    assert invoke.await_count == 1
    env.download.assert_not_called()

    # Exercise the product SSE route and serializer on top of the same actual
    # Runtime; ASGI transport is in-process and does not claim network/PG E2E.
    from cygnusx.api import deps
    from cygnusx.api.v1 import chat as chat_api
    from cygnusx.application.services.chat.chat_event_service import ChatEventService

    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api/v1/chat")

    async def db_dependency():
        yield env.db

    async def user_dependency():
        return env.owner

    app.dependency_overrides[deps.get_db] = db_dependency
    app.dependency_overrides[deps.get_current_user_id] = user_dependency
    monkeypatch.setattr(chat_api, "ChatService", lambda _db: service)
    monkeypatch.setattr(
        chat_api.ChatEventService,
        "from_settings",
        lambda: ChatEventService(enforcement="warn"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated"
    ) as client:
        response = await client.post(
            "/api/v1/chat/stream",
            json={
                "agent_id": "fixture",
                "session_id": "assistant",
                "messages": [{"role": "user", "content": "read catalog"}],
            },
        )
    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1]["type"] == "done", events
    assert any(event["type"] == "tool_result" for event in events)
    assert any(event["type"] == "text" and response_marker in event["content"]
               for event in events)
    assert provider.calls == 4
    assert invoke.await_count == 2
    env.download.assert_not_called()


async def test_bridge_rechecks_revocation_during_derivation(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.application.services.tool_bridge_service import ToolBridgeService

    original = AgentToolGateway.context
    calls = 0

    async def derive(self: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        result = await original(self, *args, **kwargs)
        calls += 1
        if calls == 1:
            (await env.db.get(UserModel, UUID(env.owner))).disabled_modules = ["downloads"]
        return result

    monkeypatch.setattr(AgentToolGateway, "context", derive)
    result = await ToolBridgeService().execute(
        env.owner, "bioops_downloads_describe_capabilities", {},
        context=ToolInvocationContext(user_id=env.owner, session_id="assistant", db=env.db),
    )
    assert calls == 2
    assert result["success"] is False
    env.download.assert_not_called()
