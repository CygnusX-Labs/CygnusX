"""Shared read-only catalog with real isolated SQL authorization; no CLI/network."""

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import select

from cygnusx.application.schemas.agent_tools import CAPABILITY_MODELS
from cygnusx.application.schemas.download_capability import DownloadCapabilities
from cygnusx.application.services import agent_tool_gateway as gateway_module
from cygnusx.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from cygnusx.infrastructure.database.models.agent_tool_invocation import AgentToolInvocationModel
from cygnusx.infrastructure.database.models.chat import ChatSessionModel
from cygnusx.infrastructure.database.models.dataset import DatasetModel, DatasetVersionModel
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.tools.download import config as configuration
from tests.unit.test_agent_tools_phase2 import env as env
from tests.unit.test_dataset_phase3 import registry as registry

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def describe(env, session="mouse", arguments=None):
    context = await env.gateway.context(env.owner, session)
    return (await env.gateway.invoke(context, "downloads.describe_capabilities", arguments or {}))[
        "result"
    ]


async def test_twelve_capabilities_distinguish_code_configuration_and_runtime(env):
    result = await describe(env)
    entries = {e["source_type"]: e for e in result["capabilities"]}
    assert set(entries) == {
        "geo_metadata",
        "ncbi_sra",
        "ena_fastq",
        "geo_supplementary",
        "http_direct_link",
        "https_direct_link",
        "ftp",
        "oss",
        "tos",
        "obs",
        "cloud_drive",
        "existing_dataset_assets",
    }
    assert entries["cloud_drive"]["states"] == ["NOT_IMPLEMENTED", "UNKNOWN", "EXECUTION_BLOCKED"]
    for entry in entries.values():
        assert entry["runtime_verification"] == "UNKNOWN"
        assert "RUNTIME_VERIFIED" not in entry["states"]
        assert entry["execution_allowed"] is False
        if entry["transport_required"]:
            assert "EXECUTION_BLOCKED" in entry["states"]
    assert gateway_module.WRITE_RUNTIME_ACCEPTED is False
    from cygnusx.infrastructure.download.policy import DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED

    assert DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED is False
    env.download.assert_not_called()
    env.analysis.assert_not_called()
    assert all(row.task_id is None for row in env.db.sync.scalars(select(AgentToolInvocationModel)))
    assert env.gateway.confirmations._store is None
    assert list(env.root.iterdir()) == []


async def test_same_business_schema_and_projection_for_both_agents(env):
    a, b = await describe(env), await describe(env, "assistant")
    assert a == b
    for sid in ("mouse", "assistant"):
        catalog = env.gateway.catalog(await env.gateway.context(env.owner, sid))
        entry = next(e for e in catalog if e["capability_id"] == "downloads.describe_capabilities")
        assert (
            entry["input_schema"] == CAPABILITY_MODELS[entry["capability_id"]].model_json_schema()
        )


@pytest.mark.parametrize(
    "key",
    ["owner_id", "project_id", "session_id", "scopes", "runtime_verified", "caller_kind", "states"],
)
async def test_model_cannot_forge_catalog_context_or_certification(env, key):
    with pytest.raises(SchemaError):
        await describe(env, arguments={key: "forged"})
    assert not env.db.sync.scalars(select(AgentToolInvocationModel)).all()


async def test_configuration_changes_never_certify_runtime(env, monkeypatch):
    settings = configuration.get_settings().model_copy(update={"enable_direct_download": False})
    config = configuration.get_download_config().model_copy(deep=True)
    config.features.direct_link = False
    monkeypatch.setattr(configuration, "get_download_config", lambda: config)
    monkeypatch.setattr(configuration, "get_settings", lambda: settings)
    before = await describe(env)
    config.features.direct_link = True
    after = await describe(env)

    def lookup(r):
        return next(e for e in r["capabilities"] if e["source_type"] == "http_direct_link")

    assert "CONFIGURED" not in lookup(before)["states"]
    assert "CONFIGURED" in lookup(after)["states"]
    assert lookup(after)["runtime_verification"] == "UNKNOWN"
    assert lookup(after)["execution_allowed"] is False
    # REST response validation/round-trip stays compatible with the existing DTO.
    DownloadCapabilities.model_validate(configuration.describe_download_capabilities())


@pytest.mark.parametrize("module", ["downloads", "treasure-mouse"])
async def test_disabled_module_denies_even_preexisting_context(env, module):
    context = await env.gateway.context(env.owner, "mouse")
    user = await env.db.get(UserModel, UUID(env.owner))
    user.disabled_modules = [module]
    with pytest.raises(AuthorizationError):
        await env.gateway.invoke(context, "downloads.describe_capabilities", {})


