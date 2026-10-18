"""Real Task repository/SQLite/files; queue/executor replaced, no runtime acceptance."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError

from cygnusx.application.schemas.execution_evidence import ExecutionDefinitionV2, ExecutionEvidence
from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.services import execution_evidence_service as evidence
from cygnusx.application.services.flow_service import FlowService
from cygnusx.core.exceptions import ConflictError, ValidationError
from cygnusx.domain.flow.submission_validator import FlowSubmissionValidator, ValidationResult
from cygnusx.domain.task.entities import Task
from cygnusx.domain.task.value_objects import TaskStatus
from cygnusx.infrastructure.config.storage_config import StorageConfig
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl
from cygnusx.infrastructure.storage.path_factory import StoragePathFactory
from tests.unit.test_dataset_phase3 import registry as registry

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def execution_env(registry, tmp_path, monkeypatch):
    db, _, owner, *_ = registry
    TaskModel.__table__.create(db.sync.bind)

    async def refresh(instance, **kwargs):
        db.sync.refresh(instance, **kwargs)

    async def scalar(statement, **kwargs):
        return db.sync.scalar(statement, **kwargs)

    monkeypatch.setattr(db, "refresh", refresh)
    monkeypatch.setattr(db, "scalar", scalar)
    from cygnusx.infrastructure import storage

    factory = StoragePathFactory(StorageConfig(data_root=str(tmp_path), users_subdir="users"))
    monkeypatch.setattr(storage, "get_path_factory", lambda: factory)
    work = factory.user_root(str(owner)) / "projects/owned/run/work"
    work.mkdir(parents=True)
    config = work / "analysis.yaml"
    config.write_text("alpha: 0.05\n")
    request = TaskSubmitRequest(flow_id="rna_seq", name="isolated", parameters={"alpha": 0.05})
    flow = FlowService().get_flow_config("rna_seq").model_dump(mode="json")
    task = Task(id=uuid4(), user_id=owner, flow_id="rna_seq", work_dir=str(work))
    task.parameters = {
        **request.parameters,
        evidence.EVIDENCE_KEY: evidence.freeze_execution_evidence(
            task.id,
            owner,
            request,
            flow,
            generated_files=evidence.capture_generated_files(owner, str(work), {"config": config}),
        ),
    }
    return SimpleNamespace(db=db, owner=owner, task=task, config=config, flow=flow, request=request)


async def test_definition_is_task_independent_binding_is_not(execution_env):
    env = execution_env
    first = evidence.read_execution_evidence(env.task)
    other = ExecutionEvidence.model_validate(
        evidence.freeze_execution_evidence(
            uuid4(),
            env.owner,
            env.request,
            env.flow,
            generated_files=first.generated_files,
        )
    )
    assert first.definition_digest == other.definition_digest
    assert first.execution_binding_digest != other.execution_binding_digest
    assert first.definition.workflow_release_digest is None
    assert first.definition.container_image_digest is None
    with pytest.raises(SchemaError):
        ExecutionDefinitionV2(**first.definition.model_dump(), task_id=uuid4())


@pytest.mark.parametrize("mutation", ["parameters", "flow", "file", "owner", "digest"])
async def test_drift_rejected_and_failure_retained(execution_env, monkeypatch, mutation):
    env = execution_env
    repo = TaskRepositoryImpl(env.db)
    await repo.save(env.task)
    await env.db.commit()
    if mutation == "parameters":
        env.task.parameters["alpha"] = 0.1
    elif mutation == "flow":
        monkeypatch.setattr(
            evidence.FlowService,
            "get_flow_config",
            lambda *a: SimpleNamespace(model_dump=lambda **k: {"different": True}),
        )
    elif mutation == "file":
        env.config.write_text("alpha: 0.99\n")
    elif mutation == "owner":
        env.task.user_id = uuid4()
    else:
        env.task.parameters[evidence.EVIDENCE_KEY]["definition_digest"] = "0" * 64
    with pytest.raises(ConflictError):
        await evidence.observe_execution(env.db, env.task)
    saved = await repo.get_by_id(env.task.id)
    if mutation in {"parameters", "flow", "file"}:
        event = evidence.read_execution_evidence(saved).observations[-1]
        assert event.phase == "FAILED" and event.input_integrity == "FAILED"
    else:
        assert evidence.read_execution_evidence(saved).observations == ()


async def test_before_after_failure_and_restart_retain_evidence(execution_env):
    env = execution_env
    repo = TaskRepositoryImpl(env.db)
    await repo.save(env.task)
    await evidence.observe_execution(env.db, env.task)
    restarted = await repo.get_by_id(env.task.id)
    await evidence.observe_execution(env.db, restarted, after=True, failed=True)
    saved = await repo.get_by_id(env.task.id)
    result = evidence.read_execution_evidence(saved)
    assert [e.phase for e in result.observations] == ["PREFLIGHT", "FAILED"]
    assert all(e.image_status == "NOT_OBSERVED" for e in result.observations)
    assert all(e.input_integrity == "NOT_OBSERVED" for e in result.observations)
    assert result.definition_digest == evidence.read_execution_evidence(env.task).definition_digest


async def test_legacy_not_backfilled(execution_env):
    env = execution_env
    env.task.parameters = {"alpha": 0.05}
    await evidence.observe_execution(env.db, env.task)
    assert env.task.parameters == {"alpha": 0.05}
    assert evidence.evidence_projection(env.task) is None


async def test_definition_projection_never_copies_credentials(execution_env):
    env = execution_env
    req = env.request.model_copy(
        update={"parameters": {"api_key": "PRIVATE", "raw_data_path": "/host"}}
    )
    payload = evidence.freeze_execution_evidence(uuid4(), env.owner, req, env.flow)
    assert "PRIVATE" not in json.dumps(payload) and "/host" not in json.dumps(payload)
    assert payload["definition"]["normalized_parameters"] == []


async def test_generated_link_escape_rejected(execution_env, tmp_path):
    env = execution_env
    env.config.unlink()
    target = tmp_path / "foreign"
    target.write_text("foreign")
    env.config.symlink_to(target)
    with pytest.raises(ValidationError):
        evidence.capture_generated_files(env.owner, env.task.work_dir, {"config": env.config})


@pytest.mark.parametrize("cookies_enabled", [False, True])
async def test_submit_freezes_before_queue_and_reuses_idempotency(
    execution_env, monkeypatch, cookies_enabled
):
    env = execution_env
    from cygnusx.application.services import file_service, task_service
    from cygnusx.core.config import get_settings

    req = TaskSubmitRequest(
        flow_id="rna_seq", name="isolated", parameters={"cores": 1}, idempotency_key="ri13-isolated"
    )
    monkeypatch.setattr(
        FlowSubmissionValidator,
        "validate",
        AsyncMock(
            return_value=ValidationResult(
                valid=True,
                errors=[],
                warnings=[],
                normalized_request=req,
            )
        ),
    )
    monkeypatch.setattr(file_service, "ensure_directory_chain", AsyncMock())
    monkeypatch.setattr(
        task_service,
        "get_settings",
        lambda: get_settings().model_copy(update={"enable_cookie_system": cookies_enabled}),
    )
    from decimal import Decimal

    from cygnusx.application.services.task_cookie_consumer import TaskCookieConsumer

    charge = AsyncMock(return_value=Decimal("2"))
    monkeypatch.setattr(TaskCookieConsumer, "on_submit", charge)
    service = task_service.TaskService(env.db)
    monkeypatch.setattr(service, "_make_work_dir", lambda *a: env.task.work_dir)
    monkeypatch.setattr(service, "_write_monitor_config", lambda **k: None)
    queued = []

    def enqueue(*args, **kwargs):
        persisted = env.db.sync.get(TaskModel, UUID(args[2]))
        assert persisted is not None
        assert persisted.status == "queued"
        assert persisted.parameters.get("_cookie_pre_deducted", 0) == (2 if cookies_enabled else 0)
        frozen = evidence.read_execution_evidence(persisted)
        assert frozen is not None and len(frozen.generated_files) >= 1
        queued.append(args[2])

    monkeypatch.setattr(task_service, "enqueue_task", enqueue)
    result = await service.submit(str(env.owner), req)
    repeated = await service.submit(str(env.owner), req)
    assert result.id == repeated.id and queued == [str(result.id)]
    assert charge.await_count == (1 if cookies_enabled else 0)


@pytest.mark.parametrize("tamper", [False, True])
async def test_actual_worker_boundary_retains_failure_and_never_runs_drifted_input(
    execution_env, monkeypatch, tamper
):
    from contextlib import asynccontextmanager

    from cygnusx.infrastructure.celery_app.tasks import analysis
    from cygnusx.infrastructure.database import session as session_module
    from cygnusx.infrastructure.database.models.run import RunModel

    env = execution_env
    RunModel.__table__.create(env.db.sync.bind)
    env.task.status = TaskStatus.QUEUED
    await TaskRepositoryImpl(env.db).save(env.task)
    await env.db.commit()

    @asynccontextmanager
    async def session_factory():
        yield env.db

    monkeypatch.setattr(session_module, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(analysis, "publish_task_log", AsyncMock())
    execute = AsyncMock(
        return_value={"status": "failed", "returncode": 1, "stdout": "", "stderr": "controlled"}
    )
    monkeypatch.setattr(analysis.LocalSnakemakeExecutor, "_execute", execute)
    if tamper:
        env.config.write_text("changed after enqueue")
    flow = FlowService().get_flow_config("rna_seq").execution
    # Fixture uses the real configured filename at the Worker boundary.
    if env.config.name != flow.config_file_name:
        actual = env.config.with_name(flow.config_file_name)
        env.config.rename(actual)
        if not tamper:
            frozen = evidence.freeze_execution_evidence(
                env.task.id,
                env.owner,
                env.request,
                env.flow,
                generated_files=evidence.capture_generated_files(
                    env.owner, env.task.work_dir, {"config": actual}
                ),
            )
            env.task.parameters[evidence.EVIDENCE_KEY] = frozen
            await TaskRepositoryImpl(env.db).save(env.task)
            await env.db.commit()
    result = await analysis._execute_snakemake(
        snakefile=flow.snakefile,
        task_id=str(env.task.id),
        config_file=str(Path(env.task.work_dir) / flow.config_file_name),
        config_file_param=flow.config_file_param or "analysisyaml",
        work_dir=env.task.work_dir,
        cores=flow.default_resources.cores,
    )
    saved = await TaskRepositoryImpl(env.db).get_by_id(env.task.id)
    assert result["status"] == "failed" and saved.status.value == "failed"
    events = evidence.read_execution_evidence(saved).observations
    if tamper:
        execute.assert_not_awaited()
        assert events[-1].input_integrity == "FAILED"
    else:
        execute.assert_awaited_once()
        assert [event.phase for event in events] == ["PREFLIGHT", "FAILED"]


@pytest.mark.parametrize(
    "field", ["snakefile", "work_dir", "config_file", "config_file_param", "cores"]
)
async def test_queue_arguments_cannot_override_task_binding(execution_env, field):
    env = execution_env
    flow = FlowService().get_flow_config("rna_seq").execution
    kwargs = dict(
        snakefile=flow.snakefile,
        work_dir=env.task.work_dir,
        config_file=str(Path(env.task.work_dir) / flow.config_file_name),
        config_file_param=flow.config_file_param or "analysisyaml",
        cores=flow.default_resources.cores,
    )
    evidence.validate_executor_binding(env.task, **kwargs)
    kwargs[field] = 99 if field == "cores" else "changed"
    with pytest.raises(ConflictError):
        evidence.validate_executor_binding(env.task, **kwargs)


async def test_real_dataset_input_before_after_integrity(execution_env, registry, monkeypatch):
    import hashlib

    from cygnusx.application.schemas.dataset import DatasetCreate
    from cygnusx.application.services import research_execution_binding as binding
    from cygnusx.application.services.dataset_import_service import digest
    from cygnusx.infrastructure.database.models.dataset import (
        DatasetAnalysisLinkModel,
        DatasetVersionModel,
    )

    env = execution_env
    db, datasets, owner, _, project, *rest = registry
    DatasetAnalysisLinkModel.__table__.create(db.sync.bind)
    dataset = await datasets.create(owner, project, DatasetCreate(name="ri13-input"))
    version = db.sync.query(DatasetVersionModel).filter_by(dataset_id=dataset.id).one()
    record = rest[-2][0]
    from cygnusx.infrastructure.storage import get_path_factory

    factory = get_path_factory()
    path = factory.data_root / record.storage_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"real bounded input")
    handoff = {
        "assets": [
            {
                "file_record_id": str(record.id),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ],
        "validation": {"worker_paths_verified": True},
    }
    handoff["manifest_hash"] = digest({**handoff, "manifest_hash": None})
    version.handoff = handoff
    link = DatasetAnalysisLinkModel(
        id=uuid4(),
        task_id=env.task.id,
        version_id=version.id,
        flow_id="rna_seq",
        handoff_hash=handoff["manifest_hash"],
        parameters_hash="0" * 64,
        state="QUEUED",
        normalized_request={
            "owner_id": str(owner),
            "project_id": str(project),
            "dataset_id": str(dataset.id),
            "dataset_version_id": str(version.id),
        },
    )
    db.add(link)
    await db.flush()
    monkeypatch.setattr(binding, "get_path_factory", lambda: factory)
    env.task.parameters[evidence.EVIDENCE_KEY] = evidence.freeze_execution_evidence(
        env.task.id,
        owner,
        env.request,
        env.flow,
        link=link,
        handoff=handoff,
    )
    await TaskRepositoryImpl(db).save(env.task)
    await evidence.observe_execution(db, env.task)
    assert evidence.read_execution_evidence(env.task).observations[-1].input_integrity == "VERIFIED"
    path.write_bytes(b"modified during execution")
    with pytest.raises(ConflictError):
        await evidence.observe_execution(db, env.task, after=True)
    saved = await TaskRepositoryImpl(db).get_by_id(env.task.id)
    assert evidence.read_execution_evidence(saved).observations[-1].input_integrity == "FAILED"


async def test_v1_task_digest_stays_unchanged_while_v2_separates_binding():
    from cygnusx.application.schemas.execution_definition import ExecutionDefinition

    first = ExecutionDefinition(workflow_id="rna_seq", task_id=uuid4())
    second = first.model_copy(update={"task_id": uuid4()})
    assert first.content_digest() != second.content_digest()


@pytest.mark.parametrize(
    "state", [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.RUNNING]
)
async def test_worker_redelivery_never_reopens_execution(execution_env, monkeypatch, state):
    from contextlib import asynccontextmanager

    from cygnusx.infrastructure.celery_app.tasks import analysis
    from cygnusx.infrastructure.database import session as session_module

    env = execution_env
    env.task.status = state
    await TaskRepositoryImpl(env.db).save(env.task)
    await env.db.commit()

    @asynccontextmanager
    async def session_factory():
        yield env.db

    monkeypatch.setattr(session_module, "get_session_factory", lambda: session_factory)
    execute = AsyncMock()
    monkeypatch.setattr(analysis.LocalSnakemakeExecutor, "_execute", execute)
    result = await analysis._execute_snakemake("unused", str(env.task.id), "", "", "", 1)
    assert result["execution"] == "not_started"
    execute.assert_not_awaited()
    assert evidence.read_execution_evidence(env.task).observations == ()
