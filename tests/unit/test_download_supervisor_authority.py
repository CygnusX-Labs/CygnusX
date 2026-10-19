"""P0-A authority contract on isolated SQL; no Supervisor or OS backend is started."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionAdmissionModel,
    DownloadExecutionLeaseNonceModel,
)
from cygnusx.infrastructure.database.repositories import download_execution_admission as repo
from cygnusx.infrastructure.download.execution_request import build_execution_boundary_request
from cygnusx.infrastructure.download.supervisor_authority import DatabaseAdmissionAuthority
from cygnusx.infrastructure.download.supervisor_server import SupervisorDeniedError
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryRequest,
    deterministic_execution_id,
)
from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_download_execution_admission import admission_db as _admission_db_fixture

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def admission_db(registry, monkeypatch):
    return _admission_db_fixture.__wrapped__(registry, monkeypatch)


async def prepare_authority(admission_db):
    db, kwargs, _, task, _, _ = admission_db
    if not db.sync.bind.dialect.has_table(db.sync.connection(), "download_execution_lease_nonces"):
        DownloadExecutionLeaseNonceModel.__table__.create(db.sync.bind)
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    task.status = "running"
    task.parameters = {
        **task.parameters,
        "_download_execution_binding": {
            "version": 1,
            "admission_ref": str(admission.id),
            "budget_ref": str(admission.budget_id),
        },
    }
    await db.commit()

    @asynccontextmanager
    async def session_context():
        yield db

    request = ExecutionBoundaryRequest(
        task_id=kwargs["task_id"],
        owner_id=kwargs["owner_id"],
        attempt_id=admission.attempt_id,
        execution_id=deterministic_execution_id(kwargs["task_id"], admission.attempt_id, 1),
        execution_epoch=1,
        admission_ref=admission.id,
        budget_ref=admission.budget_id,
    )
    authority = DatabaseAdmissionAuthority(
        session_factory=session_context,
        lease_seconds=10,
    )
    return db, admission, task, request, authority


async def test_authority_atomically_claims_then_revalidates_exact_epoch(admission_db):
    db, admission, task, request, authority = await prepare_authority(admission_db)

    verified = await authority.revalidate(request, "worker-1", claim=True)
    assert verified.request == request
    assert verified.project_id == admission.project_id
    assert verified.tool_digest == "b" * 64
    assert verified.source_digest == admission.source_digest
    assert verified.rx_limit_bytes == 100
    assert verified.disk_limit_bytes == 4096
    assert verified.inode_limit == 10
    assert verified.http_urls == ("http://source.example/file.tsv",)
    assert [
        (destination.host, destination.port, destination.path)
        for destination in verified.allowed_destinations
    ] == [("source.example", 80, "/file.tsv")]
    assert verified.lease_deadline <= verified.expires_at

    claimed = await db.get(DownloadExecutionAdmissionModel, admission.id)
    assert claimed is not None
    assert claimed.status == "CONSUMED"
    assert claimed.execution_epoch == 1
    lease_nonce = uuid4()
    renewed = await authority.revalidate(
        request,
        "worker-1",
        claim=False,
        lease_nonce=lease_nonce,
        supervisor_id="supervisor-test",
    )
    assert renewed.request == request
    assert renewed.lease_deadline <= renewed.expires_at

    with pytest.raises(SupervisorDeniedError, match="LEASE_NONCE_REPLAY"):
        await authority.revalidate(
            request,
            "worker-1",
            claim=False,
            lease_nonce=lease_nonce,
            supervisor_id="supervisor-test",
        )


async def test_authority_rejects_mismatched_task_binding_before_claim(admission_db):
    db, admission, task, request, authority = await prepare_authority(admission_db)
    task.parameters["_download_execution_binding"]["budget_ref"] = str(uuid4())
    await db.commit()

    with pytest.raises(SupervisorDeniedError, match="TASK_BINDING_REJECTED"):
        await authority.revalidate(request, "worker-1", claim=True)
    unchanged = await db.get(DownloadExecutionAdmissionModel, admission.id)
    assert unchanged is not None
    assert unchanged.status == "READY"
    assert unchanged.execution_epoch == 0


async def test_worker_request_builder_uses_persisted_binding(admission_db):
    _, admission, task, _, _ = await prepare_authority(admission_db)
    request = await build_execution_boundary_request(
        admission_db[0], task.id, task.user_id
    )
    retry_request = await build_execution_boundary_request(
        admission_db[0], task.id, task.user_id
    )
    assert request.admission_ref == admission.id
    assert request.budget_ref == admission.budget_id
    assert request.attempt_id == admission.attempt_id
    assert request.execution_epoch == 1
    assert retry_request.execution_id == request.execution_id
    assert retry_request == request
    assert request.protocol == "http"

    task.parameters["_download_execution_binding"]["admission_ref"] = str(uuid4())
    with pytest.raises(SupervisorDeniedError, match="ADMISSION_NOT_READY|BINDING"):
        await build_execution_boundary_request(admission_db[0], task.id, task.user_id)


async def test_worker_request_builder_rebuilds_consumed_execution_identity(admission_db):
    db, admission, task, request, authority = await prepare_authority(admission_db)

    await authority.revalidate(request, "worker-1", claim=True)
    rebuilt = await build_execution_boundary_request(db, task.id, task.user_id)

    assert rebuilt == request
    assert admission.status == "CONSUMED"
    assert admission.execution_id == request.execution_id


async def test_authority_rejects_wrong_epoch_and_duplicate_claim(admission_db):
    db, admission, _, request, authority = await prepare_authority(admission_db)
    wrong_epoch = request.model_copy(
        update={
            "execution_epoch": 2,
            "execution_id": deterministic_execution_id(request.task_id, request.attempt_id, 2),
        }
    )
    with pytest.raises(SupervisorDeniedError, match="ATTEMPT_BINDING_REJECTED"):
        await authority.revalidate(wrong_epoch, "worker-1", claim=True)

    await authority.revalidate(request, "worker-1", claim=True)
    retry = await authority.revalidate(request, "worker-1", claim=True)
    assert retry.request == request
    with pytest.raises(SupervisorDeniedError, match="EXECUTION_ID_REJECTED"):
        await authority.revalidate(
            request.model_copy(update={"execution_id": uuid4()}),
            "worker-1",
            claim=True,
        )
    claimed = await db.get(DownloadExecutionAdmissionModel, admission.id)
    assert claimed is not None
    assert claimed.execution_epoch == 1
    assert claimed.execution_id == request.execution_id


async def test_authority_rejects_consumed_admission_without_execution_identity(admission_db):
    db, admission, _, request, authority = await prepare_authority(admission_db)
    await authority.revalidate(request, "worker-1", claim=True)
    admission.execution_id = None
    await db.commit()
    with pytest.raises(SupervisorDeniedError, match="DOWNLOAD_ADMISSION_REJECTED"):
        await authority.revalidate(request, "worker-1", claim=True)


async def test_authority_fails_closed_when_runtime_profile_disappears(admission_db):
    db, _, _, request, authority = await prepare_authority(admission_db)
    settings = admission_db[5]
    settings.download_admission_profiles = {}

    with pytest.raises(SupervisorDeniedError, match="DOWNLOAD_ADMISSION_PROFILE_MISSING"):
        await authority.revalidate(request, "worker-1", claim=True)

    admission = await db.get(DownloadExecutionAdmissionModel, request.admission_ref)
    assert admission is not None
    assert admission.status == "READY"


async def test_lease_nonce_constraints_reject_empty_supervisor_and_zero_epoch(admission_db):
    db, *_ = await prepare_authority(admission_db)
    expires_at = datetime.now(UTC) + timedelta(seconds=30)
    for supervisor_id, execution_epoch in (("", 1), ("supervisor-test", 0)):
        with pytest.raises(IntegrityError), db.sync.begin_nested():
            db.add(
                DownloadExecutionLeaseNonceModel(
                    supervisor_id=supervisor_id,
                    nonce=uuid4(),
                    task_id=uuid4(),
                    execution_epoch=execution_epoch,
                    expires_at=expires_at,
                )
            )
            db.sync.flush()
