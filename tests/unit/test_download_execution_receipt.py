import base64
import json
from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryObservation,
    ExecutionReceiptClaims,
    SignedExecutionReceipt,
    artifact_manifest_sha256,
    decode_supervisor_public_key,
    require_quiescent,
    verify_execution_receipt,
    verify_publishable_execution_receipt,
)

pytestmark = pytest.mark.unit
TASK = UUID(int=101)
SCOPE = UUID(int=202)
NONCE = UUID(int=303)
ATTEMPT = UUID(int=404)
EXECUTION = UUID(int=505)
NOW = 1_800_000_000
POLICY = "sha256:trusted-http-policy"
ENVIRONMENT = "isolated-linux-xfs-v1"
BINARY_SHA256 = "b" * 64
ARTIFACT_MANIFEST = "a" * 64
SUPERVISOR_ID = "acceptance-supervisor-1"


def _observation(**changes: object) -> ExecutionBoundaryObservation:
    data: dict[str, object] = {
        "task_id": TASK,
        "scope_ref": SCOPE,
        "execution_id": EXECUTION,
        "execution_epoch": 7,
        "policy_revision": POLICY,
        "state": "stopped",
        "reason": "completed",
        "rx_admitted_bytes": 20,
        "rx_observed_bytes": 20,
        "rx_dropped_bytes": 0,
        "rx_limit_bytes": 100,
        "disk_peak_allocated_bytes": 20,
        "disk_limit_bytes": 100,
        "inode_peak_used": 2,
        "inode_limit": 10,
        "started_at": NOW - 10,
        "stopped_at": NOW - 1,
        "live_processes": 0,
        "cgroup_populated": False,
        "egress_revoked": True,
        "quota_enforced": True,
        "cleanup_complete": True,
        "returncode": 0,
    }
    data.update(changes)
    return ExecutionBoundaryObservation.model_validate(data)


