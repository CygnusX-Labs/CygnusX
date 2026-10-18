"""Real Worker registration + SQLite/FileRegistry + Dataset reconciliation, no network."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

from cygnusx.application.schemas.dataset import DatasetCreate
from cygnusx.application.services import dataset_import_service as imports_module
from cygnusx.infrastructure.celery_app.tasks import download as worker
from cygnusx.infrastructure.config.storage_config import StorageConfig
from cygnusx.infrastructure.database.models.dataset import DatasetAssetModel, DatasetIngestionModel
from cygnusx.infrastructure.database.models.file import DirectoryModel, FileRecordModel
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.infrastructure.storage import file_registry
from cygnusx.infrastructure.storage.backend import LocalStorageBackend
from cygnusx.infrastructure.storage.path_factory import StoragePathFactory
from tests.unit.test_dataset_import_handoff import imports as imports
from tests.unit.test_dataset_import_handoff import request
from tests.unit.test_dataset_phase3 import registry as registry

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
async def sandbox_thread_wakeup():
    # Sandbox may suppress the event-loop self-pipe wakeup from to_thread.
    # A timer keeps real filesystem threads observable; no filesystem/SQL double.
    async def tick():
        while True:  # noqa: ASYNC110 - periodic wakeup is the purpose of this sandbox fixture.
            await asyncio.sleep(0.01)

    ticker = asyncio.create_task(tick())
    yield
    await asyncio.get_running_loop().shutdown_default_executor()
    ticker.cancel()
    with suppress(asyncio.CancelledError):
        await ticker


@pytest.fixture
def download_env(registry, imports, monkeypatch):
    db, datasets, owner, other, project, *_ = registry
    service, _, original_factory, _ = imports
    DirectoryModel.__table__.create(db.sync.bind)
    factory = StoragePathFactory(
        StorageConfig(data_root=str(original_factory.data_root), users_subdir="users")
    )
    backend = LocalStorageBackend(factory)
    from cygnusx.infrastructure import storage

    monkeypatch.setattr(storage, "get_path_factory", lambda: factory)
    monkeypatch.setattr(storage, "get_storage_backend", lambda: backend)
    monkeypatch.setattr(file_registry, "get_path_factory", lambda: factory)
    monkeypatch.setattr(file_registry, "get_storage_backend", lambda: backend)

    async def scalar(statement, **kwargs):
        return db.sync.scalar(statement, **kwargs)

    async def refresh(instance, **kwargs):
        db.sync.refresh(instance, **kwargs)

    @asynccontextmanager
    async def begin_nested():
        with db.sync.begin_nested():
            yield

    monkeypatch.setattr(db, "begin_nested", begin_nested)
    monkeypatch.setattr(db, "scalar", scalar)
    monkeypatch.setattr(db, "refresh", refresh)
    return SimpleNamespace(
        db=db,
        datasets=datasets,
        owner=owner,
        other=other,
        project=project,
        service=service,
        factory=factory,
    )


@pytest.mark.parametrize("task_status", ["success", "failed"])
async def test_f01_f10_real_worker_register_to_dataset_reconcile(
    download_env, monkeypatch, task_status
):
    env = download_env
    proposal = await env.service.prepare(env.owner, env.project, request())
    row = await env.db.get(DatasetIngestionModel, UUID(proposal["proposal_id"]))
    dataset = await env.datasets.create(
        env.owner, env.project, DatasetCreate(name="worker-contract")
    )
    detail = await env.datasets.detail(env.owner, env.project, dataset.id)
    row.version_id = UUID(detail["versions"][0]["id"])
    task = TaskModel(user_id=env.owner, flow_id="ebi_download", name="isolated", status=task_status)
    env.db.add(task)
    await env.db.flush()
    row.task_ids, row.state = [str(task.id)], "QUEUED"
    work = env.factory.user_root(str(env.owner)) / "projects/owned/downloads/SRR1"
    work.mkdir(parents=True)
    task.work_dir = str(work)
    task.parameters = {"_download_output_baseline": []}
    content = b"@r\nACGT\n+\nIIII\n"
    (work / "GSM1_R1.fastq").write_bytes(content)
    await env.db.flush()
    await worker._register_downloaded_files(
        session=env.db,
        user_id=env.owner,
        task_id=task.id,
        work_dir=str(work),
        directory="projects/owned/downloads",
        storage_root=str(env.factory.data_root),
        complete=task_status == "success",
    )
    record = env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.storage_path.like("%GSM1_R1.fastq"))
    ).one()
    assert record.task_id == task.id
    assert record.source == "download"
    assert record.checksum == hashlib.sha256(content).hexdigest()
    assert record.size == len(content) and record.user_id == env.owner
    monkeypatch.setattr(imports_module, "require_import_write", lambda: None)
    result = await env.service.reconcile(env.owner, env.project, row.id)
    assert result["state"] == ("COMPLETED" if task_status == "success" else "PARTIAL")
    asset = env.db.sync.scalars(
        select(DatasetAssetModel).where(DatasetAssetModel.version_id == row.version_id)
    ).one()
    assert asset.file_record_id == record.id and asset.download_task_id == task.id
    assert asset.sha256 == record.checksum
    user = await env.db.get(UserModel, env.owner)
    assert user.used_storage == len(content)


async def make_task(env, owner=None):
    owner = owner or env.owner
    task = TaskModel(user_id=owner, flow_id="ebi_download", name="isolated", status="running")
    env.db.add(task)
    await env.db.flush()
    work = (
        env.factory.user_root(str(owner)) / "projects/owned/downloads" / f"task-{str(task.id)[:8]}"
    )
    work.mkdir(parents=True)
    task.work_dir = str(work)
    await worker._prepare_download_registration(env.db, task.id, owner, str(work))
    return task, work


async def register_outputs(env, task, *, complete=True):
    return await worker._register_downloaded_files(
        session=env.db,
        user_id=task.user_id,
        task_id=task.id,
        work_dir=task.work_dir,
        directory="projects/owned/downloads",
        storage_root=str(env.factory.data_root),
        complete=complete,
    )


async def test_f02_f03_f05_multiple_outputs_owners_and_idempotent_quota(download_env):
    env = download_env
    task, work = await make_task(env)
    other, elsewhere = await make_task(env, env.other)
    for p in (
        work / "run1_R1.fastq",
        work / "run1_R2.fastq",
        work / "run2_R1.fastq",
        elsewhere / "run1_R1.fastq",
    ):
        p.write_bytes(b"@r\nACGT\n+\nIIII\n")
    first = await register_outputs(env, task)
    await register_outputs(env, other)
    again = await register_outputs(env, task)
    assert first["file_ids"] == again["file_ids"] and again["new_bytes"] == 0
    own = env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).all()
    foreign = env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == other.id)
    ).all()
    assert len(own) == 3 and len(foreign) == 1
    assert all(f.user_id == env.owner for f in own)
    assert all(f.user_id == env.other for f in foreign)
    assert (await env.db.get(UserModel, env.owner)).used_storage == 3 * 15
    assert (await env.db.get(UserModel, env.other)).used_storage == 15


async def test_f04_control_files_and_incomplete_payload_not_assets(download_env):
    env = download_env
    task, work = await make_task(env)
    for name in [
        "progress.key",
        "run.log",
        ".checkpoint/state",
        "SRR_metadata/ena_metadata.tsv",
        "run.fastq.aria2",
        "run.fastq",
        "reads.part",
        "checkpoint/part",
    ]:
        path = work / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"control")
    (work / "valid.fastq").write_bytes(b"@r\nACGT\n+\nIIII\n")
    result = await register_outputs(env, task, complete=False)
    assert result["state"] == "PARTIAL" and result["file_count"] == 1
    records = env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).all()
    assert [f.original_name for f in records] == ["valid.fastq"]
    assert (work / "progress.key").exists()


@pytest.mark.parametrize("mode", ["unlinked", "other_task", "wrong_owner", "hash_changed"])
async def test_f06_f07_existing_records_never_claimed_or_silently_rehashed(download_env, mode):
    from cygnusx.core.exceptions import ValidationError

    env = download_env
    task, work = await make_task(env)
    path = work / "reads.fastq"
    path.write_bytes(b"@r\nACGT\n+\nIIII\n")
    await register_outputs(env, task)
    record = env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).one()
    if mode == "unlinked":
        record.task_id, record.checksum = None, ""
    elif mode == "other_task":
        from uuid import uuid4

        record.task_id = uuid4()
    elif mode == "wrong_owner":
        record.user_id = env.other
    else:
        path.write_bytes(b"different contents")
    await env.db.flush()
    before = (record.user_id, record.task_id, record.checksum)
    with pytest.raises(ValidationError, match="对账"):
        await register_outputs(env, task)
    assert (record.user_id, record.task_id, record.checksum) == before
    assert (await env.db.get(UserModel, env.owner)).used_storage == 15


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory_link", "fifo", "escape"])
async def test_f08_links_special_and_owner_escape_rejected(download_env, tmp_path, kind):
    import os

    from cygnusx.core.exceptions import ValidationError

    env = download_env
    task, work = await make_task(env)
    outside = tmp_path / "outside.fastq"
    outside.write_bytes(b"private")
    if kind == "symlink":
        (work / "link.fastq").symlink_to(outside)
    elif kind == "hardlink":
        os.link(outside, work / "link.fastq")
    elif kind == "directory_link":
        (work / "nested").symlink_to(tmp_path, target_is_directory=True)
    elif kind == "fifo":
        os.mkfifo(work / "pipe")
    else:
        task.work_dir = str(tmp_path)
        await env.db.flush()
    with pytest.raises(ValidationError):
        await register_outputs(env, task)
    assert not env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).all()


async def test_f09_registry_failure_rolls_back_files_directories_and_quota(
    download_env, monkeypatch
):
    env = download_env
    task, work = await make_task(env)
    for name in ["a.fastq", "b.fastq"]:
        (work / name).write_bytes(b"@r\nACGT\n+\nIIII\n")
    real_register = file_registry.FileRegistry.register
    calls = []

    async def fail_second(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("injected database failure after first real register")
        return await real_register(self, *args, **kwargs)

    monkeypatch.setattr(file_registry.FileRegistry, "register", fail_second)
    assert not await worker._finalize_download_files(
        env.db,
        task.id,
        env.owner,
        str(work),
        "",
        str(env.factory.data_root),
        True,
    )
    assert not env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).all()
    assert (await env.db.get(UserModel, env.owner)).used_storage == 0
    assert task.parameters["_download_registration"]["state"] == "RECONCILIATION_REQUIRED"
    assert len(list(work.iterdir())) == 2  # Never compensate by deleting user files.


@pytest.mark.parametrize("missing", [False, True])
async def test_f11_success_without_outputs_requires_reconciliation(download_env, missing):
    env = download_env
    task, work = await make_task(env)
    if missing:
        work.rmdir()
    ok = await worker._finalize_download_files(
        env.db,
        task.id,
        env.owner,
        str(work),
        "",
        str(env.factory.data_root),
        True,
    )
    assert not ok
    assert task.parameters["_download_registration"]["state"] == "RECONCILIATION_REQUIRED"
    assert task.parameters["_download_registration"]["scientific_ready"] is False


async def test_legacy_disk_file_and_shared_task_directory_require_review(download_env):
    from uuid import uuid4

    from cygnusx.core.exceptions import ValidationError

    env = download_env
    task, work = await make_task(env)
    (work / "old.fastq").write_bytes(b"old")
    task.parameters = {}  # A first pre-transfer inventory sees old content.
    with pytest.raises(ValidationError, match="未归属"):
        await worker._prepare_download_registration(env.db, task.id, env.owner, str(work))
    task.parameters = {"_download_output_baseline": ["old.fastq"]}
    with pytest.raises(ValidationError, match="自动认领"):
        await register_outputs(env, task)
    sibling = TaskModel(id=uuid4(), user_id=env.owner, flow_id="ebi_download", work_dir=str(work))
    env.db.add(sibling)
    await env.db.flush()
    with pytest.raises(ValidationError, match="其他任务"):
        await worker._prepare_download_registration(env.db, task.id, env.owner, str(work))


async def test_f12_http_worker_refuses_untrusted_binary_execution(download_env, monkeypatch):
    from cygnusx.domain.task.services import TaskDomainService
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl

    env = download_env
    task, work = await make_task(env)
    config = worker.get_download_config().model_copy(deep=True)
    config.binaries.aria2c = "/bin/true"
    monkeypatch.setattr(worker, "get_download_config", lambda: config)
    monkeypatch.setattr(
        worker, "get_settings", lambda: SimpleNamespace(storage_path=str(env.factory.data_root))
    )

    from cygnusx.infrastructure.download import policy
    monkeypatch.setattr(policy, "require_download_runtime", lambda source: None)

    class TransferDouble:
        async def execute(self, context):
            raise AssertionError("HTTP transfer must not start without a trusted supervisor")

    monkeypatch.setattr(worker, "get_executor", lambda _: TransferDouble())
    repo = TaskRepositoryImpl(env.db)
    domain_task = await repo.get_by_id(task.id)

    async def log(*args, **kwargs):
        pass

    result = await worker._execute_direct_link_download(
        task_id=str(task.id),
        task_uuid=task.id,
        task=domain_task,
        params={
            "source": "direct_link",
            "links": ["https://example.invalid/data"],
            "recursive": False,
        },
        session=env.db,
        repo=repo,
        domain=TaskDomainService(repo),
        add_and_publish_log=log,
    )
    assert result["status"] == "failed"
    assert "Supervisor 尚未接入" in result["error"]
    assert not env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).all()
    assert list(work.glob("*.fastq")) == []


@pytest.mark.parametrize(
    "bound", ["max_registration_entries", "max_registration_files", "max_registration_bytes"]
)
async def test_registration_limits_fail_without_quota_or_asset_side_effects(
    download_env, monkeypatch, bound
):
    from cygnusx.core.exceptions import ValidationError

    env = download_env
    task, work = await make_task(env)
    (work / "a.fastq").write_bytes(b"payload")
    (work / "b.fastq").write_bytes(b"payload")
    config = worker.get_download_config().model_copy(deep=True)
    setattr(config.validation, bound, 1)
    monkeypatch.setattr(worker, "get_download_config", lambda: config)
    with pytest.raises(ValidationError):
        await register_outputs(env, task)
    assert (await env.db.get(UserModel, env.owner)).used_storage == 0
    assert not env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).all()


@pytest.mark.parametrize("forgery", ["task_owner", "missing_baseline", "storage_root"])
async def test_registration_context_fails_closed(download_env, forgery):
    from cygnusx.core.exceptions import ValidationError

    env = download_env
    task, work = await make_task(env)
    (work / "a.fastq").write_bytes(b"payload")
    if forgery == "task_owner":
        task.user_id = env.other
    elif forgery == "missing_baseline":
        task.parameters = {}
    else:
        env.factory._root = env.factory.data_root / "wrong"
    await env.db.flush()
    with pytest.raises(ValidationError):
        await register_outputs(env, task)
    assert not env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).all()


@pytest.mark.parametrize(
    ("scheme", "expected_code"),
    [
        ("http", "DOWNLOAD_PUBLICATION_RECEIPT_REJECTED"),
        ("https", "DOWNLOAD_PROTOCOL_NOT_CERTIFIED"),
    ],
)
async def test_http_registration_requires_supervisor_receipt(
    download_env, monkeypatch, scheme, expected_code
):
    from cygnusx.core.exceptions import ValidationError

    env = download_env
    task, work = await make_task(env)
    task.parameters = {
        "_download_output_baseline": [],
        "source": "direct_link",
        "links": [f"{scheme}://controlled-origin.test/read.fastq"],
    }
    (work / "read.fastq").write_bytes(b"@r\nACGT\n+\nIIII\n")
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            download_execution_supervisor_id=None,
            download_execution_supervisor_public_key_b64=None,
        ),
    )

    with pytest.raises(ValidationError) as error:
        await register_outputs(env, task)
    assert error.value.code == expected_code
    assert not env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.task_id == task.id)
    ).all()
    assert (await env.db.get(UserModel, env.owner)).used_storage == 0


async def test_http_registration_consumes_signed_receipt_in_file_registry_transaction(
    download_env, monkeypatch
):
    from cygnusx.core.exceptions import ValidationError
    from cygnusx.infrastructure.database.models.download_execution import (
        DownloadExecutionReceiptNonceModel,
    )
    from cygnusx.infrastructure.download.trusted_execution import (
        ExecutionBoundaryObservation,
        ExecutionReceiptClaims,
        SignedExecutionReceipt,
        artifact_manifest_sha256,
    )

    env = download_env
    DownloadExecutionReceiptNonceModel.__table__.create(env.db.sync.get_bind())
    monkeypatch.setattr(env.db, "get_bind", lambda: env.db.sync.get_bind())
    task, work = await make_task(env)
    content = b"@r\nACGT\n+\nIIII\n"
    output = work / "read.fastq"
    output.write_bytes(content)
    task.parameters = {
        "_download_output_baseline": [],
        "source": "direct_link",
        "links": ["http://controlled-origin.test/read.fastq"],
    }
    manifest_hash = artifact_manifest_sha256(
        [(output.relative_to(work).as_posix(), hashlib.sha256(content).hexdigest(), len(content))]
    )
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    supervisor_id = "test-supervisor"
    scope_ref = UUID(int=9123)
    attempt_id = UUID(int=9125)
    execution_id = UUID(int=9126)
    policy_revision = "controlled-http-v1"
    environment_id = "acceptance-linux-xfs-v1"
    binary_sha256 = "d" * 64
    now = int(datetime.now(UTC).timestamp())
    observation = ExecutionBoundaryObservation(
        task_id=task.id,
        scope_ref=scope_ref,
        execution_id=execution_id,
        execution_epoch=1,
        policy_revision=policy_revision,
        state="stopped",
        reason="completed",
        rx_admitted_bytes=32,
        rx_observed_bytes=32,
        rx_dropped_bytes=0,
        rx_limit_bytes=1024,
        disk_peak_allocated_bytes=len(content),
        disk_limit_bytes=1024,
        inode_peak_used=1,
        inode_limit=8,
        started_at=now - 2,
        stopped_at=now - 1,
        live_processes=0,
        cgroup_populated=False,
        egress_revoked=True,
        quota_enforced=True,
        cleanup_complete=True,
        returncode=0,
    )
    claims = ExecutionReceiptClaims(
        supervisor_id=supervisor_id,
        task_id=task.id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        scope_ref=scope_ref,
        execution_epoch=1,
        policy_revision=policy_revision,
        environment_id=environment_id,
        binary_sha256=binary_sha256,
        nonce=UUID(int=9124),
        issued_at=now,
        expires_at=now + 30,
        artifact_manifest_sha256=manifest_hash,
        observation=observation,
    )
    payload = json.dumps(
        claims.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    signature = base64.urlsafe_b64encode(private_key.sign(payload)).decode().rstrip("=")
    receipt = SignedExecutionReceipt(claims=claims, signature=signature)
    task.parameters["_download_execution"] = {
        "scope_ref": str(scope_ref),
        "attempt_id": str(attempt_id),
        "execution_id": str(execution_id),
        "execution_epoch": 1,
        "policy_revision": policy_revision,
        "environment_id": environment_id,
        "binary_sha256": binary_sha256,
        "receipt": receipt.model_dump(mode="json"),
    }
    encoded_public_key = base64.urlsafe_b64encode(public_key).decode().rstrip("=")
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            download_execution_supervisor_id=supervisor_id,
            download_execution_supervisor_public_key_b64=encoded_public_key,
        ),
    )

    summary = await register_outputs(env, task)
    assert summary["state"] == "FILES_REGISTERED"
    assert env.db.sync.query(DownloadExecutionReceiptNonceModel).count() == 1
    assert (await env.db.get(UserModel, env.owner)).used_storage == len(content)
    with pytest.raises(ValidationError) as error:
        await register_outputs(env, task)
    assert error.value.code == "DOWNLOAD_PUBLICATION_RECEIPT_REJECTED"


async def test_ri01_invalid_task_reference_never_registers(download_env):
    from uuid import uuid4

    from cygnusx.core.exceptions import ValidationError

    env = download_env
    task, work = await make_task(env)
    (work / "a.fastq").write_bytes(b"payload")
    with pytest.raises(ValidationError, match="任务不匹配"):
        await worker._register_downloaded_files(session=env.db, task_id=uuid4(), user_id=env.owner,
            work_dir=str(work), directory="", storage_root=str(env.factory.data_root))
    assert not env.db.sync.scalars(select(FileRecordModel).where(FileRecordModel.task_id == task.id)).all()


async def test_ri01_project_revocation_blocks_real_registration(download_env):
    from cygnusx.core.exceptions import NotFoundError
    from cygnusx.infrastructure.database.models.project import ProjectModel

    env = download_env
    proposal = await env.service.prepare(env.owner, env.project, request())
    row = await env.db.get(DatasetIngestionModel, UUID(proposal["proposal_id"]))
    task, work = await make_task(env)
    row.task_ids = [str(task.id)]
    project = await env.db.get(ProjectModel, env.project)
    project.user_id = env.other
    (work / "a.fastq").write_bytes(b"payload")
    await env.db.flush()
    with pytest.raises(NotFoundError):
        await register_outputs(env, task)
    assert not env.db.sync.scalars(select(FileRecordModel).where(FileRecordModel.task_id == task.id)).all()


async def test_ri03_10_quota_change_blocks_registration_without_deleting_files(download_env):
    from cygnusx.core.exceptions import ValidationError
    env = download_env
    task, work = await make_task(env)
    payload = work / "data.fastq"
    payload.write_bytes(b"payload")
    user = await env.db.get(UserModel, env.owner)
    user.used_storage = user.storage_quota
    await env.db.flush()
    with pytest.raises(ValidationError, match="配额"):
        await register_outputs(env, task)
    assert payload.read_bytes() == b"payload"
    assert not env.db.sync.scalars(select(FileRecordModel).where(FileRecordModel.task_id == task.id)).all()


async def test_ri01_owner_module_revocation_during_download(download_env):
    from cygnusx.core.exceptions import ValidationError
    env = download_env
    task, work = await make_task(env)
    (work / "data.fastq").write_bytes(b"payload")
    user = await env.db.get(UserModel, env.owner)
    user.disabled_modules = ["downloads"]
    await env.db.flush()
    with pytest.raises(ValidationError, match="权限"):
        await register_outputs(env, task)
    assert not env.db.sync.scalars(select(FileRecordModel).where(FileRecordModel.task_id == task.id)).all()