async def test_files_scope_filters_dataset_queries_and_unknown_agent_is_not_catalogued(env):
    user = await env.db.get(UserModel, UUID(env.owner))
    user.disabled_modules = ["files"]
    result = await describe(env)
    assert "existing_dataset_assets" not in {e["source_type"] for e in result["capabilities"]}
    context = await env.gateway.context(env.owner, "mouse")
    context.extra["agent_kind"] = "flow_agent"
    assert env.gateway.catalog(context) == []
    with pytest.raises(AuthorizationError):
        await env.gateway.context(env.owner, "mouse", expected_agent="platform_ai")


async def test_reduced_scope_is_not_expanded_by_context_refresh(env):
    context = await env.gateway.context(env.owner, "mouse")
    context.extra["scopes"] = ["read:tasks"]
    with pytest.raises(AuthorizationError):
        await env.gateway.invoke(context, "downloads.describe_capabilities", {})


async def test_catalog_without_project_is_safe_but_assets_require_project(env, monkeypatch):
    session = env.db.sync.scalar(
        select(ChatSessionModel).where(ChatSessionModel.session_id == "mouse")
    )
    session.project_id = None
    env.settings.dataset_discovery_readonly = True
    result = await describe(env)
    assert all(not e["project_context_available"] for e in result["capabilities"])
    with pytest.raises(ValidationError) as error:
        await env.gateway.invoke(
            await env.gateway.context(env.owner, "mouse"), "dataset.list_project_assets", {}
        )
    assert error.value.code == "PROJECT_REQUIRED"
    # No UUID(None) error on the existing task status fallback without a project.
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        gateway_module.TaskService, "get_task", AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    )
    with pytest.raises(NotFoundError):
        await env.gateway.task_status(await env.gateway.context(env.owner, "mouse"), str(uuid4()))


async def test_existing_assets_have_scoped_version_handles(env):
    for model in (DatasetModel, DatasetVersionModel):
        model.__table__.create(env.engine)
    ids = []
    for owner, project in (
        (env.owner, env.project),
        (env.owner, env.project2),
        (env.other, env.foreign_project),
    ):
        dataset_id, version_id = uuid4(), uuid4()
        env.db.add(
            DatasetModel(id=dataset_id, user_id=UUID(owner), project_id=UUID(project), name="owned")
        )
        env.db.add(
            DatasetVersionModel(
                id=version_id, dataset_id=dataset_id, number=1, initiated_by=UUID(owner)
            )
        )
        ids.append((str(dataset_id), str(version_id)))
    await env.db.flush()
    env.settings.dataset_discovery_readonly = True
    response = await env.gateway.invoke(
        await env.gateway.context(env.owner, "mouse"), "dataset.list_project_assets", {}
    )
    assert [e["id"] for e in response["result"]] == [ids[0][0]]
    assert response["result"][0]["versions"][0]["version_id"] == ids[0][1]
    with pytest.raises(NotFoundError):
        await env.gateway.context(env.other, "mouse")
    context = await env.gateway.context(env.owner, "mouse")
    session = env.db.sync.scalar(
        select(ChatSessionModel).where(ChatSessionModel.session_id == "mouse")
    )
    session.project_id = env.foreign_project
    with pytest.raises(AuthorizationError):
        await env.gateway.invoke(context, "dataset.list_project_assets", {})
    env.download.assert_not_called()


@pytest.mark.parametrize("accession", ["GSE123", "SRR123"])
async def test_gateway_reuses_bounded_metadata_resolver_without_execution(
    env, monkeypatch, accession
):
    import httpx

    from cygnusx.application.services import dataset_import_service as imports
    from cygnusx.infrastructure.geo.adapter import GeoMetadataAdapter

    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "www.ncbi.nlm.nih.gov":
            return httpx.Response(200, text="^SERIES = GSE123\n!Series_title = fixture\n")
        return httpx.Response(
            200,
            text=(
                "run_accession\texperiment_accession\tsample_accession\tstudy_accession\tfastq_ftp\tfastq_bytes\n"
                "SRR123\tSRX123\tSRS123\tSRP123\tftp.sra.ebi.ac.uk/vol1/a.fastq.gz\t20\n"
            ),
        )

    geo = GeoMetadataAdapter(transport=httpx.MockTransport(handler), request_interval=0)
    env.settings.dataset_discovery_readonly = True
    monkeypatch.setattr(imports, "get_settings", lambda: env.settings)
    monkeypatch.setattr(imports, "metadata_adapter", lambda: geo)
    response = await env.gateway.invoke(
        await env.gateway.context(env.owner, "mouse"), "dataset.discover", {"accession": accession}
    )
    assert response["result"]["primary_accession"] == accession
    assert response["result"]["raw"]["runtime_verified"] is False
    assert requests and all(r.url.scheme == "https" for r in requests)
    env.download.assert_not_called()
    assert env.gateway.confirmations._store is None
    user = await env.db.get(UserModel, UUID(env.owner))
    user.disabled_modules = ["downloads"]
    before = len(requests)
    with pytest.raises(AuthorizationError):
        await env.gateway.invoke(
            await env.gateway.context(env.owner, "mouse"),
            "dataset.discover",
            {"accession": accession},
        )
    assert len(requests) == before


