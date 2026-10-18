"""Real Task SQL transactions and filesystem; no broker, subprocess or network."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.services import download_service as module
from cygnusx.core.exceptions import ConflictError
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.download import policy, reliability
from cygnusx.infrastructure.storage.backend import LocalStorageBackend
from tests.unit.test_download_registration_contract import download_env as download_env
from tests.unit.test_download_registration_contract import imports as imports
from tests.unit.test_download_registration_contract import registry as registry
from tests.unit.test_download_registration_contract import (
    sandbox_thread_wakeup as sandbox_thread_wakeup,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def env(download_env, monkeypatch):
    e = download_env
    e.db.sync_session = e.db.sync
    monkeypatch.setattr(module, "get_path_factory", lambda: e.factory)
    monkeypatch.setattr(module, "ensure_download_available", lambda *a: None)
    monkeypatch.setattr(policy, "require_download_runtime", lambda *a: None)
    original_dispatch = reliability.dispatch_download
    send = Mock(return_value=True)
    monkeypatch.setattr(reliability, "dispatch_download", send)
    service = module.DownloadService(e.db, LocalStorageBackend(e.factory))
    return SimpleNamespace(
        **vars(e), submit=service.submit, send=send, original_dispatch=original_dispatch
    )


async def test_commit_then_dispatch_and_duplicate_intent(env):
    req = DownloadRequest(accession="SRR123")
    first = await env.submit(str(env.owner), req, project_id=env.project)
    second = await env.submit(str(env.owner), req, project_id=env.project)
    assert first.id == second.id
    assert len(env.db.sync.scalars(select(TaskModel)).all()) == 1
    env.send.assert_not_called()
    await env.db.commit()
    env.send.assert_called_once_with(str(first.id))


async def test_dispatch_log_does_not_claim_broker_ack(monkeypatch, caplog):
    from cygnusx.infrastructure.task_queue import dispatcher

    monkeypatch.setattr(dispatcher, "enqueue_task", Mock(return_value=object()))
    with caplog.at_level("INFO", logger=reliability.logger.name):
        assert reliability.dispatch_download("task-without-confirm") is True
    assert "outcome=transport_call_returned" in caplog.text
    assert "outcome=published" not in caplog.text


async def test_rollback_never_dispatches(env):
    await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.rollback()
    await env.db.commit()
    env.send.assert_not_called()
    assert not env.db.sync.scalars(select(TaskModel)).all()


async def test_key_conflict_and_owner_project_scope(env):
    req = DownloadRequest(accession="SRR123", request_key="same")
    first = await env.submit(str(env.owner), req, project_id=env.project)
    await env.db.commit()
    with pytest.raises(ConflictError):
        await env.submit(
            str(env.owner),
            DownloadRequest(accession="SRR456", request_key="same"),
            project_id=env.project,
        )
    await env.db.rollback()
    other = await env.submit(str(env.other), req)
    assert other.id != first.id


async def test_workdirs_unique_and_links_refused(env, tmp_path):
    first = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    second = await env.submit(str(env.owner), DownloadRequest(accession="SRR456"))
    assert first.work_dir != second.work_dir
    root = env.factory.user_root(str(env.owner))
    (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        await env.submit(
            str(env.owner), DownloadRequest(accession="SRR789", target_directory="escape")
        )


async def test_broker_failure_remains_durable_and_recovery_does_not_replay_running(
    env, monkeypatch
):
    from cygnusx.infrastructure.task_queue import dispatcher

    # Notify executes the real dispatch wrapper, whose broker fails.
    monkeypatch.setattr(reliability, "dispatch_download", env.original_dispatch)
    monkeypatch.setattr(dispatcher, "enqueue_task", Mock(side_effect=OSError("offline")))
    response = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    row = await env.db.get(TaskModel, response.id)
    assert row.status == "queued"
    row.updated_at = datetime.now(UTC) - timedelta(hours=1)
    await env.db.commit()
    sent = Mock(return_value=True)
    monkeypatch.setattr(reliability, "dispatch_download", sent)
    assert (await reliability.reconcile_download_tasks(env.db))["dispatched"] == 1
    row.status = "running"
    row.updated_at = datetime.now(UTC) - timedelta(hours=1)
    await env.db.commit()
    sent.reset_mock()
    assert (await reliability.reconcile_download_tasks(env.db))["reconciliation_required"] == 1
    sent.assert_not_called()
    assert row.parameters["_download_recovery"]["process_tree_stopped"] is False


async def test_commit_failure_never_publishes(env):
    from sqlalchemy import event
    from sqlalchemy.exc import IntegrityError

    await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))

    def fail(session):
        raise IntegrityError("injected commit failure", {}, Exception())

    event.listen(env.db.sync, "before_commit", fail)
    try:
        with pytest.raises(IntegrityError):
            await env.db.commit()
    finally:
        event.remove(env.db.sync, "before_commit", fail)
        await env.db.rollback()
    env.send.assert_not_called()


async def test_cancelled_task_cannot_be_resurrected(env):
    from cygnusx.application.services.task_service import TaskService
    from cygnusx.domain.task.value_objects import TaskStatus
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl

    response = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    repo = TaskRepositoryImpl(env.db)
    stale = await repo.get_by_id(response.id)
    cancelled = await TaskService(env.db).cancel_task(response.id, str(env.owner))
    await env.db.commit()
    assert cancelled.parameters["_download_cancellation"]["process_tree_stopped"] is False
    stale.status = TaskStatus.SUCCESS
    saved = await repo.save(stale)
    assert saved.status == TaskStatus.CANCELLED


@pytest.mark.parametrize("status", ["running", "success", "failed", "cancelled"])
async def test_worker_redelivery_never_executes(env, monkeypatch, status):
    from contextlib import asynccontextmanager

    from cygnusx.infrastructure.celery_app.tasks import download as worker
    from cygnusx.infrastructure.database import session as sessions

    response = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    row = await env.db.get(TaskModel, response.id)
    row.status = status
    await env.db.commit()

    @asynccontextmanager
    async def factory():
        yield env.db

    monkeypatch.setattr(sessions, "get_session_factory", lambda: factory)
    executor = Mock(side_effect=AssertionError("must not execute"))
    monkeypatch.setattr(worker, "get_executor", executor)
    result = await worker._execute_download(str(row.id))
    assert result["status"] == "duplicate_or_reconciliation_required"
    executor.assert_not_called()


async def test_concurrent_calls_and_terminal_retry_keys(env):
    import asyncio

    # Cooperative interleaving on SQLite verifies business dedup, not PG row locks.
    first, joined = await asyncio.gather(
        env.submit(str(env.owner), DownloadRequest(accession="SRR123")),
        env.submit(str(env.owner), DownloadRequest(accession="SRR123", request_key="join")),
    )
    assert first.id == joined.id
    await env.db.commit()
    row = await env.db.get(TaskModel, first.id)
    row.status = "failed"
    await env.db.commit()
    same = await env.submit(str(env.owner), DownloadRequest(accession="SRR123", request_key="join"))
    assert same.id == first.id
    retry = await env.submit(
        str(env.owner), DownloadRequest(accession="SRR123", request_key="retry")
    )
    assert retry.id != first.id
    assert retry.work_dir != first.work_dir


@pytest.mark.parametrize("terminal_status", ["failed", "cancelled"])
async def test_terminal_retry_keeps_file_records_bound_to_their_original_tasks(
    env, terminal_status
):
    import hashlib
    from pathlib import Path

    from cygnusx.infrastructure.celery_app.tasks.download import (
        _prepare_download_registration,
        _register_downloaded_files,
    )
    from cygnusx.infrastructure.database.models.file import FileRecordModel

    original = await env.submit(
        str(env.owner), DownloadRequest(accession="SRR123", request_key="original")
    )
    await env.db.commit()
    await _prepare_download_registration(env.db, original.id, env.owner, original.work_dir)
    old_content = b"old task output"
    old_path = Path(original.work_dir) / "result.fastq"
    old_path.write_bytes(old_content)
    await _register_downloaded_files(
        session=env.db,
        user_id=env.owner,
        task_id=original.id,
        work_dir=original.work_dir,
        directory="downloads",
        storage_root=str(env.factory.data_root),
    )
    original_row = await env.db.get(TaskModel, original.id)
    original_row.status = terminal_status
    await env.db.commit()

    same_key = await env.submit(
        str(env.owner), DownloadRequest(accession="SRR123", request_key="original")
    )
    retry = await env.submit(
        str(env.owner), DownloadRequest(accession="SRR123", request_key="retry")
    )
    assert same_key.id == original.id
    assert retry.id != original.id
    assert retry.work_dir != original.work_dir

    await _prepare_download_registration(env.db, retry.id, env.owner, retry.work_dir)
    new_content = b"new retry output"
    new_path = Path(retry.work_dir) / "result.fastq"
    new_path.write_bytes(new_content)
    await _register_downloaded_files(
        session=env.db,
        user_id=env.owner,
        task_id=retry.id,
        work_dir=retry.work_dir,
        directory="downloads",
        storage_root=str(env.factory.data_root),
    )

    records = env.db.sync.scalars(
        select(FileRecordModel).where(FileRecordModel.user_id == env.owner)
    ).all()
    by_task = {record.task_id: record for record in records}
    old_record, new_record = by_task[original.id], by_task[retry.id]
    assert old_record.id != new_record.id
    assert old_record.storage_path != new_record.storage_path
    assert old_record.checksum == hashlib.sha256(old_content).hexdigest()
    assert new_record.checksum == hashlib.sha256(new_content).hexdigest()


async def test_same_owner_different_project_never_reuses(env):
    from cygnusx.infrastructure.database.models.project import ProjectModel

    other = ProjectModel(
        user_id=env.owner, name="second-project", slug="s4a-distinct-project", status="active"
    )
    env.db.add(other)
    await env.db.flush()
    req = DownloadRequest(accession="SRR123", request_key="same")
    first = await env.submit(str(env.owner), req, project_id=env.project)
    second = await env.submit(str(env.owner), req, project_id=other.id)
    assert first.id != second.id


async def test_savepoint_commit_does_not_publish_before_outer_commit(env):
    async with env.db.begin_nested():
        response = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    env.send.assert_not_called()
    await env.db.commit()
    env.send.assert_called_once_with(str(response.id))


async def test_savepoint_rollback_preserves_outer_dispatch_notifications(env):
    first = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    with pytest.raises(RuntimeError, match="rollback savepoint"):
        async with env.db.begin_nested():
            await env.submit(str(env.owner), DownloadRequest(accession="SRR456"))
            raise RuntimeError("rollback savepoint")

    env.send.assert_not_called()
    await env.db.commit()
    env.send.assert_called_once_with(str(first.id))
    rows = env.db.sync.scalars(select(TaskModel)).all()
    assert [row.id for row in rows] == [first.id]


async def test_cancelled_domain_callback_preserves_cancellation(env):
    from cygnusx.application.services.task_service import TaskService
    from cygnusx.domain.task.services import TaskDomainService
    from cygnusx.domain.task.value_objects import TaskStatus
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl

    response = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    await TaskService(env.db).cancel_task(response.id, str(env.owner))
    repo = TaskRepositoryImpl(env.db)
    task = await repo.get_by_id(response.id)
    result = await TaskDomainService(repo).transition_status(task, TaskStatus.FAILED)
    assert result.status == TaskStatus.CANCELLED


async def test_legacy_rows_are_not_replayed(env):
    row = TaskModel(
        user_id=env.owner,
        flow_id="ebi_download",
        name="legacy",
        status="queued",
        parameters={},
        updated_at=datetime.now(UTC) - timedelta(hours=1),
    )
    env.db.add(row)
    await env.db.commit()
    result = await reliability.reconcile_download_tasks(env.db)
    assert result == {"dispatched": 0, "reconciliation_required": 0}
    env.send.assert_not_called()
