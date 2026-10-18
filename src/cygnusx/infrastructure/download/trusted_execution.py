"""S3-E1 interface and G3 receipt contract; no OS runtime implementation.

Only trusted server code may construct requests after existing authorization. The
supervisor must independently bind these references to persisted Task/policy state.
Neither these types nor supplied evidence certify an execution environment.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import PurePosixPath
from typing import Literal, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionBoundaryRequest(BaseModel):
    """Server references, never arbitrary argv, environment, mounts or credentials.

    task_id is the existing Task; admission_ref resolves identity, approval, tool
    digest and HTTP destination policy. budget_ref resolves durable shared quota.
    The supervisor chooses paths/env and creates the scope BEFORE starting a CLI.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: UUID
    owner_id: UUID
    attempt_id: UUID
    execution_id: UUID
    execution_epoch: int = Field(gt=0)
    admission_ref: UUID
    budget_ref: UUID
    protocol: Literal["http"] = "http"


class ExecutionBoundaryObservation(BaseModel):
    """Supervisor facts; raw wire data remains untrusted until provenance checked.

    rx_admitted_bytes counts ingress bytes synchronously admitted to the Task at
    the enforced boundary, including retries/headers. It is not ISP billing RX.
    Disk bytes are allocated blocks, not final file lengths. No FileRecord is
    manufactured here: the existing registry hashes stable files after quiescence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: UUID
    scope_ref: UUID
    execution_id: UUID
    execution_epoch: int = Field(gt=0)
    policy_revision: str = Field(min_length=1, max_length=128)
    state: Literal["running", "stopped", "unknown"]
    reason: Literal[
        "running",
        "completed",
        "cancelled",
        "network_limit",
        "disk_limit",
        "worker_lost",
        "deadline",
        "policy_denied",
        "failed",
        "unknown",
    ]
    rx_admitted_bytes: int = Field(ge=0)
    rx_observed_bytes: int = Field(ge=0)
    rx_dropped_bytes: int = Field(ge=0)
    rx_limit_bytes: int = Field(gt=0)
    disk_peak_allocated_bytes: int = Field(ge=0)
    disk_limit_bytes: int = Field(gt=0)
    inode_peak_used: int = Field(ge=0)
    inode_limit: int = Field(gt=0)
    started_at: int = Field(ge=0)
    stopped_at: int = Field(ge=0)
    live_processes: int = Field(ge=0)
    cgroup_populated: bool
    egress_revoked: bool
    quota_enforced: bool
    cleanup_complete: bool
    returncode: int | None

    @model_validator(mode="after")
    def validate_observation(self) -> ExecutionBoundaryObservation:
        if (
            self.rx_observed_bytes != self.rx_admitted_bytes + self.rx_dropped_bytes
            or self.stopped_at < self.started_at
        ):
            raise ValueError("DOWNLOAD_RX_COUNTERS_INCONSISTENT")
        return self


class ExecutionReceiptClaims(BaseModel):
    """Supervisor-signed identity, observation, and immutable output manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    supervisor_id: str = Field(min_length=1, max_length=128)
    task_id: UUID
    attempt_id: UUID
    execution_id: UUID
    scope_ref: UUID
    execution_epoch: int = Field(gt=0)
    policy_revision: str = Field(min_length=1, max_length=128)
    environment_id: str = Field(min_length=1, max_length=128)
    binary_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    nonce: UUID
    issued_at: int = Field(ge=0)
    expires_at: int = Field(gt=0)
    artifact_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observation: ExecutionBoundaryObservation


class SignedExecutionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    claims: ExecutionReceiptClaims
    signature: str = Field(min_length=80, max_length=100)


