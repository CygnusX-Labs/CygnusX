import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionReceiptNonceModel,
)
from cygnusx.infrastructure.database.repositories.download_execution_receipt import (
    consume_execution_receipt_nonce,
    execution_receipt_nonce_consumer,
    purge_expired_execution_receipt_nonces,
    verify_publishable_execution_receipt_in_transaction,
)
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionReceiptClaims,
    SignedExecutionReceipt,
)

pytestmark = pytest.mark.unit


class _AsyncSessionFacade:
    """Small async facade over SQLite for testing repository transaction semantics."""

    def __init__(self, engine) -> None:
        self.session = Session(engine)

    def get_bind(self):
        return self.session.get_bind()

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()


@pytest.fixture
def nonce_db():
    engine = create_engine("sqlite://")
    DownloadExecutionReceiptNonceModel.__table__.create(engine)
    yield engine
    engine.dispose()


async def test_nonce_is_atomic_across_sessions_and_expired_rows_can_be_purged(nonce_db):
    supervisor_id = "supervisor-acceptance"
    nonce = UUID(int=8101)
    expires_at = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
    first = _AsyncSessionFacade(nonce_db)
    assert await consume_execution_receipt_nonce(first, supervisor_id, nonce, expires_at)
    await first.commit()
    first.close()

    replay = _AsyncSessionFacade(nonce_db)
    assert not await execution_receipt_nonce_consumer(replay)(supervisor_id, nonce, expires_at)
    purged = await purge_expired_execution_receipt_nonces(
        replay, now=datetime.now(UTC) + timedelta(days=2)
    )
    assert purged == 1
    await replay.commit()
    replay.close()


async def test_nonce_consumption_rolls_back_with_callers_publication_transaction(nonce_db):
    supervisor_id = "supervisor-acceptance"
    nonce = UUID(int=8102)
    expires_at = int((datetime.now(UTC) + timedelta(days=1)).timestamp())
    rolled_back = _AsyncSessionFacade(nonce_db)
    assert await consume_execution_receipt_nonce(rolled_back, supervisor_id, nonce, expires_at)
    await rolled_back.rollback()
    rolled_back.close()

    retry = _AsyncSessionFacade(nonce_db)
    assert await consume_execution_receipt_nonce(retry, supervisor_id, nonce, expires_at)
    await retry.commit()
    retry.close()


async def test_expired_nonce_cannot_be_inserted(nonce_db):
    session = _AsyncSessionFacade(nonce_db)
    expired = int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())
    assert not await consume_execution_receipt_nonce(
        session, "supervisor-acceptance", UUID(int=8103), expired
    )
    session.close()


async def test_receipt_verifier_consumes_nonce_in_publication_transaction(nonce_db):
    task_id = UUID(int=8201)
    scope_ref = UUID(int=8202)
    nonce = UUID(int=8203)
    policy_revision = "policy-acceptance"
    manifest_hash = "c" * 64
    now = int(datetime.now(UTC).timestamp())
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    observation = ExecutionBoundaryObservation(
        task_id=task_id,
        scope_ref=scope_ref,
        execution_id=UUID(int=8204),
        execution_epoch=1,
        policy_revision=policy_revision,
        state="stopped",
        reason="completed",
        rx_admitted_bytes=1,
        rx_observed_bytes=1,
        rx_dropped_bytes=0,
        rx_limit_bytes=8,
        disk_peak_allocated_bytes=1,
        disk_limit_bytes=8,
        inode_peak_used=1,
        inode_limit=4,
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
        supervisor_id="supervisor-acceptance",
        task_id=task_id,
        attempt_id=UUID(int=8205),
        execution_id=UUID(int=8204),
        scope_ref=scope_ref,
        execution_epoch=1,
        policy_revision=policy_revision,
        environment_id="acceptance-linux-xfs-v1",
        binary_sha256="d" * 64,
        nonce=nonce,
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
    expected = {
        "supervisor_public_key": public_key,
        "expected_supervisor_id": "supervisor-acceptance",
        "expected_task_id": task_id,
        "expected_attempt_id": UUID(int=8205),
        "expected_execution_id": UUID(int=8204),
        "expected_scope_ref": scope_ref,
        "expected_execution_epoch": 1,
        "expected_policy_revision": policy_revision,
        "expected_environment_id": "acceptance-linux-xfs-v1",
        "expected_binary_sha256": "d" * 64,
        "expected_artifact_manifest_sha256": manifest_hash,
        "now_epoch_seconds": now,
    }

    first = _AsyncSessionFacade(nonce_db)
    await verify_publishable_execution_receipt_in_transaction(first, receipt, **expected)
    await first.commit()
    first.close()

    replay = _AsyncSessionFacade(nonce_db)
    with pytest.raises(ValueError, match="DOWNLOAD_RECEIPT_REJECTED"):
        await verify_publishable_execution_receipt_in_transaction(replay, receipt, **expected)
    await replay.rollback()
    replay.close()
