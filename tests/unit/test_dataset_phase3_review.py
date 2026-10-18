"""Human review, immutable versions, execution revocation and bounded reconciliation."""

from __future__ import annotations

from uuid import UUID

import pytest
import sqlalchemy as sa

from cygnusx.application.schemas.dataset import AssetAttach, DatasetCreate
from cygnusx.application.services import dataset_import_service as import_module
from cygnusx.application.services.dataset_handoff_service import DatasetHandoffService
from cygnusx.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from cygnusx.infrastructure.database.models.dataset import (
    DatasetAnalysisLinkModel,
    DatasetAssetModel,
    DatasetVersionModel,
)
from cygnusx.infrastructure.database.models.user import UserModel
from tests.unit.test_dataset_import_handoff import imports as imports
from tests.unit.test_dataset_import_handoff import request
from tests.unit.test_dataset_phase3 import registry as registry

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_human_review_freeze_is_stable_and_revision_preserves_source(registry, imports):
    db, service, owner, _, project, _, _, files, _ = registry
    DatasetAnalysisLinkModel.__table__.create(db.sync.bind)
    ds = await service.create(owner, project, DatasetCreate(name="review"))
    version = db.sync.scalar(
        sa.select(DatasetVersionModel).where(DatasetVersionModel.dataset_id == ds.id)
    )
    version.source_snapshot = {"source": "original text"}
    asset = await service.attach_asset(
        owner, project, ds.id, version.id, AssetAttach(file_record_id=files[0].id)
    )
    await service.review_asset_role(
        owner, project, ds.id, version.id, asset.id, "metadata", "sample sheet from source"
    )
    assert asset.data_type == "UNKNOWN" and asset.checksum_status == "PENDING"
    await service.review_version(
        owner, project, ds.id, version.id, "bulk_rnaseq", "documented library strategy"
    )
    handoffs = DatasetHandoffService(db)
    frozen = await handoffs.manifest(owner, project, ds.id, version.id, freeze=True)
    assert frozen["provenance"]["review_annotations"]["assay_type"] == "bulk_rnaseq"
    assert frozen == await handoffs.manifest(owner, project, ds.id, version.id, freeze=True)
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
    from cygnusx.infrastructure.database.models.agent_tool_invocation import AgentToolInvocationModel

    context = ToolInvocationContext(
        user_id=str(owner), session_id="inspection", db=db,
        extra={"project_id": str(project)},
    )
    gateway = AgentToolGateway(db)
    inspected = await gateway._dataset_tool(
        context, AgentToolInvocationModel(), "dataset.inspect",
        {"dataset_id": str(ds.id), "version_id": str(version.id)},
    )
    assert inspected["handoff_frozen"] is True
    with pytest.raises(ValidationError):
        await service.review_version(owner, project, ds.id, version.id, "scrna", "new evidence")
    revision = await service.new_version(owner, project, ds.id, "new evidence")
    assert revision.number == 2 and not revision.handoff
    assert revision.source_snapshot == version.source_snapshot
    await service.review_version(owner, project, ds.id, revision.id, "scrna", "revised review")
    assert version.review_annotations["assay_type"] == "bulk_rnaseq"
    cloned = db.sync.scalar(
        sa.select(DatasetAssetModel).where(DatasetAssetModel.version_id == revision.id)
    )
    assert cloned.file_record_id == files[0].id and cloned.checksum_status == "PENDING"
    live = await gateway._dataset_tool(
        context, AgentToolInvocationModel(), "dataset.inspect",
        {"dataset_id": str(ds.id), "version_id": str(revision.id)},
    )
    assert live["manifest_hash"] and live["handoff_frozen"] is False


async def test_permission_and_quota_revoked_after_approval_prevent_submit(
    registry, imports, monkeypatch
):
    db, _, owner, _, project, *_ = registry
    service, *_ = imports
    proposal = await service.prepare(owner, project, request())
    iid = UUID(proposal["proposal_id"])
    await service.decide(owner, project, iid, True)
    monkeypatch.setattr(import_module, "require_import_write", lambda: None)
    user = await db.get(UserModel, owner)
    old_quota = user.storage_quota
    user.storage_quota = 0
    await db.flush()
    with pytest.raises(ValidationError, match="配额"):
        await service.execute(owner, project, iid)
    user.storage_quota = old_quota
    user.status = "disabled"
    await db.flush()
    with pytest.raises(NotFoundError):
        await service.execute(owner, project, iid)


async def test_reconciler_closed_gate_does_not_create_database_engine(monkeypatch):
    from cygnusx.infrastructure.celery_app.tasks import datasets
    from cygnusx.infrastructure.database import session

    def forbidden():
        raise AssertionError("closed gate touched database")

    monkeypatch.setattr(session, "create_unpooled_engine", forbidden)
    assert datasets.reconcile_dataset_jobs.run() == {"status": "BLOCKED", "reconciled": 0}


