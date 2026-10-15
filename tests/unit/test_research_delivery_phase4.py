"""Phase4 isolated persistence and hostile-manifest tests; never runtime admission."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError

from cygnusx.application.schemas.agent_tools import CAPABILITY_MODELS, capability_catalog
from cygnusx.application.schemas.dataset import DatasetCreate
from cygnusx.application.services import research_provenance_service as module
from cygnusx.application.services.dataset_import_service import digest
from cygnusx.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from cygnusx.infrastructure.database.models.dataset import (
    DatasetAnalysisLinkModel,
    DatasetVersionModel,
)
from cygnusx.infrastructure.database.models.report import (
    ReportFileModel,
    ReportGenerationJobModel,
    ReportModel,
    ReportSnapshotModel,
)
from cygnusx.infrastructure.database.models.result_observation import ResultObservationModel
from cygnusx.infrastructure.database.models.run import RunModel
from cygnusx.infrastructure.database.models.task import TaskModel
from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_report_snapshot import inline_file_capture as inline_file_capture

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def delivery(registry, tmp_path, monkeypatch):
    db, datasets, owner, other, project, *_ = registry
    for model in (
        TaskModel,
        RunModel,
        DatasetAnalysisLinkModel,
        ResultObservationModel,
        ReportSnapshotModel,
        ReportModel,
        ReportFileModel,
        ReportGenerationJobModel,
    ):
        model.__table__.create(db.sync.bind)
    root = tmp_path / "storage"
    factory = SimpleNamespace(data_root=root, user_root=lambda uid: root / "users" / str(uid))
    monkeypatch.setattr(module, "get_path_factory", lambda: factory)
    from cygnusx.core.config import Settings

    settings = Settings(research_delivery_read_enabled=True)
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    return db, datasets, owner, other, project, factory, settings


async def linked(delivery, monkeypatch):
    db, datasets, owner, _, project, factory, _ = delivery
    dataset = await datasets.create(
        owner, project, DatasetCreate(name="synthetic", assay_type="bulk_rnaseq")
    )
    version = db.sync.query(DatasetVersionModel).filter_by(dataset_id=dataset.id).one()
    version.handoff = {
        "assets": [],
        "source": [{"repository": "GEO", "accession": "GSE1"}],
        "samples": [],
    }
    version.handoff["manifest_hash"] = digest({**version.handoff, "manifest_hash": None})
    work = factory.user_root(str(owner)) / "projects" / "owned" / "runs" / "fixture" / "work"
    result = work / "results"
    result.mkdir(parents=True)
    task = TaskModel(
        id=uuid4(),
        user_id=owner,
        flow_id="counts_deg",
        status="success",
        work_dir=str(work),
        parameters={},
    )
    db.add(task)
    link = DatasetAnalysisLinkModel(
        id=uuid4(),
        task_id=task.id,
        version_id=version.id,
        flow_id=task.flow_id,
        handoff_hash=version.handoff["manifest_hash"],
        parameters_hash="b" * 64,
        normalized_request={
            "owner_id": str(owner),
            "project_id": str(project),
            "dataset_id": str(dataset.id),
            "dataset_version_id": str(version.id),
        },
        execution_binding={
            "flow_version": "1.0.0",
            "flow_config_sha256": "c" * 64,
            "parameters_sha256": "d" * 64,
        },
        state="QUEUED",
    )
    db.add(link)
    await db.flush()

    async def verified_inputs(*args, **kwargs):
        return version.handoff

    monkeypatch.setattr(module, "check_inputs", verified_inputs)
    artifact = result / "deg.tsv"
    artifact.write_text("gene\tlog2FoldChange\ngene1\t1.0\n")
    manifest = {
        "platform": {"task_id": str(task.id), "user_id": str(owner), "flow_id": task.flow_id},
        "cygnusx": {
            **link.execution_binding,
            "dataset_version_id": str(version.id),
            "handoff_hash": link.handoff_hash,
        },
        "files": [
            {
                "path": artifact.name,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "size_bytes": artifact.stat().st_size,
                "category": "deg",
            }
        ],
    }
    (result / "result_manifest.json").write_text(json.dumps(manifest))
    return task, link, artifact, manifest


async def test_missing_manifest_never_ready_and_run_not_invented(delivery, monkeypatch):
    task, _, artifact, _ = await linked(delivery, monkeypatch)
    (artifact.parent / "result_manifest.json").unlink()
    graph = await module.ResearchProvenanceService(delivery[0]).task(delivery[2], task.id)
    assert graph.run_id is None and graph.result_integrity == "MISSING"
    assert graph.delivery_state != "READY" and "RESULT_MANIFEST_MISSING" in graph.gaps


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("unchanged", "VERIFIED"),
        ("missing", "MISSING"),
        ("changed", "FAILED"),
        ("sha", "FAILED"),
        ("identity", "FAILED"),
        ("traversal", "FAILED"),
        ("malformed", "FAILED"),
    ],
)
async def test_actual_manifest_and_bytes(delivery, monkeypatch, mutation, expected):
    task, _, artifact, manifest = await linked(delivery, monkeypatch)
    if mutation == "missing":
        artifact.unlink()
    if mutation == "changed":
        artifact.write_text("tampered")
    if mutation == "sha":
        manifest["files"][0]["sha256"] = "0" * 64
    if mutation == "identity":
        manifest["platform"]["user_id"] = str(uuid4())
    if mutation == "traversal":
        manifest["files"][0]["path"] = "../../secret"
    if mutation == "malformed":
        manifest["platform"] = []
    (artifact.parent / "result_manifest.json").write_text(json.dumps(manifest))
    graph = await module.ResearchProvenanceService(delivery[0]).task(delivery[2], task.id)
    assert graph.result_integrity == expected
    assert graph.delivery_state != "READY"
    assert graph.flow["version"] == "1.0.0" and graph.runtime["image_digest"] is None
    assert str(artifact) not in graph.model_dump_json()


async def test_legacy_task_and_owner_scope(delivery):
    db, _, owner, other, *_ = delivery
    task = TaskModel(id=uuid4(), user_id=owner, flow_id="rna_seq", status="success")
    db.add(task)
    await db.flush()
    graph = await module.ResearchProvenanceService(db).task(owner, task.id)
    assert graph.dataset_version_id is None and graph.evidence_state == "UNKNOWN"
    assert "DATASET_LINEAGE_UNKNOWN" in graph.gaps
    with pytest.raises(NotFoundError):
        await module.ResearchProvenanceService(db).task(other, task.id)


async def test_write_gate_before_db_or_files():
    class NoDB:
        def __getattr__(self, name):
            raise AssertionError("DB touched before gate")

    with pytest.raises(AuthorizationError):
        await module.ResearchProvenanceService(NoDB()).reconcile(uuid4(), uuid4())


@pytest.mark.parametrize(
    "name",
    [
        "research.task_provenance",
        "research.report_provenance",
        "research.dataset_provenance",
        "research.project_delivery",
    ],
)
async def test_shared_read_tools_reject_identity_or_verification_injection(name):
    assert name not in {c.capability_id for c in capability_catalog()}
    capability = next(
        c for c in capability_catalog(include_research=True) if c.capability_id == name
    )
    assert capability.side_effect == "none" and capability.scope == "read:research"
    args = (
        {"task_id": str(uuid4())}
        if name.endswith("task_provenance")
        else {"report_id": str(uuid4())}
        if name.endswith("report_provenance")
        else {"dataset_id": str(uuid4()), "version_id": str(uuid4())}
        if name.endswith("dataset_provenance")
        else {}
    )
    CAPABILITY_MODELS[name].model_validate(args)
    for key in ("owner_id", "project_id", "integrity", "_confirmed"):
        with pytest.raises(SchemaError):
            CAPABILITY_MODELS[name].model_validate({**args, key: "VERIFIED"})


@pytest.mark.parametrize(
    "path", ["../a", "/etc/passwd", "a/./b", "https://evil/a", "a\\b", "a\x00b"]
)
async def test_path_rejection(path):
    with pytest.raises(ValidationError):
        module.relative_file(path)


async def test_observation_append_only(delivery):
    db, _, owner, _, project, *_ = delivery
    row = ResultObservationModel(
        user_id=owner,
        project_id=project,
        analysis_link_id=uuid4(),
        task_id=uuid4(),
        evidence_digest="a" * 64,
        payload={},
    )
    db.add(row)
    await db.flush()
    row.payload = {"changed": True}
    with pytest.raises(ValueError):
        await db.flush()


async def test_reconcile_registers_actual_files_once_and_never_submits_compute(
    delivery, monkeypatch
):
    from cygnusx.application.services import report_service
    from cygnusx.application.services.task_service import TaskService
    from cygnusx.infrastructure.database.models.file import DirectoryModel, FileRecordModel
    from cygnusx.infrastructure.storage.file_registry import FileRegistry

    db, _, owner, _, _, factory, _ = delivery
    DirectoryModel.__table__.create(db.sync.bind)
    factory.relative_to_root = lambda path: Path(path).relative_to(factory.data_root).as_posix()

    async def refresh(record):
        db.sync.refresh(record)

    monkeypatch.setattr(db, "refresh", refresh)

    class LocalStat:
        name = "local"

        async def stat(self, path):
            return {"size": (factory.data_root / path).stat().st_size}

    backend = LocalStat()
    monkeypatch.setattr(
        module,
        "FileRegistry",
        lambda session: FileRegistry(session, path_factory=factory, backend=backend),
    )
    monkeypatch.setattr(report_service, "get_path_factory", lambda: factory)
    monkeypatch.setattr(report_service, "get_storage_backend", lambda: backend)
    monkeypatch.setattr(module, "require_research_write", lambda: None)

    async def forbidden(*args, **kwargs):
        raise AssertionError("reconciliation replayed compute")

    monkeypatch.setattr(TaskService, "submit", forbidden)
    task, link, artifact, manifest = await linked(delivery, monkeypatch)
    first = await module.ResearchProvenanceService(db).reconcile(owner, task.id)
    second = await module.ResearchProvenanceService(db).reconcile(owner, task.id)
    assert first.result_observation_id == second.result_observation_id
    assert db.sync.query(ResultObservationModel).count() == 1
    record = db.sync.query(FileRecordModel).filter_by(task_id=task.id).one()
    assert record.checksum == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert first.artifacts[0].file_record_id == record.id
    # A later missing output appends evidence and leaves the successful compute untouched.
    artifact.unlink()
    third = await module.ResearchProvenanceService(db).reconcile(owner, task.id)
    assert third.result_integrity == "MISSING" and task.status == "success"
    assert third.result_observation_id != first.result_observation_id
    assert db.sync.query(ResultObservationModel).count() == 2


async def test_phase4_sqlite_upgrade_downgrade_preserves_legacy_rows():
    import importlib.util

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.dialects.postgresql import UUID as PGUUID

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    for name in (
        "users",
        "projects",
        "tasks",
        "dataset_analysis_links",
        "file_records",
        "reports",
        "report_files",
    ):
        sa.Table(name, metadata, sa.Column("id", PGUUID(as_uuid=True), primary_key=True))
    metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location(
        "phase4_migration", "alembic/versions/bioopsphase4_research_evidence.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(metadata.tables["reports"].insert().values(id=uuid4()))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "result_manifest_observations" in sa.inspect(connection).get_table_names()
            assert "result_observation_id" in {
                c["name"] for c in sa.inspect(connection).get_columns("reports")
            }
            migration.downgrade()
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(metadata.tables["reports"]))
            == 1
        )
        assert "result_manifest_observations" not in sa.inspect(connection).get_table_names()
    engine.dispose()


async def test_scientific_job_gate_precedes_db_and_renderer(monkeypatch):
    from cygnusx.application.services.scientific_report_job import run_scientific_report

    class NoDB:
        def __getattr__(self, name):
            raise AssertionError("write gate bypassed")

    job = ReportGenerationJobModel(
        id=uuid4(), task_id=uuid4(), user_id=uuid4(), template_version="scientific-counts-v1"
    )
    with pytest.raises(AuthorizationError):
        await run_scientific_report(NoDB(), job)


def test_published_provenance_schema_matches_python_dto():
    from cygnusx.application.schemas.research_delivery import ResearchProvenance

    assert (
        json.loads(Path("docs/contracts/cygnusx-provenance-v1.schema.json").read_text())
        == ResearchProvenance.model_json_schema()
    )


async def test_scientific_render_failures_retry_independently():
    from cygnusx.application.services.bioreport_adapter import BioReportRenderError
    from cygnusx.infrastructure.celery_app.tasks.reports import failure_details

    code, message, retryable = failure_details(BioReportRenderError("secret token must not escape"))
    assert code == "scientific_render_failed" and retryable
    assert "secret" not in message


async def test_counts_scientific_job_failure_then_retry_preserves_compute(
    delivery, monkeypatch, inline_file_capture
):
    from cygnusx.application.services import report_service
    from cygnusx.application.services import scientific_report_job as science
    from cygnusx.application.services.bioreport_adapter import BioReportRenderError
    from cygnusx.core import config
    from cygnusx.infrastructure.celery_app.tasks.reports import record_failure
    from cygnusx.infrastructure.database.models.file import DirectoryModel
    from cygnusx.infrastructure.storage.file_registry import FileRegistry

    db, _, owner, _, _, factory, settings = delivery
    db.sync_session = db.sync
    db._proxied = db.sync
    DirectoryModel.__table__.create(db.sync.bind)
    factory.relative_to_root = lambda path: Path(path).relative_to(factory.data_root).as_posix()
    attempts = []

    def run_dir(uid, project, label):
        target = factory.user_root(uid) / "projects" / project / "runs" / f"{label}-{len(attempts)}"
        (target / "output").mkdir(parents=True, exist_ok=True)
        return target

    factory.create_project_run_dir = run_dir

    class Backend:
        name = "local"

        async def stat(self, path):
            return {"size": (factory.data_root / path).stat().st_size}

    backend = Backend()
    for target in (module, science, report_service):
        monkeypatch.setattr(target, "get_path_factory", lambda: factory)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(science, "get_settings", lambda: settings)
    from datetime import UTC

    from sqlalchemy.orm.attributes import set_committed_value

    from cygnusx.application.services.report_snapshot_sources import DatabaseTaskEvidenceSource

    class SQLiteUTCSource(DatabaseTaskEvidenceSource):
        async def read(self, *args, **kwargs):
            records = await super().read(*args, **kwargs)
            # SQLite drops timezone information; PostgreSQL timestamps are timezone-aware.
            for record in (records.task, *records.files):
                for key in ("created_at", "updated_at", "started_at", "finished_at"):
                    value = getattr(record, key, None)
                    if value is not None and value.tzinfo is None:
                        set_committed_value(record, key, value.replace(tzinfo=UTC))
            return records

    monkeypatch.setattr(science, "DatabaseTaskEvidenceSource", SQLiteUTCSource)
    monkeypatch.setattr(science, "get_storage_backend", lambda: backend)
    monkeypatch.setattr(report_service, "get_storage_backend", lambda: backend)
    for target in (module, science):
        monkeypatch.setattr(target, "require_research_write", lambda: None)
        monkeypatch.setattr(
            target,
            "FileRegistry",
            lambda session: FileRegistry(session, path_factory=factory, backend=backend),
        )
    task, _, artifact, manifest = await linked(delivery, monkeypatch)
    qc = artifact.parent / "sample_qc.tsv"
    qc.write_text("sample\tcounts\ns1\t10\n")
    manifest["files"].append(
        {
            "path": qc.name,
            "sha256": hashlib.sha256(qc.read_bytes()).hexdigest(),
            "size_bytes": qc.stat().st_size,
        }
    )
    (artifact.parent / "result_manifest.json").write_text(json.dumps(manifest))
    await module.ResearchProvenanceService(db).reconcile(owner, task.id)
    job = ReportGenerationJobModel(
        id=uuid4(),
        user_id=owner,
        task_id=task.id,
        template_version="scientific-counts-v1",
        idempotency_key="scientific-fixture",
        status="queued",
    )
    db.add(job)
    await db.commit()

    def render(*args):
        attempts.append("render")
        if len(attempts) == 1:
            raise BioReportRenderError("synthetic renderer outage")
        return b"<!doctype html><html><body>Fixture rendering only</body></html>"

    monkeypatch.setattr(science, "render_counts", render)
    with pytest.raises(BioReportRenderError) as error:
        await science.run_scientific_report(db, job)
    await record_failure(db, job.id, error.value)
    frozen = job.snapshot_id
    assert job.status == "failed" and job.retryable and task.status == "success"
    job.status = "queued"
    await db.commit()
    await science.run_scientific_report(db, job)
    assert job.status == "ready" and job.snapshot_id == frozen and task.status == "success"
    report = await db.get(ReportModel, job.report_id)
    assert report.report_kind == "scientific" and report.result_observation_id is not None
    assert db.sync.query(ReportModel).count() == 1 and len(attempts) == 2


async def test_project_revocation_blocks_existing_report_and_shared_project_scope(
    delivery, monkeypatch
):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.infrastructure.database.models.project import ProjectModel

    db, _, owner, other, project, *_ = delivery
    task, _, _, _ = await linked(delivery, monkeypatch)
    gateway = AgentToolGateway(db)
    context = SimpleNamespace(user_id=str(owner), extra={"project_id": str(uuid4())})
    with pytest.raises(AuthorizationError):
        await gateway._research_tool(context, "research.task_provenance", {"task_id": str(task.id)})
    report = ReportModel(
        id=uuid4(),
        user_id=owner,
        task_id=task.id,
        flow_id=task.flow_id,
        created_at=datetime.now(UTC),
        report_kind="scientific",
    )
    db.add(report)
    await db.flush()
    row = await db.get(ProjectModel, project)
    row.user_id = other
    await db.flush()
    with pytest.raises(NotFoundError):
        await module.ResearchProvenanceService(db).report(owner, report.id)


async def test_final_dataset_binding_rejects_changed_parameters_and_reuses_queued_link(
    delivery, monkeypatch
):
    from cygnusx.application.schemas.task import TaskSubmitRequest
    from cygnusx.application.services import agent_tool_gateway
    from cygnusx.application.services import research_execution_binding as binding
    from cygnusx.core.exceptions import ConflictError

    db, _, owner, *_ = delivery
    task, link, _, _ = await linked(delivery, monkeypatch)
    from cygnusx.application.services import flow_service

    monkeypatch.setattr(
        flow_service,
        "get_settings",
        lambda: delivery[-1].model_copy(update={"counts_deg_flow_enabled": True}),
    )
    request = TaskSubmitRequest(
        flow_id="counts_deg", name="fixture", idempotency_key=f"dataset:{link.id}"
    )
    link.normalized_request = {
        **link.normalized_request,
        "request": request.model_dump(mode="json"),
    }
    link.execution_binding = binding.execution_binding(
        task.flow_id, request.model_dump(mode="json"), link.handoff_hash
    )
    await db.flush()
    monkeypatch.setattr(agent_tool_gateway, "require_agent_write_gate", lambda operation: None)

    async def inputs(*args, **kwargs):
        return {}

    monkeypatch.setattr(binding, "check_inputs", inputs)
    assert await binding.validate_dataset_submission(db, owner, request) is link
    assert await binding.validate_dataset_submission(db, owner, request) is link
    with pytest.raises(ConflictError):
        await binding.validate_dataset_submission(
            db, owner, request.model_copy(update={"name": "changed"})
        )
    assert db.sync.query(TaskModel).count() == 1 and task.status == "success"


async def test_execution_input_check_observes_frozen_bytes(delivery, monkeypatch):
    from cygnusx.application.services import research_execution_binding as binding
    from cygnusx.core.exceptions import ConflictError
    from cygnusx.infrastructure.database.models.file import FileRecordModel

    db, _, owner, _, _, factory, _ = delivery
    _, link, _, _ = await linked(delivery, monkeypatch)
    record = (
        db.sync.query(FileRecordModel)
        .filter_by(user_id=owner, directory="projects/owned/raw")
        .one()
    )
    path = factory.data_root / record.storage_path
    path.write_bytes(b"original-input")
    record.size = path.stat().st_size
    version = await db.get(DatasetVersionModel, link.version_id)
    handoff = {
        "assets": [
            {
                "file_record_id": str(record.id),
                "size": record.size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ],
        "validation": {},
    }
    handoff["manifest_hash"] = digest({**handoff, "manifest_hash": None})
    version.handoff = handoff
    link.handoff_hash = handoff["manifest_hash"]
    await db.flush()
    monkeypatch.setattr(binding, "get_path_factory", lambda: factory)
    await binding.check_inputs(db, owner, link, require_worker=False)
    path.write_bytes(b"changed-input")
    with pytest.raises(ConflictError, match="Input file changed"):
        await binding.check_inputs(db, owner, link, require_worker=False)


async def test_dataset_cannot_fall_back_to_legacy_unverified_directory_scans():
    from cygnusx.infrastructure.celery_app.tasks.analysis import (
        _archive_pipeline_run,
        _register_pipeline_outputs,
    )

    class NoIO:
        idempotency_key = "dataset:" + str(uuid4())

        def __getattr__(self, name):
            raise AssertionError("legacy scan touched data or DB")

    assert await _register_pipeline_outputs(NoIO(), NoIO()) == 0
    await _archive_pipeline_run(NoIO(), NoIO(), "completed", "fixture")


async def test_cross_owner_output_record_rejects_registration(delivery, monkeypatch):
    from cygnusx.infrastructure.database.models.file import FileRecordModel

    db, _, owner, other, _, factory, _ = delivery
    task, _, artifact, _ = await linked(delivery, monkeypatch)
    db.add(
        FileRecordModel(
            user_id=other,
            storage_path=artifact.relative_to(factory.data_root).as_posix(),
            original_name="foreign.tsv",
            size=artifact.stat().st_size,
            task_id=task.id,
            status="active",
            lifecycle_status="active",
            owner_scope="personal",
            storage_backend="local",
        )
    )
    await db.flush()
    with pytest.raises(AuthorizationError):
        await module.ResearchProvenanceService(db).task(owner, task.id)
    assert db.sync.query(ResultObservationModel).count() == 0