async def test_prepare_remains_single_confirmation_without_task_or_directories(env):
    response = await env.gateway.invoke(
        await env.gateway.context(env.owner, "mouse"), "downloads.prepare", {"accession": "SRR123"}
    )
    assert response["result"]["operation"] == "downloads.submit"
    assert len(env.gateway.confirmations._store._records) == 1
    assert all(row.task_id is None for row in env.db.sync.scalars(select(AgentToolInvocationModel)))
    env.download.assert_not_called()
    assert list(env.root.iterdir()) == []


async def test_gateway_read_feature_disabled_before_catalog_or_audit(env):
    context = await env.gateway.context(env.owner, "mouse")
    env.settings.tool_gateway_read_enabled = False
    with pytest.raises(AuthorizationError) as error:
        await env.gateway.invoke(context, "downloads.describe_capabilities", {})
    assert error.value.code == "FEATURE_DISABLED"
    assert not env.db.sync.scalars(select(AgentToolInvocationModel)).all()


async def test_node_delegation_retains_restricted_scope_for_catalog(env, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from cygnusx.application.services import agent_tool_delegation as delegation

    context = await env.gateway.context(env.owner, "mouse")
    context.extra["scopes"] = ["read:discovery"]
    token = await delegation.issue_delegation(context)
    monkeypatch.setattr(
        delegation, "get_redis", lambda: SimpleNamespace(set=AsyncMock(return_value=True))
    )
    delegated = await delegation.verify_delegation(
        env.db, token, "downloads.describe_capabilities", str(uuid4())
    )
    assert delegated.extra["scopes"] == ["read:discovery"]
    result = (await env.gateway.invoke(delegated, "downloads.describe_capabilities", {}))["result"]
    assert result["available_tools"] == ["downloads.describe_capabilities"]
    assert all(not entry["query_tools"] for entry in result["capabilities"])


async def test_existing_filerecord_assets_use_original_handoff_queries(registry):
    from cygnusx.application.schemas.dataset import AssetAttach, DatasetCreate
    from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
    from cygnusx.infrastructure.database.models.dataset import DatasetIngestionModel

    db, service, owner, other, project, _, foreign, files, _ = registry
    DatasetIngestionModel.__table__.create(db.sync.bind)
    dataset = await service.create(owner, project, DatasetCreate(name="existing"))
    version = db.sync.scalar(
        select(DatasetVersionModel).where(DatasetVersionModel.dataset_id == dataset.id)
    )
    await service.attach_asset(
        owner, project, dataset.id, version.id, AssetAttach(file_record_id=files[0].id)
    )
    gateway = gateway_module.AgentToolGateway(db)
    args = {"dataset_id": str(dataset.id), "version_id": str(version.id)}
    context = ToolInvocationContext(
        user_id=str(owner), session_id="fixture", db=db, extra={"project_id": str(project)}
    )
    result = await gateway._dataset_tool(
        context, AgentToolInvocationModel(), "dataset.list_files", args
    )
    assert result["assets"][0]["file_record_id"] == str(files[0].id)
    assert result["assets"][0]["checksum_status"] == "PENDING"
    assert result["validation"]["worker_paths_verified"] is False
    for uid, pid in ((owner, foreign), (other, project)):
        invalid = context.model_copy(
            update={"user_id": str(uid), "extra": {"project_id": str(pid)}}
        )
        with pytest.raises(NotFoundError):
            await gateway._dataset_tool(
                invalid, AgentToolInvocationModel(), "dataset.list_files", args
            )


async def test_existing_manual_capability_endpoint_preserves_v1_response(env):
    import httpx
    from fastapi import FastAPI

    from cygnusx.api.deps import get_current_user_id
    from cygnusx.api.v1.downloads import router

    app = FastAPI()
    app.include_router(router, prefix="/downloads")

    async def owner_dependency():
        return env.owner

    app.dependency_overrides[get_current_user_id] = owner_dependency
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://isolated"
    ) as client:
        response = await client.get("/downloads/capabilities")
    assert response.status_code == 200
    view = DownloadCapabilities.model_validate(response.json())
    assert view.schema_version == "cygnusx.download_capabilities.v1"
    assert len(view.sources) == 4
    assert len(view.capabilities) == 12
    assert view.write_enabled is False
    env.download.assert_not_called()