class ExecutionPublicationContext(BaseModel):
    """Server-owned task metadata needed to verify a final publication receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scope_ref: UUID
    attempt_id: UUID
    execution_id: UUID
    execution_epoch: int = Field(gt=0)
    policy_revision: str = Field(min_length=1, max_length=128)
    environment_id: str = Field(min_length=1, max_length=128)
    binary_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt: SignedExecutionReceipt


def artifact_manifest_sha256(entries: Sequence[tuple[str, str, int]]) -> str:
    """Hash sorted relative-path/SHA-256/size tuples using canonical JSON."""
    if not entries:
        raise ValueError("DOWNLOAD_ARTIFACT_MANIFEST_EMPTY")
    normalized: list[dict[str, str | int]] = []
    seen_paths: set[str] = set()
    for relative_path, sha256, size in entries:
        path = PurePosixPath(relative_path)
        if (
            not relative_path
            or path.is_absolute()
            or path.as_posix() != relative_path
            or ".." in path.parts
            or "\\" in relative_path
            or relative_path in seen_paths
            or not re.fullmatch(r"[a-f0-9]{64}", sha256)
            or size <= 0
        ):
            raise ValueError("DOWNLOAD_ARTIFACT_MANIFEST_INVALID")
        seen_paths.add(relative_path)
        normalized.append({"path": relative_path, "sha256": sha256, "size": size})
    normalized.sort(key=lambda entry: str(entry["path"]))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def decode_supervisor_public_key(encoded_key: str) -> bytes:
    """Decode a pinned base64url Ed25519 public key and reject malformed values."""
    try:
        key = base64.b64decode(
            encoded_key + "=" * (-len(encoded_key) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("DOWNLOAD_SUPERVISOR_KEY_INVALID") from exc
    if len(key) != 32:
        raise ValueError("DOWNLOAD_SUPERVISOR_KEY_INVALID")
    return key


async def verify_execution_receipt(
    receipt: SignedExecutionReceipt,
    *,
    supervisor_public_key: bytes,
    expected_supervisor_id: str,
    expected_task_id: UUID,
    expected_attempt_id: UUID,
    expected_execution_id: UUID,
    expected_scope_ref: UUID,
    expected_execution_epoch: int,
    expected_policy_revision: str,
    expected_environment_id: str,
    expected_binary_sha256: str,
    expected_artifact_manifest_sha256: str,
    consume_nonce: Callable[[str, UUID, int], Awaitable[bool]],
    now_epoch_seconds: int | None = None,
    max_ttl_seconds: int = 60,
) -> ExecutionBoundaryObservation:
    """Authenticate a bounded receipt and atomically consume its replay nonce.

    ``consume_nonce`` must use durable atomic insert-if-absent semantics in the
    trusted service. This only validates claims; it cannot prove the OS source
    of any claim unless the signing key belongs to a real isolated Supervisor.
    """
    claims = receipt.claims
    now = int(time.time()) if now_epoch_seconds is None else now_epoch_seconds
    if (
        claims.observation.rx_admitted_bytes > claims.observation.rx_limit_bytes
        or claims.observation.disk_peak_allocated_bytes > claims.observation.disk_limit_bytes
        or claims.observation.inode_peak_used > claims.observation.inode_limit
        or claims.observation.cgroup_populated
        or not claims.observation.egress_revoked
        or not claims.observation.quota_enforced
        or not claims.observation.cleanup_complete
        or claims.observation.live_processes != 0
        or (
            claims.task_id != expected_task_id
            or claims.attempt_id != expected_attempt_id
            or claims.execution_id != expected_execution_id
            or claims.supervisor_id != expected_supervisor_id
            or claims.scope_ref != expected_scope_ref
            or claims.execution_epoch != expected_execution_epoch
            or claims.policy_revision != expected_policy_revision
            or claims.environment_id != expected_environment_id
            or claims.binary_sha256 != expected_binary_sha256
            or claims.artifact_manifest_sha256 != expected_artifact_manifest_sha256
            or claims.observation.task_id != claims.task_id
            or claims.observation.execution_id != claims.execution_id
            or claims.observation.execution_epoch != claims.execution_epoch
            or claims.observation.scope_ref != claims.scope_ref
            or claims.observation.policy_revision != claims.policy_revision
            or claims.expires_at <= claims.issued_at
            or claims.expires_at - claims.issued_at > max_ttl_seconds
            or claims.issued_at > now
            or claims.expires_at <= now
        )
    ):
        raise ValueError("DOWNLOAD_RECEIPT_REJECTED")

    signed_payload = json.dumps(
        claims.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    try:
        signature = base64.b64decode(
            receipt.signature + "=" * (-len(receipt.signature) % 4),
            altchars=b"-_",
            validate=True,
        )
        Ed25519PublicKey.from_public_bytes(supervisor_public_key).verify(signature, signed_payload)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("DOWNLOAD_RECEIPT_REJECTED") from exc

    if not await consume_nonce(claims.supervisor_id, claims.nonce, claims.expires_at):
        raise ValueError("DOWNLOAD_RECEIPT_REJECTED")
    return claims.observation


async def verify_publishable_execution_receipt(
    receipt: SignedExecutionReceipt,
    *,
    supervisor_public_key: bytes,
    expected_supervisor_id: str,
    expected_task_id: UUID,
    expected_attempt_id: UUID,
    expected_execution_id: UUID,
    expected_scope_ref: UUID,
    expected_execution_epoch: int,
    expected_policy_revision: str,
    expected_environment_id: str,
    expected_binary_sha256: str,
    expected_artifact_manifest_sha256: str,
    consume_nonce: Callable[[str, UUID, int], Awaitable[bool]],
    now_epoch_seconds: int | None = None,
    max_ttl_seconds: int = 60,
) -> ExecutionBoundaryObservation:
    """Verify a final receipt and reject it unless it permits artifact publication."""
    observation = await verify_execution_receipt(
        receipt,
        supervisor_public_key=supervisor_public_key,
        expected_supervisor_id=expected_supervisor_id,
        expected_task_id=expected_task_id,
        expected_attempt_id=expected_attempt_id,
        expected_execution_id=expected_execution_id,
        expected_scope_ref=expected_scope_ref,
        expected_execution_epoch=expected_execution_epoch,
        expected_policy_revision=expected_policy_revision,
        expected_environment_id=expected_environment_id,
        expected_binary_sha256=expected_binary_sha256,
        expected_artifact_manifest_sha256=expected_artifact_manifest_sha256,
        consume_nonce=consume_nonce,
        now_epoch_seconds=now_epoch_seconds,
        max_ttl_seconds=max_ttl_seconds,
    )
    require_publishable_execution(
        observation,
        task_id=expected_task_id,
        scope_ref=expected_scope_ref,
        artifact_manifest_sha256=expected_artifact_manifest_sha256,
    )
    return observation


def require_publishable_execution(
    observation: ExecutionBoundaryObservation,
    *,
    task_id: UUID,
    scope_ref: UUID,
    artifact_manifest_sha256: str,
) -> None:
    """Reject publication unless a stopped, successful scope binds this artifact.

    This is a necessary policy check after receipt authentication, not an adapter,
    durable nonce store, or transaction with FileRegistry.
    """
    require_quiescent(observation, task_id, scope_ref)
    if (
        observation.reason != "completed"
        or observation.returncode != 0
        or not re.fullmatch(r"[a-f0-9]{64}", artifact_manifest_sha256)
    ):
        raise ValueError("DOWNLOAD_PUBLICATION_RECEIPT_REJECTED")


class TrustedExecutionAdapter(Protocol):
    """Future authenticated OS-supervisor client, NOT a second task scheduler.

    Must fail closed on unavailable/expired/mismatched authorization. start is
    idempotent for the existing Task and never resets its durable budget. It must
    resolve the original download argv server-side and execute the existing CLI.
    No shell, Docker socket or Worker credentials enter the child scope.
    """

    async def start(self, request: ExecutionBoundaryRequest) -> UUID:
        """Atomically reserve restricted scope/lease/quota then spawn; no fallback."""
        ...

    async def observe(self, task_id: UUID, scope_ref: UUID) -> ExecutionBoundaryObservation:
        """Read authenticated counters/identity; transport failure means unknown."""
        ...

    async def renew(self, task_id: UUID, scope_ref: UUID) -> None:
        """Refresh bounded Worker lease; supervisor revokes/kills on expiry."""
        ...

    async def stop(self, task_id: UUID, scope_ref: UUID) -> ExecutionBoundaryObservation:
        """Idempotently revoke egress, kill all descendants and await empty scope.

        Do not delete files or release quota until original reconciliation finishes.
        Worker loss must trigger this behavior without a call from the dead Worker.
        """
        ...

    async def evidence(
        self, request: ExecutionBoundaryRequest, scope_ref: UUID
    ) -> ExecutionPublicationContext:
        """Fetch the signed publication context after execution has stopped."""
        ...


def require_quiescent(
    observation: ExecutionBoundaryObservation, task_id: UUID, scope_ref: UUID
) -> None:
    """Necessary reconciliation precondition, never proof of runtime authenticity."""
    if (
        observation.task_id != task_id
        or observation.scope_ref != scope_ref
        or observation.state != "stopped"
        or observation.live_processes != 0
        or not observation.egress_revoked
        or observation.reason in {"running", "unknown"}
        or observation.rx_admitted_bytes > observation.rx_limit_bytes
        or observation.disk_peak_allocated_bytes > observation.disk_limit_bytes
        or observation.inode_peak_used > observation.inode_limit
        or observation.cgroup_populated
        or not observation.quota_enforced
        or not observation.cleanup_complete
    ):
        raise ValueError("DOWNLOAD_SCOPE_RECONCILIATION_REQUIRED")