async def test_fastq_handoff_real_rna_validator_and_no_path_override(
    registry, imports, monkeypatch
):
    from cygnusx.application.schemas.dataset import DatasetAnalysisPrepare, SampleAttach
    from cygnusx.application.services import dataset_analysis_service as analysis_module
    from cygnusx.application.services.dataset_analysis_service import DatasetAnalysisService
    from cygnusx.domain.flow import submission_validator

    db, service, owner, _, project, _, _, files, sample = registry
    _, _, factory, settings = imports
    DatasetAnalysisLinkModel.__table__.create(db.sync.bind)
    monkeypatch.setattr(analysis_module, "get_settings", lambda: settings)
    monkeypatch.setattr(analysis_module, "require_dataset_read", lambda: None)
    monkeypatch.setattr(analysis_module, "get_path_factory", lambda: factory)
    monkeypatch.setattr(submission_validator, "get_path_factory", lambda: factory)
    ds = await service.create(
        owner, project, DatasetCreate(name="RNA fixture", assay_type="bulk_rnaseq")
    )
    version = db.sync.scalar(
        sa.select(DatasetVersionModel).where(DatasetVersionModel.dataset_id == ds.id)
    )
    path = factory.user_root(str(owner)) / "projects/owned/raw/sample1_R1.fastq"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"@r\nACGT\n+\nIIII\n")
    files[0].storage_path = path.relative_to(factory.data_root).as_posix()
    files[0].original_name, files[0].size = path.name, path.stat().st_size
    await service.attach_asset(
        owner, project, ds.id, version.id, AssetAttach(file_record_id=files[0].id, role="raw_reads")
    )
    await service.attach_sample(
        owner,
        project,
        ds.id,
        version.id,
        SampleAttach(
            sample_id=sample.id,
            sample_key="sample1",
            file_record_ids=[files[0].id],
            group="control",
            group_confirmed=True,
        ),
    )
    handoffs = DatasetHandoffService(db)
    await handoffs.verify(owner, project, ds.id, version.id)
    frozen = await handoffs.manifest(owner, project, ds.id, version.id, freeze=True)
    assert frozen["validation"]["compatible_flow_ids"] == ["rna_seq"]
    analysis = DatasetAnalysisService(db)
    args = DatasetAnalysisPrepare(
        flow_id="rna_seq",
        options={
            "parameters": {
                "Genome_Version": "hg38",
                "species": "Homo sapiens",
                "Library_Types": "fr-unstranded",
                "deg": False,
            }
        },
    )
    prepared = await analysis.prepare(owner, project, ds.id, version.id, args)
    assert "analysis_proposal_id" in prepared, prepared
    assert prepared["parameters"]["raw_data_path"].startswith("directory://projects/owned/")
    assert not prepared["worker_paths_verified"] and not prepared["write_enabled"]
    with pytest.raises(ValidationError, match="覆盖"):
        await analysis.prepare(
            owner,
            project,
            ds.id,
            version.id,
            args.model_copy(update={"options": {"parameters": {"raw_data_path": "/etc"}}}),
        )
    with pytest.raises(AuthorizationError):
        await analysis.execute(
            owner, project, ds.id, version.id, UUID(prepared["analysis_proposal_id"])
        )
    monkeypatch.setattr(analysis_module, "require_agent_write_gate", lambda operation: None)
    settings.analysis_submit_from_dataset = True
    with pytest.raises(ValidationError, match="Worker"):
        await analysis.execute(
            owner, project, ds.id, version.id, UUID(prepared["analysis_proposal_id"])
        )


