"""P0-A real ORM bindings on isolated SQLite; no PG concurrency certification."""

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.infrastructure.database.models.dataset import DatasetIngestionModel
from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionAdmissionModel,
    DownloadExecutionBudgetModel,
    DownloadExecutionReceiptNonceModel,
)
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.database.repositories import download_execution_admission as repo
from cygnusx.infrastructure.database.repositories.download_execution_receipt import (
    settle_execution_budget_from_receipt_in_transaction,
)
from cygnusx.infrastructure.download.reliability import intent_digest, notify_after_commit
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionReceiptClaims,
    SignedExecutionReceipt,
)
from tests.unit.test_dataset_phase3 import registry as registry

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def admission_db(registry, monkeypatch):
    db, _, owner, _, project, *_ = registry
    monkeypatch.setattr(db, "get_bind", lambda: db.sync.get_bind())
    for model in (DatasetIngestionModel, TaskModel, DownloadExecutionBudgetModel,
                  DownloadExecutionAdmissionModel, DownloadExecutionReceiptNonceModel):
        model.__table__.create(db.sync.bind)
    iid, tid = uuid4(), uuid4()
    expires = datetime.now(UTC) + timedelta(minutes=5)
    req = DownloadRequest(source="direct_link", links=["http://source.example/file.tsv"],
                          target_directory="projects/owned/downloads")
    bound = {"owner_id": str(owner), "project_id": str(project), "proposal_id": str(iid),
             "input": {"mode": "processed"}, "requests": [req.model_dump(mode="json")],
             "candidate": {"source": "offline synthetic"}, "max_bytes": 100}
    digest = hashlib.sha256(json.dumps(bound, sort_keys=True, ensure_ascii=False,
                                      default=str).encode()).hexdigest()
    snapshot = {"approval_id": "confirmation-1", "approval_version": 1,
                "actor_id": str(owner), "owner_id": str(owner), "project_id": str(project),
                "ingestion_id": str(iid), "proposal_digest": repo._digest(bound),
                "request_digest": digest, "source_digest": repo._digest(bound["candidate"]),
                "scope": "dataset.execute_import", "method": "processed_http",
                "max_budget": 100, "status": "APPROVED", "revoked_at": None,
                "nonce_status": "CONSUMED",
                "nonce_hash": hashlib.sha256(b"confirmation-1").hexdigest(),
                "auth_session_or_jti_hash": "a" * 64,
                "approved_at": (datetime.now(UTC) - timedelta(seconds=2)).isoformat(),
                "consumed_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                "expires_at": expires.isoformat()}
    row = DatasetIngestionModel(id=iid, user_id=owner, project_id=project, request_key="key",
        parameters_hash=digest, normalized_request=bound, confirmation_id="confirmation-1",
        task_ids=[str(tid)], state="SUBMITTING", approval_snapshot=snapshot)
    params = {key: getattr(req, key) for key in ("source", "links", "download_threads",
              "overwrite_policy", "recursive", "target_directory")}
    params["project_id"] = str(project)
    params["_download_intent"] = intent_digest(str(owner), str(project), params)
    params["_download_reliability"] = {"version": 1}
    task = TaskModel(id=tid, user_id=owner, name="synthetic", flow_id="ebi_download",
                     status="queued", parameters=params)
    db.add(row)
    db.add(task)
    db.sync.commit()
    profile = {"caller_kind": "worker", "caller_id": "worker-1",
        "environment_id": "isolated", "tool_digest": "b" * 64,
        "policy_revision": "policy-1",
        "allowed_destinations": [{"host": "source.example", "port": 80, "path": "/file.tsv"}],
        "disk_block_limit_bytes": 4096, "disk_inodes_limit": 10}
    settings = SimpleNamespace(download_admission_profiles={"isolated": profile})
    monkeypatch.setattr(repo, "get_settings", lambda: settings)
    kwargs = dict(ingestion_id=iid, task_id=tid, owner_id=owner, project_id=project,
        confirmation_id="confirmation-1", request_digest=digest, limit_bytes=100,
        policy_revision="policy-1", environment_id="isolated", caller_id="worker-1",
        allowed_destinations=profile["allowed_destinations"], expires_at=expires)
    return db, kwargs, row, task, profile, settings


def claim(kwargs, admission):
    return dict(task_id=kwargs["task_id"], owner_id=kwargs["owner_id"],
        request_digest=kwargs["request_digest"], caller_id=kwargs["caller_id"],
        attempt_id=admission.attempt_id, expected_epoch=0, tool_digest="b" * 64,
        environment_id="isolated")


def signed_terminal_receipt(admission, kwargs, *, now, rx_bytes=40, state="stopped"):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    execution_id, scope_ref = uuid4(), uuid4()
    observation = ExecutionBoundaryObservation(
        task_id=kwargs["task_id"], scope_ref=scope_ref, execution_id=execution_id,
        execution_epoch=admission.execution_epoch, policy_revision="policy-1",
        state=state, reason="cancelled", rx_admitted_bytes=rx_bytes,
        rx_observed_bytes=rx_bytes, rx_dropped_bytes=0, rx_limit_bytes=100,
        disk_peak_allocated_bytes=512, disk_limit_bytes=4096,
        inode_peak_used=2, inode_limit=10, started_at=now - 2, stopped_at=now - 1,
        live_processes=0, cgroup_populated=False, egress_revoked=True,
        quota_enforced=True, cleanup_complete=True, returncode=1,
    )
    claims = ExecutionReceiptClaims(
        supervisor_id="supervisor-acceptance", task_id=kwargs["task_id"],
        attempt_id=admission.attempt_id, execution_id=execution_id, scope_ref=scope_ref,
        execution_epoch=admission.execution_epoch, policy_revision="policy-1",
        environment_id="isolated", binary_sha256="b" * 64, nonce=uuid4(),
        issued_at=now, expires_at=now + 30, artifact_manifest_sha256="c" * 64,
        observation=observation,
    )
    payload = json.dumps(
        claims.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    signature = base64.urlsafe_b64encode(private_key.sign(payload)).decode().rstrip("=")
    return SignedExecutionReceipt(claims=claims, signature=signature), public_key, execution_id, scope_ref


async def test_processed_http_admission_is_bound_and_consumed_once(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    budget = await db.get(DownloadExecutionBudgetModel, admission.budget_id)
    assert budget.reserved_bytes == 100 and budget.admitted_bytes is None
    args = claim(kwargs, admission)
    consumed = await repo.consume_execution_admission(db, admission.id, **args)
    assert consumed.status == "CONSUMED" and consumed.execution_epoch == 1
    first_identity = consumed.execution_id
    first_budget = (budget.reserved_bytes, budget.admitted_bytes)
    with pytest.raises(repo.DownloadExecutionAdmissionError):
        await repo.consume_execution_admission(db, admission.id, **args)
    replayed = await db.get(DownloadExecutionAdmissionModel, admission.id)
    replayed_budget = await db.get(DownloadExecutionBudgetModel, admission.budget_id)
    assert replayed is not None and replayed.execution_epoch == 1
    assert replayed.execution_id == first_identity
    assert replayed_budget is not None
    assert (replayed_budget.reserved_bytes, replayed_budget.admitted_bytes) == first_budget


async def test_claim_rejects_non_deterministic_execution_identity(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="EXECUTION_ID_INVALID"):
        await repo.consume_execution_admission(
            db, admission.id, **{**claim(kwargs, admission), "execution_id": uuid4()}
        )
    assert admission.status == "READY"


async def test_resolver_requires_both_server_issued_references(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    for budget_id in (uuid4(), admission.budget_id):
        if budget_id == admission.budget_id:
            pair = await repo.resolve_execution_admission(db, admission.id, budget_id,
                task_id=kwargs["task_id"], owner_id=kwargs["owner_id"], caller_id="worker-1")
            assert pair[1].admitted_bytes is None
        else:
            with pytest.raises(repo.DownloadExecutionAdmissionError):
                await repo.resolve_execution_admission(db, admission.id, budget_id,
                    task_id=kwargs["task_id"], owner_id=kwargs["owner_id"], caller_id="worker-1")


async def test_budget_reservation_is_conditional_and_revoke_blocks_consumption(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="EXCEEDED"):
        await repo.reserve_execution_budget(db, admission.budget_id, amount=1)
    await repo.revoke_execution_admission(db, admission.id)
    await repo.revoke_execution_admission(db, admission.id)
    budget = await db.get(DownloadExecutionBudgetModel, admission.budget_id)
    assert admission.status == "REVOKED" and budget.reserved_bytes == 0
    with pytest.raises(repo.DownloadExecutionAdmissionError):
        await repo.consume_execution_admission(db, admission.id, **claim(kwargs, admission))


async def test_mismatched_caller_cannot_consume_admission(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    args = {**claim(kwargs, admission), "caller_id": "worker-evil"}
    with pytest.raises(repo.DownloadExecutionAdmissionError):
        await repo.consume_execution_admission(db, admission.id, **args)


@pytest.mark.parametrize("field,value", [("nonce_status", "APPROVED"),
    ("status", "REJECTED"), ("project_id", "foreign"),
    ("source_digest", "c" * 64), ("auth_session_or_jti_hash", "")])
async def test_snapshot_corruption_creates_no_budget(admission_db, field, value):
    db, kwargs, row, *_ = admission_db
    row.approval_snapshot = {**row.approval_snapshot, field: value}
    with pytest.raises(repo.DownloadExecutionAdmissionError):
        await repo.issue_processed_http_admission(db, **kwargs)
    assert db.sync.scalars(select(DownloadExecutionBudgetModel)).all() == []


@pytest.mark.parametrize("binding,value", [("attempt_id", uuid4()),
    ("expected_epoch", 1), ("tool_digest", "c" * 64), ("environment_id", "other")])
async def test_claim_requires_exact_fencing(admission_db, binding, value):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    with pytest.raises(repo.DownloadExecutionAdmissionError):
        await repo.consume_execution_admission(db, admission.id,
            **{**claim(kwargs, admission), binding: value})
    assert admission.status == "READY"


async def test_claimed_revoke_keeps_unknown_budget(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    await repo.consume_execution_admission(db, admission.id, **claim(kwargs, admission))
    await repo.revoke_execution_admission(db, admission.id)
    await repo.revoke_execution_admission(db, admission.id)
    budget = await db.get(DownloadExecutionBudgetModel, admission.budget_id)
    assert admission.status == "RECONCILIATION_REQUIRED"
    assert budget.reserved_bytes == 100 and budget.admitted_bytes is None


async def test_verified_stopped_receipt_settles_actual_rx_and_releases_remainder(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    await repo.consume_execution_admission(db, admission.id, **claim(kwargs, admission))
    await repo.revoke_execution_admission(db, admission.id)
    assert admission.status == "RECONCILIATION_REQUIRED"
    await db.commit()
    now = int(datetime.now(UTC).timestamp())
    receipt, public_key, execution_id, scope_ref = signed_terminal_receipt(
        admission, kwargs, now=now,
    )

    budget = await settle_execution_budget_from_receipt_in_transaction(
        db, admission.id, admission.budget_id, receipt,
        supervisor_public_key=public_key,
        expected_supervisor_id="supervisor-acceptance",
        expected_execution_id=execution_id,
        expected_scope_ref=scope_ref,
        expected_binary_sha256="b" * 64,
        expected_artifact_manifest_sha256="c" * 64,
        now_epoch_seconds=now,
    )
    assert admission.status == "SETTLED"
    assert budget.reserved_bytes == 40 and budget.admitted_bytes == 40
    budget = await repo.reserve_execution_budget(db, budget.id, amount=60)
    assert budget.reserved_bytes == 100 and budget.admitted_bytes == 40
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="EXCEEDED"):
        await repo.reserve_execution_budget(db, budget.id, amount=1)
    await db.commit()
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="BINDING_REJECTED"):
        await settle_execution_budget_from_receipt_in_transaction(
            db, admission.id, admission.budget_id, receipt,
            supervisor_public_key=public_key,
            expected_supervisor_id="supervisor-acceptance",
            expected_execution_id=execution_id,
            expected_scope_ref=scope_ref,
            expected_binary_sha256="b" * 64,
            expected_artifact_manifest_sha256="c" * 64,
            now_epoch_seconds=now,
        )


async def test_revoke_cannot_reopen_a_settled_admission(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    await repo.consume_execution_admission(db, admission.id, **claim(kwargs, admission))
    await db.commit()
    now = int(datetime.now(UTC).timestamp())
    receipt, public_key, execution_id, scope_ref = signed_terminal_receipt(
        admission, kwargs, now=now,
    )
    budget = await settle_execution_budget_from_receipt_in_transaction(
        db, admission.id, admission.budget_id, receipt,
        supervisor_public_key=public_key,
        expected_supervisor_id="supervisor-acceptance",
        expected_execution_id=execution_id,
        expected_scope_ref=scope_ref,
        expected_binary_sha256="b" * 64,
        expected_artifact_manifest_sha256="c" * 64,
        now_epoch_seconds=now,
    )
    await db.commit()
    settled_reserved = budget.reserved_bytes
    settled_admitted = budget.admitted_bytes

    await repo.revoke_execution_admission(db, admission.id)
    await db.commit()

    assert admission.status == "SETTLED"
    assert admission.revoked is False
    assert budget.reserved_bytes == settled_reserved == 40
    assert budget.admitted_bytes == settled_admitted == 40
    replacement_receipt, _, replacement_execution, replacement_scope = signed_terminal_receipt(
        admission, kwargs, now=now,
    )
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="BINDING_REJECTED"):
        await settle_execution_budget_from_receipt_in_transaction(
            db, admission.id, admission.budget_id, replacement_receipt,
            supervisor_public_key=public_key,
            expected_supervisor_id="supervisor-acceptance",
            expected_execution_id=replacement_execution,
            expected_scope_ref=replacement_scope,
            expected_binary_sha256="b" * 64,
            expected_artifact_manifest_sha256="c" * 64,
            now_epoch_seconds=now,
        )


async def test_unconfirmed_stop_cannot_settle_or_release_budget(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    await repo.consume_execution_admission(db, admission.id, **claim(kwargs, admission))
    await db.commit()
    now = int(datetime.now(UTC).timestamp())
    receipt, public_key, execution_id, scope_ref = signed_terminal_receipt(
        admission, kwargs, now=now, state="unknown",
    )

    with pytest.raises(repo.DownloadExecutionAdmissionError, match="STOP_UNCONFIRMED"):
        await settle_execution_budget_from_receipt_in_transaction(
            db, admission.id, admission.budget_id, receipt,
            supervisor_public_key=public_key,
            expected_supervisor_id="supervisor-acceptance",
            expected_execution_id=execution_id,
            expected_scope_ref=scope_ref,
            expected_binary_sha256="b" * 64,
            expected_artifact_manifest_sha256="c" * 64,
            now_epoch_seconds=now,
        )
    await db.rollback()
    budget = await db.get(DownloadExecutionBudgetModel, admission.budget_id)
    assert budget.reserved_bytes == 100 and budget.admitted_bytes is None


async def test_rollback_removes_admission_and_does_not_dispatch(admission_db, monkeypatch):
    db, kwargs, *_ = admission_db
    from cygnusx.infrastructure.download import reliability

    dispatched = []
    monkeypatch.setattr(reliability, "dispatch_download", dispatched.append)
    await repo.issue_processed_http_admission(db, **kwargs)
    notify_after_commit(db.sync, kwargs["task_id"])
    assert dispatched == []
    await db.rollback()
    await db.commit()
    assert dispatched == []
    assert db.sync.scalars(select(DownloadExecutionAdmissionModel)).all() == []
    assert db.sync.scalars(select(DownloadExecutionBudgetModel)).all() == []


@pytest.mark.parametrize("amount", [0, -1, True, 1 << 63])
async def test_invalid_budget_amounts(admission_db, amount):
    db, *_ = admission_db
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="INVALID"):
        await repo.reserve_execution_budget(db, uuid4(), amount=amount)


async def test_bigint_reservation_and_overflow_guard(admission_db):
    db, kwargs, *_ = admission_db
    budget = DownloadExecutionBudgetModel(id=uuid4(), owner_id=kwargs["owner_id"],
        project_id=kwargs["project_id"], limit_bytes=repo.MAX_BYTES, reserved_bytes=0,
        admitted_bytes=None, disk_block_limit_bytes=4096, disk_inodes_limit=1,
        status="ACTIVE", policy_revision="p", expires_at=kwargs["expires_at"])
    db.add(budget)
    await db.flush()
    result = await repo.reserve_execution_budget(db, budget.id, amount=1 << 31)
    assert result.reserved_bytes == 1 << 31
    await repo.reserve_execution_budget(db, budget.id, amount=repo.MAX_BYTES - (1 << 31))
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="EXCEEDED"):
        await repo.reserve_execution_budget(db, budget.id, amount=1)


async def test_empty_or_changed_profile_is_rejected(admission_db):
    db, kwargs, _, _, profile, settings = admission_db
    settings.download_admission_profiles = {}
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="PROFILE"):
        await repo.issue_processed_http_admission(db, **kwargs)
    settings.download_admission_profiles = {"isolated": profile}
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    profile["tool_digest"] = "d" * 64
    with pytest.raises(repo.DownloadExecutionAdmissionError):
        await repo.consume_execution_admission(db, admission.id, **claim(kwargs, admission))


@pytest.mark.parametrize("mutation", ["https", "query", "missing_path", "task_owner",
    "task_params", "raw", "multi_task", "no_snapshot"])
async def test_protocol_scope_and_original_task_fail_closed(admission_db, mutation):
    db, kwargs, row, task, profile, _ = admission_db
    if mutation in {"https", "query"}:
        bound = dict(row.normalized_request)
        request = dict(bound["requests"][0])
        request["links"] = ["https://source.example/file.tsv" if mutation == "https"
                            else "http://source.example/file.tsv?token=changed"]
        bound["requests"] = [request]
        row.normalized_request = bound
        # Re-sign isolated fixture facts to reach protocol check, not only digest mismatch.
        new_digest = hashlib.sha256(json.dumps(bound, sort_keys=True, ensure_ascii=False,
                                               default=str).encode()).hexdigest()
        row.parameters_hash = kwargs["request_digest"] = new_digest
        row.approval_snapshot = {**row.approval_snapshot,
            "proposal_digest": repo._digest(bound), "request_digest": new_digest}
    elif mutation == "missing_path":
        profile["allowed_destinations"][0].pop("path")
    elif mutation == "task_owner":
        task.user_id = uuid4()
    elif mutation == "task_params":
        task.parameters = {**task.parameters, "links": ["http://source.example/other"]}
    elif mutation == "raw":
        row.normalized_request = {**row.normalized_request, "input": {"mode": "raw"}}
    elif mutation == "multi_task":
        row.task_ids = [*row.task_ids, str(uuid4())]
    else:
        row.approval_snapshot = None
    with pytest.raises(repo.DownloadExecutionAdmissionError):
        await repo.issue_processed_http_admission(db, **kwargs)
    assert db.sync.scalars(select(DownloadExecutionBudgetModel)).all() == []


async def test_claim_missing_binding_and_duplicate_issue_are_rejected(admission_db):
    db, kwargs, *_ = admission_db
    admission = await repo.issue_processed_http_admission(db, **kwargs)
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="BINDING_MISSING"):
        await repo.consume_execution_admission(db, admission.id, task_id=kwargs["task_id"],
            owner_id=kwargs["owner_id"], request_digest=kwargs["request_digest"],
            caller_id=kwargs["caller_id"])
    with pytest.raises(repo.DownloadExecutionAdmissionError, match="ALREADY_ISSUED"):
        await repo.issue_processed_http_admission(db, **kwargs)
