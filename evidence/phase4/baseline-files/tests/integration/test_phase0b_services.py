"""Real services/domain/builders with isolated files and no database or broker."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.services import download_service, task_service
from cygnusx.core.exceptions import NotFoundError, ValidationError
from cygnusx.domain.task.services import TaskDomainService
from cygnusx.infrastructure.config.storage_config import StorageConfig
from cygnusx.infrastructure.storage.path_factory import StoragePathFactory

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    from cygnusx.application.services import file_service
    from cygnusx.domain.flow import submission_validator
    from cygnusx.infrastructure import storage

    factory = StoragePathFactory(StorageConfig(data_root=str(tmp_path), users_subdir="users"))
    for module in (storage, submission_validator, download_service):
        monkeypatch.setattr(module, "get_path_factory", lambda: factory)
    directories = AsyncMock()
    monkeypatch.setattr(file_service, "ensure_directory_chain", directories)
    owner = str(uuid4())
    factory.user_root(owner).mkdir(parents=True)
    saved = {}

    async def save(task):
        saved[task.id] = task
        return task

    async def get(task_id):
        return saved.get(task_id)

    async def get_key(key):
        return next((t for t in saved.values() if t.idempotency_key == key), None)

    repo = SimpleNamespace(save=AsyncMock(side_effect=save), get_by_id=AsyncMock(side_effect=get),
                           get_by_idempotency_key=AsyncMock(side_effect=get_key))
    queue = Mock()
    monkeypatch.setattr(task_service, "enqueue_task", queue)
    monkeypatch.setattr(download_service, "enqueue_task", queue)
    return SimpleNamespace(factory=factory, owner=owner, repo=repo, saved=saved,
                           queue=queue, directories=directories, db=AsyncMock(spec=AsyncSession))


def analysis_service(env):
    service = task_service.TaskService(env.db)
    service._repo = env.repo
    service._domain = TaskDomainService(env.repo)
    service._settings = SimpleNamespace(enable_cookie_system=False)
    service._write_monitor_config = Mock()
    return service


def request(flow):
    return TaskSubmitRequest(flow_id=flow, name="isolated-project",
        parameters={"raw_data_path": "inbox", "data_deliver": "deliver"},
        sample_sheet=[{"sample": "S1", "sample_name": "S1", "group": "ctrl"},
                      {"sample": "S2", "sample_name": "S2", "group": "treat"}],
        comparisons=[{"name": "Treat_vs_Ctrl", "Control": "ctrl", "Treat": "treat"}],
        idempotency_key="isolated-key")


@pytest.mark.parametrize("flow", ["rna_seq", "atac_seq"])
async def test_actual_service_build_queue_query_and_idempotency(isolated, flow):
    env = isolated
    service = analysis_service(env)
    result = await service.submit(env.owner, request(flow))
    assert result.status == "queued"
    assert env.saved[result.id].idempotency_key == "isolated-key"
    env.queue.assert_called_once()
    config_path = env.queue.call_args.kwargs["config_file"]
    with open(config_path) as stream:  # noqa: ASYNC230 - Tiny isolated fixture, no runtime I/O.
        config = yaml.safe_load(stream)
    assert config
    assert str(env.factory.user_root(env.owner)) in str(config)
    assert (await service.submit(env.owner, request(flow))).id == result.id
    env.queue.assert_called_once()
    assert (await service.get_task(result.id, env.owner)).id == result.id
    with pytest.raises(NotFoundError):
        await service.get_task(result.id, str(uuid4()))


@pytest.mark.parametrize("flow", ["rna_seq", "atac_seq"])
@pytest.mark.parametrize("bad", ["genome", "path", "deliver", "empty_samples", "comparison"])
async def test_final_validation_precedes_all_effects(isolated, flow, bad):
    env = isolated
    req = request(flow)
    if bad == "genome":
        req.parameters["Genome_Version"] = "invalid"
    elif bad == "path":
        req.parameters["raw_data_path"] = "/etc"
    elif bad == "deliver":
        req.parameters["data_deliver"] = "../other-owner"
    elif bad == "empty_samples":
        req.sample_sheet = []
    else:
        req.comparisons = [{"name": "bad", "Control": "unknown", "Treat": "ctrl"}]
    with pytest.raises(ValidationError):
        await analysis_service(env).submit(env.owner, req)
    env.repo.save.assert_not_awaited()
    env.directories.assert_not_awaited()
    env.queue.assert_not_called()
    assert not list(env.factory.user_root(env.owner).iterdir())


async def test_download_submit_queue_and_owner_query(isolated):
    env = isolated
    backend = SimpleNamespace(ensure_dir=AsyncMock())
    service = download_service.DownloadService(env.db, backend=backend)
    service._repo = env.repo
    service._domain = TaskDomainService(env.repo)
    result = await service.submit(env.owner, DownloadRequest(accession="SRR123", dry_run=True))
    assert result.status == "queued"
    assert env.saved[result.id].parameters["dry_run"] is True
    env.queue.assert_called_once()
    assert (await service.get_task_for_user(result.id, env.owner)).id == result.id
    with pytest.raises(NotFoundError):
        await service.get_task_for_user(result.id, str(uuid4()))


@pytest.mark.parametrize("directory", ["../other", "/etc", "safe/../../other", "safe\\other"])
async def test_download_path_rejection_has_no_effect(isolated, directory):
    backend = SimpleNamespace(ensure_dir=AsyncMock())
    service = download_service.DownloadService(isolated.db, backend=backend)
    with pytest.raises(ValidationError):
        await service.submit(isolated.owner, DownloadRequest(accession="SRR123", target_directory=directory))
    backend.ensure_dir.assert_not_awaited()
    isolated.queue.assert_not_called()


async def test_download_symlink_escape_rejected(isolated, tmp_path):
    env = isolated
    outside = tmp_path / "outside"
    outside.mkdir()
    (env.factory.user_root(env.owner) / "downloads").symlink_to(outside, target_is_directory=True)
    backend = SimpleNamespace(ensure_dir=AsyncMock())
    service = download_service.DownloadService(env.db, backend=backend)
    with pytest.raises(ValidationError):
        await service.submit(env.owner, DownloadRequest(accession="SRR123"))
    backend.ensure_dir.assert_not_awaited()


async def test_real_file_registration_owner_paths_and_symlinks(isolated, monkeypatch, tmp_path):
    from cygnusx.infrastructure.celery_app.tasks import download
    from cygnusx.infrastructure.database.repositories import file_repository, user_repository

    env = isolated
    work = env.factory.user_root(env.owner) / "downloads" / "SRR123"
    work.mkdir(parents=True)
    (work / "tiny.fastq.gz").write_bytes(b"isolated-fixture")
    outside = tmp_path / "outside.fastq.gz"
    outside.write_bytes(b"not-owned")
    (work / "escape.fastq.gz").symlink_to(outside)
    files = SimpleNamespace(save=AsyncMock())
    users = SimpleNamespace(add_used_storage=AsyncMock())
    monkeypatch.setattr(file_repository, "FileRepositoryImpl", lambda _: files)
    monkeypatch.setattr(user_repository, "SqlAlchemyUserRepository", lambda _: users)

    async def inline_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(download.asyncio, "to_thread", inline_thread)
    env.db.scalar.return_value = None
    kwargs = dict(session=env.db, user_id=env.owner, work_dir=str(work),
                  directory="downloads", storage_root=str(tmp_path))
    await download._register_downloaded_files(**kwargs)
    files.save.assert_awaited_once()
    record = files.save.call_args.args[0]
    assert str(record.user_id) == env.owner
    assert record.path == f"users/{env.owner}/downloads/SRR123/tiny.fastq.gz"
    assert record.directory == "downloads/SRR123"
    users.add_used_storage.assert_awaited_once_with(env.owner, len(b"isolated-fixture"))
    env.db.scalar.return_value = uuid4()
    await download._register_downloaded_files(**kwargs)
    files.save.assert_awaited_once()
    with pytest.raises(ValidationError):
        await download._register_downloaded_files(**{**kwargs, "user_id": str(uuid4())})
