"""Real isolated SQL/services + explicit confirmation/HTTP/download doubles."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from pydantic import ValidationError as SchemaError

from cygnusx.application.schemas.dataset import (
    ImportPrepare,
)
from cygnusx.application.services import dataset_handoff_service as handoff_module
from cygnusx.application.services import dataset_import_service as module
from cygnusx.application.services import tool_confirmation_service as confirmations
from cygnusx.application.services.dataset_handoff_service import DatasetHandoffService
from cygnusx.application.services.dataset_import_service import DatasetImportService
from cygnusx.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cygnusx.infrastructure.database.models.dataset import (
    DatasetIngestionModel,
    DatasetVersionModel,
)
from cygnusx.infrastructure.database.models.file import FileRecordModel
from cygnusx.infrastructure.database.models.task import TaskModel
from tests.unit.test_dataset_phase3 import registry as registry

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class FixtureGeo:
    def __init__(self):
        self.candidate = {
            "primary_accession": "GSE1",
            "repository": "GEO",
            "status": "NEEDS_REVIEW",
            "assay_type": "bulk_rnaseq",
            "source_evidence": [
                {
                    "url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE1",
                    "response_sha256": "a" * 64,
                }
            ],
            "related_accessions": [{"from": "GSM1", "to": "SRX1"}, {"from": "SRX1", "to": "SRR1"}],
            "samples": [
                {
                    "sample_key": "GSM1",
                    "title": ["unknown disease"],
                    "organism": ["Homo sapiens"],
                    "processing": ["featureCounts raw gene counts"],
                }
            ],
            "runs": [
                {
                    "run_accession": "SRR1",
                    "library_layout": "SINGLE",
                    "files": [{"url": "https://ftp.sra.ebi.ac.uk/vol1/a.fastq.gz", "size": 20}],
                }
            ],
            "files": [
                {
                    "url": "https://ftp.ncbi.nlm.nih.gov/geo/counts.tsv",
                    "size": None,
                    "original_name": "counts.tsv",
                    "data_type": "UNKNOWN",
                }
            ],
        }

    async def resolve(self, value, **kwargs):
        return deepcopy(self.candidate)


@pytest.fixture
def imports(registry, monkeypatch, tmp_path):
    db, _, owner, _, project, *_ = registry
    for model in (TaskModel, DatasetIngestionModel):
        model.__table__.create(db.sync.bind)
    root = tmp_path / "storage"
    user_root = root / "users" / str(owner)
    user_root.mkdir(parents=True)
    factory = SimpleNamespace(data_root=root, user_root=lambda uid: root / "users" / str(uid))
    monkeypatch.setattr(module, "get_path_factory", lambda: factory)
    monkeypatch.setattr(handoff_module, "get_path_factory", lambda: factory)
    from cygnusx.application.services import managed_file_resolver

    monkeypatch.setattr(managed_file_resolver, "get_path_factory", lambda: factory)
    settings = SimpleNamespace(
        download_admission_profiles={},
        dataset_discovery_readonly=True,
        dataset_import_write=True,
        dataset_import_max_bytes=10000,
        dataset_validation_max_rows=100,
        dataset_validation_max_columns=100,
        dataset_validation_max_line_bytes=10000,
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(handoff_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        confirmations,
        "_confirmation_service",
        confirmations.ToolConfirmationService(confirmations._MemoryStore()),
    )
    geo = FixtureGeo()
    service = DatasetImportService(db, geo=geo)
    return service, geo, factory, settings


def request(**kwargs):
    return ImportPrepare(
        accession="GSE1",
        mode="raw",
        selected_ids=["SRR1"],
        name="synthetic",
        request_key=uuid4(),
        max_bytes=10000,
        **kwargs,
    )


async def test_prepare_import_no_task_file_effect_idempotent_and_gate_closed(registry, imports):
    db, _, owner, _, project, *_ = registry
    service, geo, factory, settings = imports
    req = request()
    before = set(factory.data_root.rglob("*"))
    proposal = await service.prepare(owner, project, req)
    restored = await service.prepare(owner, project, req)
    assert restored["proposal_id"] == proposal["proposal_id"]
    assert not db.sync.scalars(sa.select(TaskModel)).all()
    assert set(factory.data_root.rglob("*")) == before
    with pytest.raises(ConflictError):
        await service.prepare(owner, project, req.model_copy(update={"name": "tampered"}))
    await service.decide(
        owner, project, UUID(proposal["proposal_id"]), True, auth_session_or_jti_hash="a" * 64
    )
    with pytest.raises(AuthorizationError, match="门禁"):
        await service.execute(owner, project, UUID(proposal["proposal_id"]))
    assert not db.sync.scalars(sa.select(TaskModel)).all()
    assert not proposal["write_enabled"]


async def test_import_processed_source_controls_unknown_size_quota(registry, imports):
    db, _, owner, _, project, *_ = registry
    service, geo, factory, settings = imports
    req = request().model_copy(
        update={"mode": "processed", "selected_ids": [geo.candidate["files"][0]["url"]]}
    )
    proposal = await service.prepare(owner, project, req)
    assert proposal["preview"]["expected_bytes"] is None
    assert proposal["preview"]["max_bytes"] == 10000
    for selected in (
        ["GSE1"],
        ["https://evil.test/steal"],
        ["https://ftp.ncbi.nlm.nih.gov/not-listed"],
    ):
        with pytest.raises(ValidationError):
            await service.prepare(
                owner,
                project,
                req.model_copy(update={"selected_ids": selected, "request_key": uuid4()}),
            )
    user = await db.get(
        __import__("cygnusx.infrastructure.database.models.user", fromlist=["UserModel"]).UserModel,
        owner,
    )
    user.storage_quota = user.used_storage
    with pytest.raises(ValidationError, match="配额"):
        await service.prepare(owner, project, req.model_copy(update={"request_key": uuid4()}))


async def test_import_forgery_rejected_and_no_auto_authorization(registry, imports, monkeypatch):
    db, _, owner, other, project, *_ = registry
    service, *_ = imports
    proposal = await service.prepare(owner, project, request())
    iid = UUID(proposal["proposal_id"])
    with pytest.raises(NotFoundError):
        await service.decide(other, project, iid, True)
    monkeypatch.setattr(
        module, "require_import_write", lambda: None
    )  # isolated future adapter only
    with pytest.raises(ConflictError, match="持久记录"):
        await service.execute(owner, project, iid)
    row = await db.get(DatasetIngestionModel, iid)
    row.normalized_request = {**row.normalized_request, "max_bytes": 9999}
    with pytest.raises(ConflictError):
        await service.decide(owner, project, iid, True, auth_session_or_jti_hash="a" * 64)
    with pytest.raises(SchemaError):
        ImportPrepare.model_validate({**request().model_dump(), "user_confirmed": True})


@pytest.mark.parametrize("task_status", ["success", "failed"])
async def test_isolated_import_task_link_file_integrity_partial_and_restore(
    registry, imports, monkeypatch, task_status
):
    db, registry_service, owner, _, project, *_ = registry
    service, geo, factory, _ = imports
    proposal = await service.prepare(owner, project, request())
    iid = UUID(proposal["proposal_id"])
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash="a" * 64)
    monkeypatch.setattr(module, "require_import_write", lambda: None)
    # Seed a historical raw import; new raw execution must stay blocked.
    from cygnusx.application.schemas.dataset import DatasetCreate

    dataset = await registry_service.create(owner, project, DatasetCreate(name="historical raw"))
    version = db.sync.scalar(
        sa.select(DatasetVersionModel).where(DatasetVersionModel.dataset_id == dataset.id)
    )
    version.source_snapshot = deepcopy(geo.candidate)
    task = TaskModel(
        user_id=owner,
        parameters={"project_id": str(project)},
        flow_id="download",
        name="historical",
        status=task_status,
    )
    db.add(task)
    await db.flush()
    row = await db.get(DatasetIngestionModel, iid)
    row.version_id, row.task_ids, row.state = version.id, [str(task.id)], "QUEUED"
    folder = factory.user_root(str(owner)) / "projects/owned/downloads/SRR1"
    folder.mkdir(parents=True)
    path = folder / "GSM1_R1.fastq"
    path.write_bytes(bytes([10]).join([b"@r", b"ACGT", b"+", b"IIII", b""]))
    db.add(
        FileRecordModel(
            user_id=owner,
            original_name=path.name,
            storage_path=path.relative_to(factory.data_root).as_posix(),
            directory="projects/owned/downloads",
            size=path.stat().st_size,
            task_id=task.id,
            source="download",
            status="active",
            owner_scope="personal",
            lifecycle_status="active",
        )
    )
    await db.flush()
    complete = await service.reconcile(owner, project, iid)
    assert complete["state"] == ("COMPLETED" if task_status == "success" else "PARTIAL")
    row = await db.get(DatasetIngestionModel, iid)
    version = await db.get(DatasetVersionModel, row.version_id)
    manifest = await DatasetHandoffService(db).manifest(
        owner, project, version.dataset_id, version.id, freeze=True
    )
    assert manifest["assets"][0]["checksum_status"] == "VERIFIED"
    assert manifest["assets"][0]["data_type"] == "RAW_FASTQ"
    assert not manifest["validation"]["dataset_ready"]  # source groups unknown
    assert "SAMPLE_GROUPS_NOT_CONFIRMED" in manifest["validation"]["blocking_reasons"]
    assert len(manifest["manifest_hash"]) == 64
    assert "storage_path" not in str(manifest)
    assert (await service.view(owner, project, iid))["dataset_version_id"] == str(version.id)


async def test_ambiguous_submit_not_replayed_and_source_change_invalidates(
    registry, imports, monkeypatch
):
    db, _, owner, _, project, *_ = registry
    service, geo, *_ = imports
    proposal = await service.prepare(owner, project, processed_http_fixture(imports, monkeypatch))
    iid = UUID(proposal["proposal_id"])
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash="a" * 64)
    monkeypatch.setattr(module, "require_import_write", lambda: None)
    await db.commit()
    geo.candidate["source_evidence"][0]["response_sha256"] = "b" * 64
    with pytest.raises(ConflictError, match="来源"):
        await service.execute(owner, project, iid)
    geo.candidate["source_evidence"][0]["response_sha256"] = "a" * 64
    calls = []

    async def timeout(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("queue outcome unknown")

    monkeypatch.setattr(module.DownloadService, "submit", timeout)
    with pytest.raises(ConflictError, match="对账"):
        await service.execute(owner, project, iid)
    with pytest.raises(ConflictError) as replay:
        await service.execute(owner, project, iid)
    assert replay.value.code == "RECONCILIATION_REQUIRED"
    assert calls == [1]


def processed_http_fixture(imports, monkeypatch):
    """Synthetic metadata-only HTTP fixture; no production URL policy change."""
    _, geo, _, settings = imports
    url = "http://fixture.invalid/counts.tsv"
    geo.candidate["files"][0]["url"] = url
    original = module.trusted_url

    def fixture_url(value, **kwargs):
        return value if value == url else original(value, **kwargs)

    monkeypatch.setattr(module, "trusted_url", fixture_url)
    settings.download_admission_profiles = {
        "offline-env": {
            "policy_revision": "offline",
            "caller_id": "offline-worker",
            "allowed_destinations": [{"host": "fixture.invalid", "port": 80}],
        }
    }
    return request().model_copy(update={"mode": "processed", "selected_ids": [url]})


@pytest.mark.parametrize("mode", ["raw", "https"])
async def test_unaccepted_import_modes_do_not_consume_approval(
    registry, imports, monkeypatch, mode
):
    db, _, owner, _, project, *_ = registry
    service, geo, *_ = imports
    req = request()
    if mode == "https":
        req = req.model_copy(
            update={"mode": "processed", "selected_ids": [geo.candidate["files"][0]["url"]]}
        )
    prepared = await service.prepare(owner, project, req)
    iid = UUID(prepared["proposal_id"])
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash="a" * 64)
    monkeypatch.setattr(module, "require_import_write", lambda: None)
    with pytest.raises(ConflictError) as caught:
        await service.execute(owner, project, iid)
    assert caught.value.code == "DOWNLOAD_ADMISSION_MODE_BLOCKED"
    row = await db.get(DatasetIngestionModel, iid)
    assert row.approval_snapshot["nonce_status"] == "APPROVED"
    assert not db.sync.scalars(sa.select(TaskModel)).all()