async def test_processed_archive_reuses_real_file_registry_and_preserves_parent(
    registry, imports, monkeypatch
):
    import zipfile
    from types import SimpleNamespace

    from cygnusx.application.services import geo_processed_data_service as processed
    from cygnusx.core.exceptions import ConflictError
    from cygnusx.infrastructure.database.models.file import DirectoryModel
    from cygnusx.infrastructure.storage.file_registry import FileRegistry

    db, service, owner, _, project, _, _, files, _ = registry
    _, _, factory, settings = imports
    DirectoryModel.__table__.create(db.sync.bind)

    async def refresh(row):
        db.sync.refresh(row)

    db.refresh = refresh
    factory.project_dir = lambda uid, slug: factory.user_root(uid) / "projects" / slug
    factory.relative_to_root = lambda path: str(path.relative_to(factory.data_root))
    settings.dataset_archive_max_files = 10
    settings.dataset_archive_max_file_bytes = 1000
    settings.dataset_archive_max_ratio = 100
    monkeypatch.setattr(processed, "get_path_factory", lambda: factory)
    monkeypatch.setattr(processed, "get_settings", lambda: settings)
    monkeypatch.setattr(processed, "require_import_write", lambda: None)
    path = factory.user_root(str(owner)) / "projects/owned/data.zip"
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("counts.tsv", "gene_id\ts1\nsafe\t2\n")
    original = path.read_bytes()
    files[0].storage_path = path.relative_to(factory.data_root).as_posix()
    files[0].size, files[0].original_name = path.stat().st_size, path.name
    ds = await service.create(owner, project, DatasetCreate(name="archive"))
    version = db.sync.scalar(
        sa.select(DatasetVersionModel).where(DatasetVersionModel.dataset_id == ds.id)
    )
    asset = await service.attach_asset(
        owner, project, ds.id, version.id, AssetAttach(file_record_id=files[0].id)
    )

    async def stat(relative):
        return {"size": (factory.data_root / relative).stat().st_size}

    real_registry = FileRegistry(db, path_factory=factory, backend=SimpleNamespace(stat=stat))
    worker = processed.GeoProcessedDataService(db, registry=real_registry)
    expanded = await worker.expand(owner, project, ds.id, version.id, asset.id)
    assert len(expanded["assets"]) == 1 and path.read_bytes() == original
    assert asset.role == "archive" and asset.checksum_status == "VERIFIED"
    child = db.sync.scalar(
        sa.select(DatasetAssetModel).where(
            DatasetAssetModel.id == UUID(expanded["assets"][0]["asset_id"])
        )
    )
    assert child.classification["parent_archive_file_record_id"] == str(files[0].id)
    assert child.data_type == "UNKNOWN"
    with pytest.raises(ConflictError):
        await worker.expand(owner, project, ds.id, version.id, asset.id)


async def test_verified_counts_metadata_human_groups_prepare_real_flow(
    registry, imports, monkeypatch
):
    from cygnusx.application.schemas.dataset import DatasetAnalysisPrepare, SampleAttach
    from cygnusx.application.services import dataset_analysis_service as analysis_module
    from cygnusx.application.services import flow_service
    from cygnusx.application.services.dataset_analysis_service import DatasetAnalysisService
    from cygnusx.domain.flow import submission_validator
    from cygnusx.infrastructure.database.models.file import FileRecordModel, SampleModel

    db, service, owner, _, project, *_ = registry
    _, _, factory, settings = imports
    DatasetAnalysisLinkModel.__table__.create(db.sync.bind)
    settings.counts_deg_flow_enabled = True
    monkeypatch.setattr(analysis_module, "require_dataset_read", lambda: None)
    for mod in (analysis_module, flow_service):
        monkeypatch.setattr(mod, "get_settings", lambda: settings)
    for mod in (analysis_module, submission_validator):
        monkeypatch.setattr(mod, "get_path_factory", lambda: factory)
    ds = await service.create(
        owner, project, DatasetCreate(name="counts", assay_type="bulk_rnaseq")
    )
    version = db.sync.scalar(
        sa.select(DatasetVersionModel).where(DatasetVersionModel.dataset_id == ds.id)
    )
    version.source_snapshot = {
        "samples": [{"processing": ["featureCounts raw gene counts"]}],
        "source_evidence": [
            {
                "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE1",
                "response_sha256": "a" * 64,
            }
        ],
    }
    records = []
    for name, text, role in [
        (
            "counts.tsv",
            "gene_id\tc1\tc2\tt1\tt2\ngeneA\t1\t2\t9\t10\ngeneB\t20\t20\t5\t6\n",
            "raw_counts",
        ),
        (
            "samples.tsv",
            "sample_id\tgroup\nc1\tcontrol\nc2\tcontrol\nt1\ttreated\nt2\ttreated\n",
            "metadata",
        ),
    ]:
        path = factory.user_root(str(owner)) / "projects/owned" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        record = FileRecordModel(
            user_id=owner,
            original_name=name,
            storage_path=path.relative_to(factory.data_root).as_posix(),
            size=path.stat().st_size,
            directory="projects/owned",
            storage_backend="local",
            owner_scope="personal",
            lifecycle_status="active",
            status="active",
        )
        db.add(record)
        await db.flush()
        records.append(record)
        await service.attach_asset(
            owner, project, ds.id, version.id, AssetAttach(file_record_id=record.id, role=role)
        )
    for key, group in [("c1", "control"), ("c2", "control"), ("t1", "treated"), ("t2", "treated")]:
        sample = SampleModel(user_id=owner, name=key, file_ids=[], meta={})
        db.add(sample)
        await db.flush()
        await service.attach_sample(
            owner,
            project,
            ds.id,
            version.id,
            SampleAttach(
                sample_id=sample.id,
                sample_key=key,
                file_record_ids=[records[0].id],
                group=group,
                group_confirmed=True,
            ),
        )
    handoffs = DatasetHandoffService(db)
    verified = await handoffs.verify(owner, project, ds.id, version.id)
    assert verified["validation"]["compatible_flow_ids"] == ["counts_deg"], verified
    await handoffs.manifest(owner, project, ds.id, version.id, freeze=True)
    analysis = DatasetAnalysisService(db)
    args = DatasetAnalysisPrepare(
        flow_id="counts_deg",
        options={
            "parameters": {"design": "~ group", "reference": "control", "treatment": "treated"}
        },
    )
    prepared = await analysis.prepare(owner, project, ds.id, version.id, args)
    assert "analysis_proposal_id" in prepared, prepared
    assert prepared["parameters"]["count_matrix"].startswith("file://")
    assert not prepared["write_enabled"]
    rejected = await analysis.decide(
        owner, project, ds.id, version.id, UUID(prepared["analysis_proposal_id"]), False
    )
    assert rejected["state"] == "REJECTED" and not rejected["write_enabled"]
    restored = await analysis.view(
        owner, project, ds.id, version.id, UUID(prepared["analysis_proposal_id"])
    )
    assert restored["dataset_id"] == str(ds.id)
    assert restored["dataset_version_id"] == str(version.id)
    assert restored["expires_at"]
    with pytest.raises(ValidationError):
        await analysis.prepare(
            owner,
            project,
            ds.id,
            version.id,
            args.model_copy(update={"options": {"parameters": {"source_reviewed": True}}}),
        )


