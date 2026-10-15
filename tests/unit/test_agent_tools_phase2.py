"""Offline SQL persistence + real gateway/services; no Redis/queue/Worker E2E."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import jwt
import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from cygnusx.application.schemas.agent_tools import capability_catalog
from cygnusx.application.services import agent_tool_delegation as delegation
from cygnusx.application.services import agent_tool_gateway as module
from cygnusx.application.services import tool_confirmation_service as confirmation
from cygnusx.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DependencyUnavailableError,
    NotFoundError,
    ValidationError,
)
from cygnusx.infrastructure.database.models.agent_tool_invocation import AgentToolInvocationModel
from cygnusx.infrastructure.database.models.chat import ChatSessionModel
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.user import UserModel

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@compiles(JSONB, "sqlite")
def sqlite_json(element, compiler, **kw):
    return "JSON"


class OfflineDB(AsyncSession):
    """Synchronous SQLite in async facade, avoiding sandbox thread/socket I/O."""

    def __init__(self, engine):
        self.sync = Session(engine, expire_on_commit=False)

    async def get(self, model, key, **kw):
        return self.sync.get(model, key)

    async def execute(self, statement, **kw):
        return self.sync.execute(statement)

    def add(self, instance, **kw):
        self.sync.add(instance)

    async def flush(self, **kw):
        self.sync.flush()

    async def commit(self):
        self.sync.commit()

    async def rollback(self):
        self.sync.rollback()


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    for table in (UserModel.__table__, ProjectModel.__table__, ChatSessionModel.__table__,
                  AgentToolInvocationModel.__table__):
        table.create(engine)
    db = OfflineDB(engine)
    owner, other = str(uuid4()), str(uuid4())
    project, project2, foreign_project = str(uuid4()), str(uuid4()), str(uuid4())
    for user_id in (owner, other):
        db.add(UserModel(id=UUID(user_id), username=user_id, email=user_id + "@test.invalid",
                         hashed_password="unused", role="user", status="active", token_version=0))
    for pid, uid, slug in ((project, owner, "owned"), (project2, owner, "second"),
                           (foreign_project, other, "foreign")):
        db.add(ProjectModel(id=UUID(pid), user_id=UUID(uid), slug=slug, name=slug))
    for sid, uid, pid, research in (("mouse", owner, project, True),
                                     ("assistant", owner, project, False),
                                     ("other", other, foreign_project, True)):
        db.add(ChatSessionModel(session_id=sid, user_id=uid, project_id=pid,
                               model_id=uuid4(), status="active",
                               sandbox_meta={"research_agent": "research-treasure-mouse"} if research else {}))
    db.sync.commit()
    settings = SimpleNamespace(tool_gateway_read_enabled=True,
        agent_download_write_enabled=True, agent_analysis_write_enabled=True,
        agent_task_cancel_enabled=True, agent_tool_delegation_ttl_seconds=300,
        jwt_secret_key="isolated-phase2-secret-not-production")
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(delegation, "get_settings", lambda: settings)
    monkeypatch.setattr(confirmation, "_confirmation_service",
                        confirmation.ToolConfirmationService(confirmation._MemoryStore()))
    root = tmp_path / "users" / owner
    root.mkdir(parents=True)
    monkeypatch.setattr(module, "get_path_factory", lambda: SimpleNamespace(user_root=lambda uid: root))
    download, analysis = AsyncMock(), AsyncMock()
    monkeypatch.setattr(module.DownloadService, "submit", download)
    monkeypatch.setattr(module.TaskService, "submit", analysis)
    gateway = module.AgentToolGateway(db)
    yield SimpleNamespace(db=db, engine=engine, owner=owner, other=other, project=project,
        project2=project2, foreign_project=foreign_project, gateway=gateway, root=root,
        settings=settings, download=download, analysis=analysis)
    db.sync.close()
    engine.dispose()


async def ctx(env, sid="mouse", owner=None):
    return await env.gateway.context(owner or env.owner, sid)


async def download_proposal(env, sid="mouse"):
    response = await env.gateway.invoke(await ctx(env, sid), "downloads.prepare", {"accession": "SRR123"})
    return response["result"]


async def test_shared_flow_catalog_and_schema_across_agents(env):
    for capability, args in (("analysis.list_workflows", {}),
                              ("analysis.get_workflow_schema", {"flow_id": "rna_seq"})):
        mouse = await env.gateway.invoke(await ctx(env), capability, args)
        assistant = await env.gateway.invoke(await ctx(env, "assistant"), capability, args)
        assert mouse["result"] == assistant["result"]
        assert mouse["invocation_id"] != assistant["invocation_id"]
    env.download.assert_not_called()
    env.analysis.assert_not_called()


async def test_owner_project_and_revocation_rechecked(env):
    with pytest.raises(NotFoundError):
        await ctx(env, "other")
    session = env.db.sync.scalar(select(ChatSessionModel).where(ChatSessionModel.session_id == "mouse"))
    session.project_id = env.foreign_project
    with pytest.raises(AuthorizationError):
        await ctx(env)
    session.project_id = env.project
    proposal = await download_proposal(env)
    session.project_id = env.project2
    with pytest.raises(NotFoundError):
        await env.gateway.decide(await ctx(env), proposal["proposal_id"], approve=True)
    session.project_id = env.project
    project = await env.db.get(ProjectModel, UUID(env.project))
    project.user_id = UUID(env.other)
    with pytest.raises(AuthorizationError):
        await ctx(env)
    env.download.assert_not_called()


async def test_hidden_capability_direct_call_denied(env):
    user = await env.db.get(UserModel, UUID(env.owner))
    user.disabled_modules = ["flows"]
    context = await ctx(env)
    assert not any(c["capability_id"].startswith("analysis.") for c in env.gateway.catalog(context))
    with pytest.raises(AuthorizationError):
        await env.gateway.invoke(context, "analysis.list_workflows", {})


@pytest.mark.parametrize("spoof", ["user_id", "project_id", "_user_id", "user_confirmed", "_confirmed", "target_directory", "links"])
async def test_model_control_fields_rejected_without_business_effect(env, spoof):
    with pytest.raises(SchemaError):
        await env.gateway.invoke(await ctx(env), "downloads.prepare", {"accession": "SRR123", spoof: "forged"})
    assert not env.db.sync.scalars(select(AgentToolInvocationModel)).all()
    env.download.assert_not_called()
    env.analysis.assert_not_called()
    assert list(env.root.iterdir()) == []


@pytest.mark.parametrize("accession", ["GSE123", "GSM456"])
async def test_geo_requires_resolution_without_fake_task(env, accession):
    result = await env.gateway.invoke(await ctx(env), "downloads.prepare", {"accession": accession})
    assert result["result"]["validation"] == "NEEDS_METADATA_RESOLUTION"
    assert "task_id" not in result["result"]
    env.download.assert_not_called()


@pytest.mark.parametrize("accession", ["https://127.0.0.1/file", "../SRR123", "SRR1;touch x", "ERR123", "javascript:x"])
async def test_unsupported_or_injected_source_rejected(env, accession):
    with pytest.raises(ValidationError):
        await env.gateway.invoke(await ctx(env), "downloads.prepare", {"accession": accession})
    env.download.assert_not_called()


async def test_symlink_target_escape_rejected_before_confirmation_or_directory(env, tmp_path):
    (env.root / "projects").symlink_to(tmp_path)
    with pytest.raises(ValidationError):
        await download_proposal(env)
    assert not env.db.sync.scalars(select(AgentToolInvocationModel)).all()
    env.download.assert_not_called()


async def test_prepare_approval_restore_and_environment_cannot_open_writes(env):
    proposal = await download_proposal(env)
    assert proposal["normalized_parameters"]["target_directory"] == "projects/owned/downloads"
    assert proposal["preview"]["bytes_estimate"] is None
    assert not proposal["write_enabled"]
    assert list(env.root.iterdir()) == []
    decision = await env.gateway.decide(await ctx(env), proposal["proposal_id"], approve=True)
    assert decision["state"] == "APPROVED" and not decision["write_enabled"]
    await env.db.commit()
    env.db.sync.expunge_all()
    links = await module.AgentToolGateway(env.db).related(await ctx(env))
    assert links[0]["proposal"]["parameters_hash"] == proposal["parameters_hash"]
    assert links[0]["state"] == "APPROVED" and links[0]["task_id"] is None
    with pytest.raises(AuthorizationError, match="门禁"):
        await env.gateway.execute(await ctx(env), proposal["proposal_id"])
    env.download.assert_not_called()
    env.analysis.assert_not_called()


@pytest.mark.parametrize("capability", ["downloads.submit", "analysis.submit", "tasks.cancel"])
async def test_gate_precedes_all_audit_and_business_writes(env, capability):
    with pytest.raises(AuthorizationError) as error:
        await env.gateway.invoke(await ctx(env), capability, {"proposal_id": str(uuid4())})
    assert error.value.code == "WRITE_GATE_BLOCKED"
    assert not env.db.sync.scalars(select(AgentToolInvocationModel)).all()
    assert list(env.root.iterdir()) == []
    env.download.assert_not_called()
    env.analysis.assert_not_called()


async def test_expired_rejected_cross_owner_and_changed_approval(env):
    proposal = await download_proposal(env)
    with pytest.raises(NotFoundError):
        await env.gateway.decide(await ctx(env, "other", env.other), proposal["proposal_id"], approve=True)
    await env.gateway.decide(await ctx(env), proposal["proposal_id"], approve=False)
    with pytest.raises(confirmation.ConfirmationError):
        await env.gateway.decide(await ctx(env), proposal["proposal_id"], approve=True)
    proposal = await download_proposal(env)
    store = env.gateway.confirmations._store
    record = await store.get(proposal["confirmation_id"])
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await store.save(record)
    with pytest.raises(confirmation.ConfirmationError):
        await env.gateway.decide(await ctx(env), proposal["proposal_id"], approve=True)
    related = await env.gateway.related(await ctx(env))
    assert next(r for r in related if r["invocation_id"] == proposal["proposal_id"])["state"] == "EXPIRED"


async def test_redis_failure_no_prepare_or_business_task(env, monkeypatch):
    unavailable = confirmation.ToolConfirmationService()
    unavailable._get_store = AsyncMock(side_effect=DependencyUnavailableError("Redis unavailable"))
    env.gateway.confirmations = unavailable
    with pytest.raises(DependencyUnavailableError):
        await download_proposal(env)
    assert not env.db.sync.scalars(select(AgentToolInvocationModel)).all()
    env.download.assert_not_called()


async def test_delegation_token_never_user_override_scope_or_replay(env, monkeypatch):
    calls = set()
    async def claim(key, value, **kwargs):
        if key in calls:
            return False
        calls.add(key)
        return True
    monkeypatch.setattr(delegation, "get_redis", lambda: SimpleNamespace(set=claim))
    token = await delegation.issue_delegation(await ctx(env))
    call_id = str(uuid4())
    context = await delegation.verify_delegation(env.db, token, "analysis.list_workflows", call_id)
    assert context.user_id == env.owner and context.extra["project_id"] == env.project
    with pytest.raises(ConflictError):
        await delegation.verify_delegation(env.db, token, "analysis.list_workflows", call_id)
    with pytest.raises(AuthenticationError):
        await delegation.verify_delegation(env.db, token, "downloads.submit", str(uuid4()))
    claims = jwt.decode(token, delegation._key(), algorithms=["HS256"], audience=delegation.AUDIENCE)
    claims["sub"] = env.other
    forged = jwt.encode(claims, "forged", algorithm="HS256")
    with pytest.raises(AuthenticationError):
        await delegation.verify_delegation(env.db, forged, "analysis.list_workflows", str(uuid4()))
    user = await env.db.get(UserModel, UUID(env.owner))
    user.token_version += 1
    with pytest.raises(AuthenticationError):
        await delegation.verify_delegation(env.db, token, "analysis.list_workflows", str(uuid4()))


async def test_delegation_redis_failure_closed(env, monkeypatch):
    from redis.exceptions import ConnectionError
    redis = SimpleNamespace(set=AsyncMock(side_effect=ConnectionError("offline")))
    monkeypatch.setattr(delegation, "get_redis", lambda: redis)
    token = await delegation.issue_delegation(await ctx(env))
    with pytest.raises(DependencyUnavailableError):
        await delegation.verify_delegation(env.db, token, "analysis.list_workflows", str(uuid4()))
    env.download.assert_not_called()


async def test_mcp_write_gate_covers_builtin_and_external_without_transport(env):
    from cygnusx.infrastructure.mcp.client import MCPClient
    client = MCPClient()
    client._call_with_reliability = AsyncMock()
    for tool in ("platform_submit_download", "rna_seq_submit", "atac_seq_submit", "cancel_task", "submit_analysis"):
        response = await client.call_tool(SimpleNamespace(name="isolated"), tool, {"user_confirmed": True})
        assert response["code"] == "WRITE_GATE_BLOCKED"
    client._call_with_reliability.assert_not_called()


async def test_contract_has_unique_names_and_no_write_discovery(env):
    catalog = capability_catalog()
    assert len({c.tool_name for c in catalog}) == len(catalog)
    assert all(c.side_effect != "task" for c in catalog)
    assert all(c.input_schema["additionalProperties"] is False for c in catalog)


async def test_isolated_submit_dedupe_and_ambiguous_recovery(env, monkeypatch):
    # Testing source-locked future adapter with stub business Service, never release
    # acceptance. SQLite lacks PostgreSQL row locking; Redis CAS is memory double.
    monkeypatch.setattr(module, "WRITE_RUNTIME_ACCEPTED", True)
    proposal = await download_proposal(env)
    context = await ctx(env)
    with pytest.raises(confirmation.ConfirmationError):
        await env.gateway.execute(context, proposal["proposal_id"])
    await env.gateway.decide(context, proposal["proposal_id"], approve=True)
    env.download.side_effect = TimeoutError("accepted but response lost")
    with pytest.raises(ConflictError):
        await env.gateway.execute(context, proposal["proposal_id"])
    with pytest.raises(ConflictError) as exc:
        await env.gateway.execute(context, proposal["proposal_id"])
    assert exc.value.code == "RECONCILIATION_REQUIRED"
    env.download.assert_called_once()


@pytest.mark.parametrize("flow", ["rna_seq", "atac_seq"])
async def test_analysis_prepare_real_validator_normalized_input_without_task(env, monkeypatch, flow):
    from cygnusx.domain.flow import submission_validator

    monkeypatch.setattr(submission_validator, "get_path_factory", module.get_path_factory)
    raw = env.root / "raw"
    raw.mkdir()
    (raw / "S1_R1.fastq.gz").write_bytes(b"tiny isolated test fixture")
    args = {"flow_id": flow, "arguments": {
        "name": "Tiny preview", "parameters": {"raw_data_path": "raw", "data_deliver": "deliver"},
        "sample_sheet": [{"sample": "S1", "sample_name": "S1", "group": "ctrl"},
                         {"sample": "S2", "sample_name": "S2", "group": "treat"}],
        "comparisons": [{"name": "TvsC", "Control": "ctrl", "Treat": "treat"}],
    }}
    result = await env.gateway.invoke(await ctx(env), "analysis.prepare", args)
    proposal = result["result"]
    assert proposal.get("operation") == "analysis.submit", proposal
    assert proposal["normalized_parameters"]["parameters"]["raw_data_path"] == str(raw)
    assert proposal["preview"]["sample_count"] == 2
    env.analysis.assert_not_called()
    assert len(env.gateway.confirmations._store._records) == 1


@pytest.mark.parametrize("bad_input", ["matrix", "missing", "escape"])
async def test_analysis_raw_matrix_missing_path_or_escape_no_proposal(env, monkeypatch, bad_input):
    from cygnusx.domain.flow import submission_validator

    monkeypatch.setattr(submission_validator, "get_path_factory", module.get_path_factory)
    (env.root / "counts.tsv").write_text("gene\tS1\nA\t1\n")
    path = {"matrix": "counts.tsv", "missing": "missing", "escape": "/etc"}[bad_input]
    result = await env.gateway.invoke(await ctx(env), "analysis.prepare", {
        "flow_id": "rna_seq", "arguments": {"name": "Invalid", "parameters": {"raw_data_path": path},
        "sample_sheet": [{"sample": "S1", "sample_name": "S1", "group": "ctrl"}]},
    })
    assert not result["result"]["valid"]
    assert "confirmation_id" not in result["result"]
    env.analysis.assert_not_called()


async def test_task_link_status_is_owner_session_project_scoped(env, monkeypatch):
    task_id = uuid4()
    task = SimpleNamespace(id=task_id, status="queued", error_message="", progress=0)
    monkeypatch.setattr(module.TaskService, "get_task", AsyncMock(return_value=task))
    with pytest.raises(NotFoundError):
        await env.gateway.task_status(await ctx(env), str(task_id))
    link = AgentToolInvocationModel(id=uuid4(), owner_id=env.owner, project_id=env.project,
        conversation_id="mouse", agent_kind="research_treasure_mouse", capability_id="downloads.prepare",
        request_id=str(uuid4()), parameters_hash="a" * 64, status="QUEUED", preview={}, task_id=task_id)
    env.db.add(link)
    await env.db.commit()
    result = await env.gateway.task_status(await ctx(env), str(task_id))
    assert result["status"] == "queued" and result["progress"] is None
    with pytest.raises(NotFoundError):
        await env.gateway.task_status(await ctx(env, "assistant"), str(task_id))
    with pytest.raises(NotFoundError):
        await env.gateway.task_status(await ctx(env, "other", env.other), str(task_id))


async def test_jwt_http_bff_approval_key_spoofing_and_gate(env, monkeypatch):
    from contextlib import asynccontextmanager

    import httpx
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from cygnusx.api import deps
    from cygnusx.api.v1 import agent_tools
    from cygnusx.core import security
    from cygnusx.core.exceptions import CygnusXError

    @asynccontextmanager
    async def factory():
        yield env.db

    monkeypatch.setattr(deps, "get_session_factory", lambda: factory)
    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(
        jwt_secret_key="isolated-phase2-jwt-secret-not-production", jwt_algorithm="HS256",
        access_token_expire_minutes=5))
    monkeypatch.setattr(deps, "_authenticate_api_key", AsyncMock(return_value=env.owner))
    app = FastAPI()
    app.include_router(agent_tools.router, prefix="/agent-tools")

    async def isolated_db():
        yield env.db
        await env.db.commit()

    app.dependency_overrides[deps.get_db] = isolated_db

    @app.exception_handler(CygnusXError)
    async def handle_error(request, error):
        return JSONResponse({"code": error.code}, status_code=error.status_code)

    human = {"Authorization": "Bearer " + security.create_access_token(env.owner, 0)}
    other = {"Authorization": "Bearer " + security.create_access_token(env.other, 0)}
    key = {"X-API-Key": "isolated-key", "X-User-Id": env.other}
    route = "/agent-tools/sessions/mouse"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(route + "/capabilities")).status_code == 401
        assert (await client.get(route + "/capabilities", headers=other)).status_code == 404
        created = await client.post(route + "/invoke", headers=key,
            json={"capability_id": "downloads.prepare", "arguments": {"accession": "SRR123"}})
        assert created.status_code == 200, created.text
        proposal_id = created.json()["result"]["proposal_id"]
        approval = route + f"/proposals/{proposal_id}/approve"
        assert (await client.post(approval, headers=key)).status_code == 401
        assert (await client.post(approval, headers=other)).status_code == 404
        assert (await client.post(approval, headers=human)).status_code == 200
        execution = route + f"/proposals/{proposal_id}/execute"
        assert (await client.post(execution, headers=human)).status_code == 403
        assert (await client.post(execution, headers=key)).status_code == 403
        env.download.assert_not_called()


async def test_concurrent_isolated_execute_returns_one_task_and_restores_link(env, monkeypatch):
    monkeypatch.setattr(module, "WRITE_RUNTIME_ACCEPTED", True)
    proposal = await download_proposal(env)
    context = await ctx(env)
    await env.gateway.decide(context, proposal["proposal_id"], approve=True)
    task = SimpleNamespace(id=uuid4(), status="queued", error_message="")
    async def submit(*args):
        await asyncio.sleep(0)
        return task
    env.download.side_effect = submit
    monkeypatch.setattr(module.TaskService, "get_task", AsyncMock(return_value=task))
    results = await asyncio.gather(
        env.gateway.execute(context, proposal["proposal_id"]),
        env.gateway.execute(context, proposal["proposal_id"]), return_exceptions=True,
    )
    assert len([r for r in results if isinstance(r, dict)]) == 1
    env.download.assert_awaited_once()
    assert (await env.gateway.execute(context, proposal["proposal_id"]))["task_id"] == str(task.id)
    env.download.assert_awaited_once()
    env.db.sync.expunge_all()
    restored = await module.AgentToolGateway(env.db).related(await ctx(env))
    assert restored[0]["task_id"] == str(task.id)


async def test_bound_parameters_and_operation_tampering_fail_closed(env, monkeypatch):
    monkeypatch.setattr(module, "WRITE_RUNTIME_ACCEPTED", True)
    proposal = await download_proposal(env)
    context = await ctx(env)
    await env.gateway.decide(context, proposal["proposal_id"], approve=True)
    record = await env.gateway.confirmations._store.get(proposal["confirmation_id"])
    record.normalized_request["parameters"]["accession"] = "SRR999"
    await env.gateway.confirmations._store.save(record)
    with pytest.raises(confirmation.ConfirmationError):
        await env.gateway.execute(context, proposal["proposal_id"])
    env.download.assert_not_called()
    env.analysis.assert_not_called()


async def test_dynamic_mcp_registry_bridge_and_gateway_share_contract(env, monkeypatch):
    from cygnusx.core import config
    from cygnusx.domain.mcp.entities import MCPServer
    from cygnusx.domain.mcp.value_objects import Transport
    from cygnusx.infrastructure.mcp import presets
    from cygnusx.infrastructure.mcp.client import MCPClient

    client = MCPClient()
    monkeypatch.setattr(config, "get_settings", lambda: env.settings)
    preset = presets.get_preset_by_name("cygnusx-tools")
    names = [t["name"] for t in preset["tools"]]
    for capability in capability_catalog():
        assert names.count(capability.tool_name) == 1
        projected = next(t for t in preset["tools"] if t["name"] == capability.tool_name)
        assert projected["inputSchema"] == capability.input_schema
    server = MCPServer(id=uuid4(), name="cygnusx-tools", transport=Transport.BUILTIN)
    response = await client._call_tool_inner(
        server, "bioops_analysis_list_workflows", {}, user_id=env.owner,
        context=await ctx(env, "assistant"),
    )
    assert response["success"]
    envelope = response["result"]
    assert envelope["success"]
    expected = await env.gateway.invoke(await ctx(env), "analysis.list_workflows", {})
    assert envelope["llm_payload"]["result"] == expected["result"]
    assert envelope["ui_payload"]["bioops"] == envelope["llm_payload"]
