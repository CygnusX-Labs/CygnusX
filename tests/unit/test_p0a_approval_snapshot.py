"""P0-A approval provenance with explicit isolated SQL and in-memory nonce store."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from cygnusx.application.services import dataset_import_service as module
from cygnusx.core.exceptions import AuthorizationError, ConflictError
from cygnusx.infrastructure.database.models.dataset import DatasetIngestionModel
from tests.unit.test_dataset_import_handoff import imports as imports
from tests.unit.test_dataset_import_handoff import request
from tests.unit.test_dataset_phase3 import registry as registry

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
IDENTITY = "a" * 64


async def proposal(registry, imports):
    db, _, owner, _, project, *_ = registry
    service, *_ = imports
    prepared = await service.prepare(owner, project, request())
    iid = UUID(prepared["proposal_id"])
    row = await db.get(DatasetIngestionModel, iid)
    return service, owner, project, iid, row


async def test_missing_jwt_provenance_does_not_approve(registry, imports):
    service, owner, project, iid, row = await proposal(registry, imports)
    with pytest.raises(AuthorizationError, match="JWT"):
        await service.decide(owner, project, iid, True)
    record = await service.confirmations.get_status(str(owner), row.confirmation_id)
    assert record.status == "PENDING" and row.approval_snapshot is None


async def test_snapshot_records_only_hash_and_is_idempotent(registry, imports):
    service, owner, project, iid, row = await proposal(registry, imports)
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash=IDENTITY)
    snapshot = deepcopy(row.approval_snapshot)
    assert snapshot["auth_session_or_jti_hash"] == IDENTITY
    assert snapshot["actor_id"] == str(owner)
    assert snapshot["nonce_status"] == "APPROVED"
    assert snapshot["consumed_at"] is None
    assert snapshot["request_digest"] == row.parameters_hash
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash="b" * 64)
    assert row.approval_snapshot == snapshot


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "different"),
        ("project_id", "different"),
        ("request_digest", "0" * 64),
        ("source_digest", "0" * 64),
        ("nonce_status", "CONSUMED"),
        ("revoked_at", "now"),
        ("approval_version", 2),
        ("max_budget", 1),
    ],
)
async def test_snapshot_tampering_fails_before_consume(registry, imports, field, value):
    service, owner, project, iid, row = await proposal(registry, imports)
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash=IDENTITY)
    row.approval_snapshot = {**row.approval_snapshot, field: value}
    record = await service.confirmations.get_status(str(owner), row.confirmation_id)
    with pytest.raises(ConflictError):
        service.validate_approval_snapshot(row, record, owner, project)
    assert record.status == "APPROVED"


async def test_redis_approval_without_snapshot_cannot_reconstruct_identity(registry, imports):
    service, owner, project, iid, row = await proposal(registry, imports)
    await service.confirmations.approve_by_human(
        user_id=str(owner), confirmation_id=row.confirmation_id
    )
    with pytest.raises(ConflictError, match="持久记录"):
        await service.decide(owner, project, iid, True, auth_session_or_jti_hash=IDENTITY)
    assert row.approval_snapshot is None


async def test_expiry_and_missing_redis_are_fail_closed(registry, imports):
    service, owner, project, iid, row = await proposal(registry, imports)
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash=IDENTITY)
    record = await service.confirmations.get_status(str(owner), row.confirmation_id)
    record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(ConflictError):
        service.validate_approval_snapshot(row, record, owner, project)
    store = await service.confirmations._get_store()
    store._records.clear()
    with pytest.raises(ConflictError):
        await service.decide(owner, project, iid, True, auth_session_or_jti_hash=IDENTITY)


async def test_reject_revokes_durable_snapshot(registry, imports):
    service, owner, project, iid, row = await proposal(registry, imports)
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash=IDENTITY)
    await service.decide(owner, project, iid, False)
    assert row.approval_snapshot["status"] == "REJECTED"
    assert row.approval_snapshot["revoked_at"]


async def test_redis_consume_then_commit_failure_does_not_permit_replay(
    registry, imports, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from cygnusx.infrastructure.database.models.task import TaskModel
    from cygnusx.infrastructure.database.repositories import download_execution_admission
    from tests.unit.test_dataset_import_handoff import processed_http_fixture

    db, _, owner, _, project, *_ = registry
    service, *_ = imports
    prepared = await service.prepare(owner, project, processed_http_fixture(imports, monkeypatch))
    iid = UUID(prepared["proposal_id"])
    row = await db.get(DatasetIngestionModel, iid)
    await service.decide(owner, project, iid, True, auth_session_or_jti_hash=IDENTITY)
    await db.commit()
    confirmation_id = row.confirmation_id
    monkeypatch.setattr(module, "require_import_write", lambda: None)

    async def submit(self, uid, req, *, project_id=None):
        task = TaskModel(
            user_id=owner,
            parameters={"project_id": str(project)},
            flow_id="download",
            name="SQL window",
            status="queued",
        )
        db.add(task)
        await db.flush()
        return SimpleNamespace(id=task.id)

    monkeypatch.setattr(module.DownloadService, "submit", submit)
    # Only outer SQL failure/Redis consumption is under test, not admission issue.
    admission = SimpleNamespace(id=uuid4(), budget_id=uuid4())
    monkeypatch.setattr(
        download_execution_admission,
        "issue_processed_http_admission",
        AsyncMock(return_value=admission),
    )
    await service.execute(owner, project, iid)
    assert row.approval_snapshot["nonce_status"] == "CONSUMED"
    task_row = await db.get(TaskModel, UUID(row.task_ids[0]))
    assert task_row is not None
    binding = task_row.parameters["_download_execution_binding"]
    assert binding == {
        "version": 1,
        "admission_ref": str(admission.id),
        "budget_ref": str(admission.budget_id),
    }

    async def failed_commit():
        raise RuntimeError("isolated commit failure")

    monkeypatch.setattr(service.db, "commit", failed_commit)
    with pytest.raises(RuntimeError, match="commit failure"):
        await service.db.commit()
    await db.rollback()
    record = await service.confirmations.get_status(str(owner), confirmation_id)
    assert record.status == "CONSUMED"
    restored = await db.get(DatasetIngestionModel, iid)
    assert restored.state == "PREPARED"
    assert restored.approval_snapshot["nonce_status"] == "APPROVED"
    assert not restored.task_ids
    with pytest.raises(ConflictError) as exc_info:
        await service.execute(owner, project, iid)
    assert exc_info.value.code == "RECONCILIATION_REQUIRED"