async def test_rest_jwt_owner_scope_and_closed_execute(registry, imports, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import httpx
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from cygnusx.api import deps
    from cygnusx.api.v1 import datasets
    from cygnusx.core import security
    from cygnusx.core.exceptions import CygnusXError

    db, _, owner, other, project, *_ = registry
    service, *_ = imports
    proposal = await service.prepare(owner, project, request())

    @asynccontextmanager
    async def factory():
        yield db

    monkeypatch.setattr(deps, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="phase3-isolated-jwt-secret-only-for-tests",
            jwt_algorithm="HS256",
            access_token_expire_minutes=5,
        ),
    )
    monkeypatch.setattr(deps, "_authenticate_api_key", AsyncMock(return_value=str(owner)))
    monkeypatch.setattr(import_module, "metadata_adapter", lambda: service.geo)
    app = FastAPI()
    app.include_router(datasets.router)

    async def isolated_db():
        yield db
        await db.commit()

    app.dependency_overrides[deps.get_db] = isolated_db

    @app.exception_handler(CygnusXError)
    async def handle(request, error):
        return JSONResponse({"code": error.code}, status_code=error.status_code)

    human = {"Authorization": "Bearer " + security.create_access_token(str(owner), 0)}
    foreign = {"Authorization": "Bearer " + security.create_access_token(str(other), 0)}
    key = {"X-API-Key": "test-key", "X-User-Id": str(other)}
    route = f"/projects/{project}/import-proposals/{proposal['proposal_id']}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(route)).status_code == 401
        assert (await client.get(route, headers=foreign)).status_code == 404
        assert (await client.get(route, headers=human)).status_code == 200
        assert (await client.post(route + "/approve", headers=key)).status_code == 401
        assert (await client.post(route + "/approve", headers=human)).status_code == 200
        assert (await client.post(route + "/execute", headers=human)).status_code == 403


async def test_same_geo_explicit_new_import_versions_do_not_overwrite(
    registry, imports, monkeypatch
):
    from types import SimpleNamespace

    from cygnusx.infrastructure.database.models.task import TaskModel

    db, service, owner, _, project, *_ = registry
    importer, *_ = imports
    ds = await service.create(owner, project, DatasetCreate(name="same GSE"))
    original = db.sync.scalar(
        sa.select(DatasetVersionModel).where(DatasetVersionModel.dataset_id == ds.id)
    )
    original.source_snapshot = {"retained": "original"}
    monkeypatch.setattr(import_module, "require_import_write", lambda: None)

    async def submit(self, uid, args):
        task = TaskModel(user_id=owner, flow_id="download", name="fixture", status="pending")
        db.add(task)
        await db.flush()
        return SimpleNamespace(id=task.id)

    monkeypatch.setattr(import_module.DownloadService, "submit", submit)
    versions = []
    for _ in range(2):
        req = request().model_copy(update={"dataset_id": ds.id})
        prepared = await importer.prepare(owner, project, req)
        iid = UUID(prepared["proposal_id"])
        await importer.decide(owner, project, iid, True)
        result = await importer.execute(owner, project, iid)
        versions.append(result["dataset_version_id"])
    assert versions[0] != versions[1]
    assert original.source_snapshot == {"retained": "original"}
    assert (
        len(
            db.sync.scalars(
                sa.select(DatasetVersionModel).where(DatasetVersionModel.dataset_id == ds.id)
            ).all()
        )
        == 3
    )