def _receipt(
    private_key: Ed25519PrivateKey,
    *,
    task_id: UUID = TASK,
    scope_ref: UUID = SCOPE,
    execution_epoch: int = 7,
    policy_revision: str = POLICY,
    issued_at: int = NOW - 5,
    expires_at: int = NOW + 30,
    nonce: UUID = NONCE,
    artifact_manifest_sha256: str = ARTIFACT_MANIFEST,
    observation: ExecutionBoundaryObservation | None = None,
) -> SignedExecutionReceipt:
    claims = ExecutionReceiptClaims(
        supervisor_id="acceptance-supervisor-1",
        task_id=task_id,
        attempt_id=ATTEMPT,
        execution_id=EXECUTION,
        scope_ref=scope_ref,
        execution_epoch=execution_epoch,
        policy_revision=policy_revision,
        environment_id=ENVIRONMENT,
        binary_sha256=BINARY_SHA256,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
        artifact_manifest_sha256=artifact_manifest_sha256,
        observation=observation or _observation(),
    )
    payload = json.dumps(
        claims.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    signature = base64.urlsafe_b64encode(private_key.sign(payload)).decode().rstrip("=")
    return SignedExecutionReceipt(claims=claims, signature=signature)


def _public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def test_artifact_manifest_digest_is_order_independent_and_rejects_unsafe_entries() -> None:
    first = ("reads/a.fastq", "a" * 64, 12)
    second = ("reads/b.fastq", "b" * 64, 24)
    assert artifact_manifest_sha256([first, second]) == artifact_manifest_sha256(
        [second, first]
    )
    with pytest.raises(ValueError, match="DOWNLOAD_ARTIFACT_MANIFEST_INVALID"):
        artifact_manifest_sha256([("../secret", "a" * 64, 12)])
    with pytest.raises(ValueError, match="DOWNLOAD_ARTIFACT_MANIFEST_INVALID"):
        artifact_manifest_sha256([("file.fastq", "bad", 12)])


def test_supervisor_public_key_decoder_requires_raw_ed25519_key() -> None:
    private_key = Ed25519PrivateKey.generate()
    encoded = base64.urlsafe_b64encode(_public_key(private_key)).decode().rstrip("=")
    assert decode_supervisor_public_key(encoded) == _public_key(private_key)
    with pytest.raises(ValueError, match="DOWNLOAD_SUPERVISOR_KEY_INVALID"):
        decode_supervisor_public_key("bad")


def _nonce_consumer() -> tuple[
    set[tuple[str, UUID]], Callable[[str, UUID, int], Awaitable[bool]]
]:
    consumed: set[tuple[str, UUID]] = set()

    async def consume(supervisor_id: str, nonce: UUID, expires_at: int) -> bool:
        del expires_at
        key = (supervisor_id, nonce)
        if key in consumed:
            return False
        consumed.add(key)
        return True

    return consumed, consume


async def test_signed_receipt_binds_scope_and_consumes_nonce_before_use() -> None:
    private_key = Ed25519PrivateKey.generate()
    receipt = _receipt(private_key)
    consumed, consume = _nonce_consumer()

    observation = await verify_execution_receipt(
        receipt,
        supervisor_public_key=_public_key(private_key),
        expected_supervisor_id=SUPERVISOR_ID,
        expected_task_id=TASK,
        expected_attempt_id=ATTEMPT,
        expected_execution_id=EXECUTION,
        expected_scope_ref=SCOPE,
        expected_execution_epoch=7,
        expected_policy_revision=POLICY,
        expected_environment_id=ENVIRONMENT,
        expected_binary_sha256=BINARY_SHA256,
        expected_artifact_manifest_sha256=ARTIFACT_MANIFEST,
        consume_nonce=consume,
        now_epoch_seconds=NOW,
    )

    require_quiescent(observation, TASK, SCOPE)
    assert consumed == {("acceptance-supervisor-1", NONCE)}


@pytest.mark.parametrize(
    "expected",
    [
        {"expected_task_id": UUID(int=404)},
        {"expected_attempt_id": UUID(int=405)},
        {"expected_execution_id": UUID(int=406)},
        {"expected_scope_ref": UUID(int=407)},
        {"expected_execution_epoch": 8},
        {"expected_policy_revision": "sha256:other-policy"},
        {"expected_environment_id": "other-environment"},
        {"expected_binary_sha256": "c" * 64},
        {"expected_supervisor_id": "other-supervisor"},
    ],
)
async def test_signed_receipt_rejects_identity_or_policy_mismatch(expected: dict[str, object]) -> None:
    private_key = Ed25519PrivateKey.generate()
    receipt = _receipt(private_key)
    consumed, consume = _nonce_consumer()
    arguments: dict[str, object] = {
        "expected_task_id": TASK,
        "expected_attempt_id": ATTEMPT,
        "expected_execution_id": EXECUTION,
        "expected_supervisor_id": SUPERVISOR_ID,
        "expected_scope_ref": SCOPE,
        "expected_execution_epoch": 7,
        "expected_policy_revision": POLICY,
        "expected_environment_id": ENVIRONMENT,
        "expected_binary_sha256": BINARY_SHA256,
        "expected_artifact_manifest_sha256": ARTIFACT_MANIFEST,
    }
    arguments.update(expected)

    with pytest.raises(ValueError, match="DOWNLOAD_RECEIPT_REJECTED"):
        await verify_execution_receipt(
            receipt,
            supervisor_public_key=_public_key(private_key),
            consume_nonce=consume,
            now_epoch_seconds=NOW,
            **arguments,
        )
    assert not consumed


async def test_signed_receipt_rejects_tampering_expiry_and_replay() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = _public_key(private_key)
    receipt = _receipt(private_key)
    consumed, consume = _nonce_consumer()
    bad_signature = ("A" if receipt.signature[0] != "A" else "B") + receipt.signature[1:]
    tampered = receipt.model_copy(update={"signature": bad_signature})

    with pytest.raises(ValueError, match="DOWNLOAD_RECEIPT_REJECTED"):
        await verify_execution_receipt(
            tampered,
            supervisor_public_key=public_key,
            expected_supervisor_id=SUPERVISOR_ID,
            expected_task_id=TASK,
            expected_attempt_id=ATTEMPT,
            expected_execution_id=EXECUTION,
            expected_scope_ref=SCOPE,
            expected_execution_epoch=7,
            expected_policy_revision=POLICY,
            expected_environment_id=ENVIRONMENT,
            expected_binary_sha256=BINARY_SHA256,
            expected_artifact_manifest_sha256=ARTIFACT_MANIFEST,
            consume_nonce=consume,
            now_epoch_seconds=NOW,
        )
    expired = _receipt(private_key, issued_at=NOW - 100, expires_at=NOW - 1)
    with pytest.raises(ValueError, match="DOWNLOAD_RECEIPT_REJECTED"):
        await verify_execution_receipt(
            expired,
            supervisor_public_key=public_key,
            expected_supervisor_id=SUPERVISOR_ID,
            expected_task_id=TASK,
            expected_attempt_id=ATTEMPT,
            expected_execution_id=EXECUTION,
            expected_scope_ref=SCOPE,
            expected_execution_epoch=7,
            expected_policy_revision=POLICY,
            expected_environment_id=ENVIRONMENT,
            expected_binary_sha256=BINARY_SHA256,
            expected_artifact_manifest_sha256=ARTIFACT_MANIFEST,
            consume_nonce=consume,
            now_epoch_seconds=NOW,
        )

    valid = _receipt(private_key)
    await verify_execution_receipt(
        valid,
        supervisor_public_key=public_key,
        expected_supervisor_id=SUPERVISOR_ID,
        expected_task_id=TASK,
        expected_attempt_id=ATTEMPT,
        expected_execution_id=EXECUTION,
        expected_scope_ref=SCOPE,
        expected_execution_epoch=7,
        expected_policy_revision=POLICY,
        expected_environment_id=ENVIRONMENT,
        expected_binary_sha256=BINARY_SHA256,
        expected_artifact_manifest_sha256=ARTIFACT_MANIFEST,
        consume_nonce=consume,
        now_epoch_seconds=NOW,
    )
    with pytest.raises(ValueError, match="DOWNLOAD_RECEIPT_REJECTED"):
        await verify_execution_receipt(
            valid,
            supervisor_public_key=public_key,
            expected_supervisor_id=SUPERVISOR_ID,
            expected_task_id=TASK,
            expected_attempt_id=ATTEMPT,
            expected_execution_id=EXECUTION,
            expected_scope_ref=SCOPE,
            expected_execution_epoch=7,
            expected_policy_revision=POLICY,
            expected_environment_id=ENVIRONMENT,
            expected_binary_sha256=BINARY_SHA256,
            expected_artifact_manifest_sha256=ARTIFACT_MANIFEST,
            consume_nonce=consume,
            now_epoch_seconds=NOW,
        )


async def test_signed_receipt_rejects_observation_bound_to_another_scope() -> None:
    private_key = Ed25519PrivateKey.generate()
    receipt = _receipt(
        private_key,
        observation=_observation(scope_ref=UUID(int=999)),
    )
    consumed, consume = _nonce_consumer()

    with pytest.raises(ValueError, match="DOWNLOAD_RECEIPT_REJECTED"):
        await verify_execution_receipt(
            receipt,
            supervisor_public_key=_public_key(private_key),
            expected_supervisor_id=SUPERVISOR_ID,
            expected_task_id=TASK,
            expected_attempt_id=ATTEMPT,
            expected_execution_id=EXECUTION,
            expected_scope_ref=SCOPE,
            expected_execution_epoch=7,
            expected_policy_revision=POLICY,
            expected_environment_id=ENVIRONMENT,
            expected_binary_sha256=BINARY_SHA256,
            expected_artifact_manifest_sha256=ARTIFACT_MANIFEST,
            consume_nonce=consume,
            now_epoch_seconds=NOW,
        )


async def test_publishable_receipt_binds_manifest_and_successful_quiescent_execution() -> None:
    private_key = Ed25519PrivateKey.generate()
    receipt = _receipt(private_key)
    consumed, consume = _nonce_consumer()

    observation = await verify_publishable_execution_receipt(
        receipt,
        supervisor_public_key=_public_key(private_key),
        expected_supervisor_id=SUPERVISOR_ID,
        expected_task_id=TASK,
        expected_attempt_id=ATTEMPT,
        expected_execution_id=EXECUTION,
        expected_scope_ref=SCOPE,
        expected_execution_epoch=7,
        expected_policy_revision=POLICY,
        expected_environment_id=ENVIRONMENT,
        expected_binary_sha256=BINARY_SHA256,
        expected_artifact_manifest_sha256=ARTIFACT_MANIFEST,
        consume_nonce=consume,
        now_epoch_seconds=NOW,
    )
    assert observation.returncode == 0
    assert consumed == {("acceptance-supervisor-1", NONCE)}


async def test_publishable_receipt_rejects_other_manifest_and_failed_execution() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = _public_key(private_key)
    consumed, consume = _nonce_consumer()
    arguments = {
        "supervisor_public_key": public_key,
        "expected_supervisor_id": SUPERVISOR_ID,
        "expected_task_id": TASK,
        "expected_attempt_id": ATTEMPT,
        "expected_execution_id": EXECUTION,
        "expected_scope_ref": SCOPE,
        "expected_execution_epoch": 7,
        "expected_policy_revision": POLICY,
        "expected_environment_id": ENVIRONMENT,
        "expected_binary_sha256": BINARY_SHA256,
        "expected_artifact_manifest_sha256": "b" * 64,
        "consume_nonce": consume,
        "now_epoch_seconds": NOW,
    }
    with pytest.raises(ValueError, match="DOWNLOAD_RECEIPT_REJECTED"):
        await verify_publishable_execution_receipt(_receipt(private_key), **arguments)
    assert not consumed

    failed = _receipt(private_key, observation=_observation(reason="failed", returncode=1))
    arguments["expected_artifact_manifest_sha256"] = ARTIFACT_MANIFEST
    with pytest.raises(ValueError, match="DOWNLOAD_PUBLICATION_RECEIPT_REJECTED"):
        await verify_publishable_execution_receipt(failed, **arguments)
    assert consumed == {("acceptance-supervisor-1", NONCE)}
