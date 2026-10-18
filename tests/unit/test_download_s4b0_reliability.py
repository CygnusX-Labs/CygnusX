"""Regression of concrete S4-A boundary defects, real SQL and services."""

from datetime import UTC, datetime, timedelta

import pytest

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.services.task_service import TaskService
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.download import reliability
from tests.unit.test_download_s4a_reliability import (
    download_env as download_env,
)
from tests.unit.test_download_s4a_reliability import (
    env as env,
)
from tests.unit.test_download_s4a_reliability import (
    imports as imports,
)
from tests.unit.test_download_s4a_reliability import (
    registry as registry,
)
from tests.unit.test_download_s4a_reliability import (
    sandbox_thread_wakeup as sandbox_thread_wakeup,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_legacy_prefix_cannot_starve_recoverable_task(env):
    for i in range(101):
        env.db.add(
            TaskModel(
                user_id=env.owner,
                flow_id="ebi_download",
                name=f"legacy-{i}",
                status="queued",
                parameters={},
                updated_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    row = await env.db.get(TaskModel, task.id)
    row.updated_at = datetime.now(UTC) - timedelta(hours=1)
    await env.db.commit()
    env.send.reset_mock()
    result = await reliability.reconcile_download_tasks(env.db)
    assert result["dispatched"] == 1


async def test_repeat_cancel_is_idempotent(env):
    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    service = TaskService(env.db)
    first = await service.cancel_task(task.id, str(env.owner))
    second = await service.cancel_task(task.id, str(env.owner))
    assert first.parameters == second.parameters


async def test_session_close_clears_pending_notifications(env):
    await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    env.db.sync.close()
    assert not env.db.sync.info.get("download_dispatch")


async def test_stale_worker_preserves_alias_and_registration(env):
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl

    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    repo = TaskRepositoryImpl(env.db)
    stale = await repo.get_by_id(task.id)
    await env.submit(str(env.owner), DownloadRequest(accession="SRR123", request_key="joined"))
    row = await env.db.get(TaskModel, task.id)
    row.parameters = {**row.parameters, "_download_registration": {"state": "FILES_REGISTERED"}}
    await env.db.flush()
    saved = await repo.save(stale)
    assert len(saved.parameters["_download_request_keys"]) == 1
    assert saved.parameters["_download_registration"]["state"] == "FILES_REGISTERED"


async def test_keyless_terminal_reuses_explicit_intent(env):
    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123", request_key="a"))
    row = await env.db.get(TaskModel, task.id)
    row.status = "failed"
    await env.db.commit()
    same = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    assert same.id == task.id


async def test_recovery_rotates_batches_and_throttles_retry(env):
    for i in range(105):
        env.db.add(
            TaskModel(
                user_id=env.owner,
                flow_id="ebi_download",
                name=f"queued-{i}",
                status="queued",
                parameters={"_download_reliability": {"version": 1}},
                updated_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
    await env.db.commit()
    results = [await reliability.reconcile_download_tasks(env.db) for _ in range(3)]
    assert [r["dispatched"] for r in results] == [100, 5, 0]
    assert len(set(call.args[0] for call in env.send.call_args_list)) == 105


async def test_broker_outage_recovery_obeys_cooldown_and_beat_interval(env, monkeypatch):
    from unittest.mock import Mock

    from cygnusx.infrastructure.celery_app.celery import celery_app
    from cygnusx.infrastructure.task_queue import dispatcher

    schedule = celery_app.conf.beat_schedule["download-task-reconcile"]["schedule"]
    assert schedule == 600.0

    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    row = await env.db.get(TaskModel, task.id)
    row.updated_at = datetime.now(UTC) - timedelta(minutes=20)
    await env.db.commit()

    broker_send = Mock(side_effect=OSError("broker unavailable"))
    monkeypatch.setattr(reliability, "dispatch_download", env.original_dispatch)
    monkeypatch.setattr(dispatcher, "enqueue_task", broker_send)

    first = await reliability.reconcile_download_tasks(env.db)
    assert first == {"dispatched": 0, "reconciliation_required": 0}
    assert broker_send.call_count == 1
    row = await env.db.get(TaskModel, task.id)
    assert row.parameters["_download_reliability"]["recovery_attempts"] == 1

    immediate = await reliability.reconcile_download_tasks(env.db)
    assert immediate == {"dispatched": 0, "reconciliation_required": 0}
    assert broker_send.call_count == 1

    row.updated_at = datetime.now(UTC) - timedelta(minutes=9, seconds=59)
    await env.db.commit()
    before_cooldown = await reliability.reconcile_download_tasks(env.db)
    assert before_cooldown == {"dispatched": 0, "reconciliation_required": 0}
    assert broker_send.call_count == 1

    row.updated_at = datetime.now(UTC) - timedelta(minutes=10, seconds=1)
    await env.db.commit()
    after_cooldown = await reliability.reconcile_download_tasks(env.db)
    assert after_cooldown == {"dispatched": 0, "reconciliation_required": 0}
    assert broker_send.call_count == 2
    row = await env.db.get(TaskModel, task.id)
    assert row.parameters["_download_reliability"]["recovery_attempts"] == 2


async def test_recovery_backlog_advances_ahead_of_newer_stale_arrivals(env):
    from uuid import uuid4

    old_ids = [uuid4() for _ in range(105)]
    for task_id in old_ids:
        env.db.add(
            TaskModel(
                id=task_id,
                user_id=env.owner,
                flow_id="ebi_download",
                name="old-backlog",
                status="queued",
                parameters={"_download_reliability": {"version": 1}},
                updated_at=datetime.now(UTC) - timedelta(hours=2),
            )
        )
    await env.db.commit()

    first = await reliability.reconcile_download_tasks(env.db)
    first_ids = {call.args[0] for call in env.send.call_args_list}
    pending_old = {str(task_id) for task_id in old_ids} - first_ids
    assert first["dispatched"] == 100
    assert len(pending_old) == 5

    new_ids = [uuid4() for _ in range(100)]
    for task_id in new_ids:
        env.db.add(
            TaskModel(
                id=task_id,
                user_id=env.owner,
                flow_id="ebi_download",
                name="newer-stale-arrival",
                status="queued",
                parameters={"_download_reliability": {"version": 1}},
                updated_at=datetime.now(UTC) - timedelta(minutes=20),
            )
        )
    await env.db.commit()

    second = await reliability.reconcile_download_tasks(env.db)
    second_ids = {call.args[0] for call in env.send.call_args_list} - first_ids
    assert second["dispatched"] == 100
    assert pending_old <= second_ids
    assert len(second_ids - pending_old) == 95


async def test_postcommit_exception_does_not_hide_committed_task(env, monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(
        reliability, "dispatch_download", Mock(side_effect=RuntimeError("lost ack"))
    )
    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    same = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    assert same.id == task.id
    assert not env.db.sync.info.get("download_dispatch")


async def test_alias_limit_preserves_existing_keys(env, monkeypatch):
    from cygnusx.application.services import download_service as module
    from cygnusx.core.exceptions import ConflictError
    from cygnusx.tools.download.config import DownloadConfig, DownloadReliabilityConfig

    monkeypatch.setattr(
        module,
        "get_download_config",
        lambda: DownloadConfig(reliability=DownloadReliabilityConfig(max_request_keys=2)),
    )
    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123", request_key="a"))
    await env.submit(str(env.owner), DownloadRequest(accession="SRR123", request_key="b"))
    with pytest.raises(ConflictError) as error:
        await env.submit(str(env.owner), DownloadRequest(accession="SRR123", request_key="c"))
    assert error.value.code == "DOWNLOAD_REQUEST_KEYS_LIMIT"
    same = await env.submit(str(env.owner), DownloadRequest(accession="SRR123", request_key="b"))
    assert same.id == task.id


async def test_rollback_marker_is_not_an_asset(env):
    import json
    from pathlib import Path

    from cygnusx.infrastructure.download.outputs import is_control_file

    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    work = Path(task.work_dir)
    await env.db.rollback()
    marker = work / ".download-task.json"
    facts = json.loads(marker.read_text())
    assert facts["task_id"] == str(task.id)
    assert facts["owner_id"] == str(env.owner)
    assert is_control_file(marker, work)


async def test_cancel_then_finalize_never_registers(env):
    import asyncio
    from pathlib import Path

    from cygnusx.infrastructure.celery_app.tasks.download import _finalize_download_files

    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    await TaskService(env.db).cancel_task(task.id, str(env.owner))
    await asyncio.to_thread(Path(task.work_dir, "payload.fastq").write_text, "partial")
    result = await _finalize_download_files(
        env.db, task.id, env.owner, task.work_dir, "downloads", str(env.factory.data_root), True
    )
    assert result is False
    row = await env.db.get(TaskModel, task.id)
    assert row.status == "cancelled"
    assert row.parameters["_download_recovery"]["state"] == "RECONCILIATION_REQUIRED"


async def test_failed_task_rejects_late_success(env):
    from cygnusx.domain.task.value_objects import TaskStatus
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl

    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    repo = TaskRepositoryImpl(env.db)
    stale = await repo.get_by_id(task.id)
    row = await env.db.get(TaskModel, task.id)
    row.status = "failed"
    await env.db.flush()
    stale.status = TaskStatus.SUCCESS
    saved = await repo.save(stale)
    assert saved.status == TaskStatus.FAILED


async def test_recovery_commit_failure_keeps_queued_fact(env, monkeypatch):
    from unittest.mock import AsyncMock

    task = await env.submit(str(env.owner), DownloadRequest(accession="SRR123"))
    await env.db.commit()
    row = await env.db.get(TaskModel, task.id)
    row.updated_at = datetime.now(UTC) - timedelta(hours=1)
    await env.db.commit()
    env.send.reset_mock()
    original = env.db.commit
    monkeypatch.setattr(env.db, "commit", AsyncMock(side_effect=RuntimeError("commit failed")))
    with pytest.raises(RuntimeError):
        await reliability.reconcile_download_tasks(env.db)
    await env.db.rollback()
    env.send.assert_not_called()
    monkeypatch.setattr(env.db, "commit", original)
    queued = await env.db.get(TaskModel, task.id)
    assert queued.status == "queued"
    assert queued.parameters["_download_reliability"].get("recovery_attempts", 0) == 0

    result = await reliability.reconcile_download_tasks(env.db)
    recovered = await env.db.get(TaskModel, task.id)
    assert result["dispatched"] == 1
    assert recovered.status == "queued"
    assert recovered.parameters["_download_reliability"]["recovery_attempts"] == 1
    env.send.assert_called_once_with(str(task.id))
