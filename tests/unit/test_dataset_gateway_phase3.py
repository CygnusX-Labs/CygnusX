"""Dataset capabilities share the Phase2 authority and remain fail-closed."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from cygnusx.application.schemas.agent_tools import capability_catalog
from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
from cygnusx.core.exceptions import AuthorizationError, NotFoundError
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


async def test_global_public_inspection_but_persistent_prepare_requires_project(env, monkeypatch):
    from unittest.mock import AsyncMock

    from cygnusx.application.services import dataset_import_service as imports
    from cygnusx.core.exceptions import ValidationError
    from cygnusx.infrastructure.database.models.chat import ChatSessionModel

    env.settings.dataset_discovery_readonly = True
    monkeypatch.setattr(imports, "get_settings", lambda: env.settings)
    geo = AsyncMock()
    geo.resolve.return_value = {
        "primary_accession": "GSE123",
        "status": "RESOLVED",
        "runs": [],
        "files": [],
        "samples": [],
        "source_evidence": [],
        "confidence_flags": ["raw_runs_not_resolved"],
    }
    monkeypatch.setattr(imports, "metadata_adapter", lambda: geo)
    from sqlalchemy import select

    session = (
        await env.db.execute(select(ChatSessionModel).where(ChatSessionModel.session_id == "mouse"))
    ).scalar_one()
    session.project_id = None
    await env.db.flush()
    gateway = AgentToolGateway(env.db)
    context = await gateway.context(env.owner, "mouse")
    result = await gateway.invoke(context, "dataset.discover", {"accession": "GSE123"})
    assert result["result"]["raw"]["runs"] == []
    assert result["result"]["confidence_flags"] == ["raw_runs_not_resolved"]
    geo.resolve.assert_awaited_once_with("GSE123")
    with pytest.raises(ValidationError) as exc:
        await gateway.invoke(context, "dataset.list_project_assets", {})
    assert exc.value.code == "PROJECT_REQUIRED"


async def test_global_inspection_flag_and_module_still_fail_closed(env, monkeypatch):
    from unittest.mock import AsyncMock

    from cygnusx.application.services import dataset_import_service as imports
    from cygnusx.infrastructure.database.models.user import UserModel

    geo = AsyncMock()
    monkeypatch.setattr(imports, "metadata_adapter", lambda: geo)
    gateway = AgentToolGateway(env.db)
    context = await gateway.context(env.owner, "mouse")
    with pytest.raises(AuthorizationError):
        await gateway.invoke(context, "dataset.discover", {"accession": "GSE123"})
    env.settings.dataset_discovery_readonly = True
    user = await env.db.get(UserModel, __import__("uuid").UUID(env.owner))
    user.disabled_modules = ["files"]
    await env.db.flush()
    with pytest.raises(AuthorizationError):
        await gateway.invoke(context, "dataset.discover", {"accession": "GSE123"})
    geo.resolve.assert_not_awaited()


async def test_archived_session_invalidates_previously_built_context(env, monkeypatch):
    from unittest.mock import AsyncMock

    from sqlalchemy import select

    from cygnusx.application.services import dataset_import_service as imports
    from cygnusx.infrastructure.database.models.chat import ChatSessionModel

    env.settings.dataset_discovery_readonly = True
    geo = AsyncMock()
    monkeypatch.setattr(imports, "metadata_adapter", lambda: geo)
    gateway = AgentToolGateway(env.db)
    stale_context = await gateway.context(env.owner, "mouse")
    session = (
        await env.db.execute(select(ChatSessionModel).where(ChatSessionModel.session_id == "mouse"))
    ).scalar_one()
    session.status = "archived"
    await env.db.flush()

    with pytest.raises(NotFoundError):
        await gateway.invoke(stale_context, "dataset.discover", {"accession": "GSE123"})
    geo.resolve.assert_not_awaited()


async def test_prepare_import_gateway_persists_invocation_without_creating_task_or_files(
    env, monkeypatch
):
    import sqlalchemy as sa

    from cygnusx.application.schemas.dataset import ImportPrepare
    from cygnusx.application.services import dataset_import_service as imports
    from cygnusx.infrastructure.database.models.agent_tool_invocation import (
        AgentToolInvocationModel,
    )
    from cygnusx.infrastructure.database.models.dataset import (
        DatasetIngestionModel,
        DatasetModel,
        DatasetVersionModel,
    )
    from cygnusx.infrastructure.database.models.task import TaskModel
    from tests.unit.test_dataset_import_handoff import FixtureGeo

    for model in (DatasetModel, DatasetVersionModel, DatasetIngestionModel, TaskModel):
        model.__table__.create(env.engine)

    env.settings.dataset_discovery_readonly = True
    service_settings = imports.get_settings().model_copy(
        update={
            "dataset_discovery_readonly": True,
            "dataset_import_write": False,
            "dataset_import_max_bytes": 10_000,
        }
    )
    geo = FixtureGeo()
    monkeypatch.setattr(imports, "get_settings", lambda: service_settings)
    monkeypatch.setattr(imports, "metadata_adapter", lambda: geo)
    monkeypatch.setattr(
        imports,
        "get_path_factory",
        lambda: SimpleNamespace(user_root=lambda _: env.root),
    )
    gateway = AgentToolGateway(env.db)
    context = await gateway.context(env.owner, "mouse")
    req = ImportPrepare(
        accession="GSE1",
        mode="raw",
        selected_ids=["SRR1"],
        name="isolated fixture",
        request_key=uuid4(),
        max_bytes=10_000,
    )

    result = await gateway.invoke(
        context,
        "dataset.prepare_import",
        {"request": req.model_dump(mode="json")},
    )

    ingestion = await env.db.get(DatasetIngestionModel, UUID(result["result"]["ingestion_id"]))
    invocation = await env.db.get(AgentToolInvocationModel, UUID(result["invocation_id"]))
    assert ingestion is not None and invocation is not None
    assert ingestion.invocation_id == invocation.id
    assert ingestion.agent_session_id == "mouse"
    assert ingestion.state == "PREPARED"
    assert result["result"]["write_enabled"] is False
    assert not env.db.sync.scalars(sa.select(TaskModel)).all()
    assert list(env.root.iterdir()) == []
