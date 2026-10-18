"""Real Worker registration + SQLite/FileRegistry + Dataset reconciliation, no network."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager, suppress
from types import SimpleNamespace
from uuid import UUID

import pytest
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


@pytest.mark.parametrize("exit_success", [False, True])
async def test_f12_real_direct_worker_nonzero_preserves_partial_or_rejects_empty_success(
    download_env,
    monkeypatch,
    exit_success,
):
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

    class TransferDouble:
        async def execute(self, context):
            if not exit_success:
                (work / "partial.fastq").write_bytes(b"@r\nACGT\n+\nIIII\n")
            return SimpleNamespace(
                status="success" if exit_success else "failed",
                returncode=0 if exit_success else 1,
                stdout="",
                stderr="transfer stopped" if not exit_success else "",
            )

    monkeypatch.setattr(worker, "get_executor", lambda _: TransferDouble())
    repo = TaskRepositoryImpl(env.db)
    domain_task = await repo.get_by_id(task.id)

    async def log(*args, **kwargs):
        pass

    result = await worker._execute_direct_link_download(
        task_id=str(task.id),
        task_uuid=task.id,
        task=domain_task,
        params={"links": ["https://example.invalid/data"], "recursive": False},
        session=env.db,
        repo=repo,
        domain=TaskDomainService(repo),
        add_and_publish_log=log,
    )
    assert result["status"] == "failed"
    summary = task.parameters["_download_registration"]
    assert summary["state"] == ("RECONCILIATION_REQUIRED" if exit_success else "PARTIAL")
    assert summary["scientific_ready"] is False
    if not exit_success:
        record = env.db.sync.scalars(
            select(FileRecordModel).where(FileRecordModel.task_id == task.id)
        ).one()
        assert record.source == "download" and len(record.checksum) == 64
        assert (work / "partial.fastq").exists()


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
