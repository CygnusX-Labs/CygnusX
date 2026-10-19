"""Trusted admission facts, fencing and budgets; transaction ownership stays with caller."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.core.config import get_settings
from cygnusx.infrastructure.database.models.dataset import DatasetIngestionModel
from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionAdmissionModel,
    DownloadExecutionBudgetModel,
)
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.infrastructure.download.reliability import intent_digest
from cygnusx.infrastructure.download.trusted_execution import deterministic_execution_id

MAX_BYTES = (1 << 63) - 1


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()


class DownloadExecutionAdmissionError(RuntimeError):
    """A caller cannot use the requested admission or budget."""


def _positive(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_BYTES


def _profile(environment_id: str) -> dict[str, Any]:
    profile = get_settings().download_admission_profiles.get(environment_id)
    if not profile or any(not profile.get(key) for key in (
        "caller_kind", "caller_id", "environment_id", "tool_digest", "policy_revision",
        "allowed_destinations", "disk_block_limit_bytes", "disk_inodes_limit",
    )):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_PROFILE_MISSING")
    tool_digest = profile["tool_digest"]
    if (
        profile["environment_id"] != environment_id
        or profile["caller_kind"] not in {"human", "agent", "worker"}
        or not isinstance(tool_digest, str) or len(tool_digest) != 64
        or any(c not in "0123456789abcdef" for c in tool_digest)
        or not _positive(profile["disk_block_limit_bytes"])
        or not _positive(profile["disk_inodes_limit"])
    ):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_PROFILE_INVALID")
    destinations = profile["allowed_destinations"]
    if not isinstance(destinations, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("host"), str)
        or not item["host"] or not isinstance(item.get("port"), int)
        or isinstance(item["port"], bool) or not 1 <= item["port"] <= 65535
        or not isinstance(item.get("path"), str) or not item["path"].startswith("/")
        or "?" in item["path"] or "#" in item["path"]
        for item in destinations
    ):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_DESTINATION_INVALID")
    return profile


def get_execution_admission_profile(environment_id: str) -> dict[str, Any]:
    """Return a validated server-owned profile for a trusted execution adapter."""
    return _profile(environment_id)


async def _facts(
    session: AsyncSession, *, ingestion_id: UUID, task_id: UUID, owner_id: UUID,
    project_id: UUID, confirmation_id: str, request_digest: str, limit_bytes: int,
    expires_at: datetime, now: datetime, allowed_destinations: list[dict[str, Any]],
    task_statuses: tuple[str, ...] = ("queued",),
) -> str:
    """Re-read original rows, never accept a caller's assertion of approval."""
    ingestion = (await session.execute(select(DatasetIngestionModel).where(
        DatasetIngestionModel.id == ingestion_id
    ).with_for_update())).scalar_one_or_none()
    task = (await session.execute(select(TaskModel).where(
        TaskModel.id == task_id
    ).with_for_update())).scalar_one_or_none()
    user = (await session.execute(select(UserModel).where(
        UserModel.id == owner_id
    ).with_for_update())).scalar_one_or_none()
    project = (await session.execute(select(ProjectModel).where(
        ProjectModel.id == project_id
    ).with_for_update())).scalar_one_or_none()
    if (ingestion is None or task is None or user is None or project is None
        or user.status != "active" or project.user_id != owner_id
        or project.status not in {None, "active"}
        or (user.role != "admin" and {"files", "downloads"}.intersection(
            user.disabled_modules or []))
        or ingestion.user_id != owner_id or ingestion.project_id != project_id
        or ingestion.state not in {"SUBMITTING", "QUEUED"}
        or ingestion.task_ids != [str(task_id)]
        or ingestion.confirmation_id != confirmation_id
        or ingestion.parameters_hash != request_digest
        or task.user_id != owner_id or task.status not in task_statuses
        or task.flow_id != "ebi_download"):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_FACTS_REJECTED")
    bound = ingestion.normalized_request
    snapshot = ingestion.approval_snapshot or {}
    requests = bound.get("requests", [])
    if (bound.get("owner_id") != str(owner_id)
        or bound.get("project_id") != str(project_id)
        or bound.get("proposal_id") != str(ingestion_id)
        or bound.get("input", {}).get("mode") != "processed"
        or len(requests) != 1 or bound.get("max_bytes") != limit_bytes):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_PROPOSAL_REJECTED")
    # Same canonical algorithm as the original Confirmation service.
    confirmation_hash = hashlib.sha256(json.dumps(
        bound, sort_keys=True, ensure_ascii=False, default=str
    ).encode()).hexdigest()
    source_digest = _digest(bound.get("candidate", {}))
    expected = {
        "approval_id": confirmation_id, "approval_version": 1,
        "actor_id": str(owner_id), "owner_id": str(owner_id),
        "project_id": str(project_id), "ingestion_id": str(ingestion_id),
        "proposal_digest": _digest(bound), "request_digest": request_digest,
        "source_digest": source_digest, "scope": "dataset.execute_import",
        "method": "processed_http", "max_budget": limit_bytes,
        "status": "APPROVED", "revoked_at": None, "nonce_status": "CONSUMED",
        "nonce_hash": hashlib.sha256(confirmation_id.encode()).hexdigest(),
    }
    try:
        approval_expiry = _utc(datetime.fromisoformat(snapshot["expires_at"]))
        approved_at = _utc(datetime.fromisoformat(snapshot["approved_at"]))
        consumed_at = _utc(datetime.fromisoformat(snapshot["consumed_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise DownloadExecutionAdmissionError("DOWNLOAD_APPROVAL_MISSING") from exc
    identity = snapshot.get("auth_session_or_jti_hash")
    if (any(snapshot.get(key) != value for key, value in expected.items())
        or confirmation_hash != request_digest or approval_expiry <= now
        or _utc(expires_at) > approval_expiry or approved_at > consumed_at or consumed_at > now
        or not isinstance(identity, str) or len(identity) != 64
        or any(c not in "0123456789abcdef" for c in identity)):
        raise DownloadExecutionAdmissionError("DOWNLOAD_APPROVAL_REJECTED")
    try:
        req = DownloadRequest.model_validate(requests[0])
    except ValidationError:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_REQUEST_INVALID") from None
    if req.source != "direct_link" or not req.links:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_HTTP_ONLY")
    for link in req.links:
        url = urlsplit(link)
        if (url.scheme != "http" or not url.hostname
            or url.username or url.password or url.fragment or url.query
            or not any(
                destination.get("host") == url.hostname
                and destination.get("port") == (url.port or (443 if url.scheme == "https" else 80))
                and destination.get("path") == url.path
                for destination in allowed_destinations
            )):
            raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_DESTINATION_REJECTED")
    parameters = {
        "source": "direct_link", "links": req.links,
        "download_threads": req.download_threads, "overwrite_policy": req.overwrite_policy,
        "recursive": req.recursive, "target_directory": req.target_directory,
        "project_id": str(project_id),
    }
    actual = task.parameters or {}
    if (any(actual.get(key) != value for key, value in parameters.items())
        or actual.get("_download_intent") != intent_digest(
            str(owner_id), str(project_id), parameters
        )
        or actual.get("_download_reliability", {}).get("version") != 1):
        raise DownloadExecutionAdmissionError("DOWNLOAD_TASK_BINDING_REJECTED")
    return source_digest


async def issue_processed_http_admission(
    session: AsyncSession, *, ingestion_id: UUID, task_id: UUID, owner_id: UUID,
    project_id: UUID, confirmation_id: str, request_digest: str, limit_bytes: int,
    policy_revision: str, environment_id: str, caller_id: str,
    allowed_destinations: list[dict[str, Any]], expires_at: datetime,
) -> DownloadExecutionAdmissionModel:
    """Issue one full reservation after DB and fixed server-profile verification."""
    now = datetime.now(UTC)
    if not _positive(limit_bytes) or _utc(expires_at) <= now:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_INVALID_BUDGET")
    profile = _profile(environment_id)
    if (caller_id != profile["caller_id"]
        or policy_revision != profile["policy_revision"]
        or environment_id != profile["environment_id"]
        or allowed_destinations != profile["allowed_destinations"]):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_PROFILE_MISMATCH")
    source_digest = await _facts(
        session, ingestion_id=ingestion_id, task_id=task_id, owner_id=owner_id,
        project_id=project_id, confirmation_id=confirmation_id, request_digest=request_digest,
        limit_bytes=limit_bytes, expires_at=expires_at, now=now,
        allowed_destinations=allowed_destinations,
    )
    existing = (await session.execute(select(DownloadExecutionAdmissionModel).where(
        (DownloadExecutionAdmissionModel.task_id == task_id)
        | (DownloadExecutionAdmissionModel.ingestion_id == ingestion_id)
    ))).scalar_one_or_none()
    if existing is not None:
        # Unique Task/ingestion is a permanent replay fence, including revoked attempts.
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_ALREADY_ISSUED")
    budget = DownloadExecutionBudgetModel(
        id=uuid4(), owner_id=owner_id, project_id=project_id, limit_bytes=limit_bytes,
        reserved_bytes=limit_bytes, admitted_bytes=None, status="ACTIVE",
        disk_block_limit_bytes=profile["disk_block_limit_bytes"],
        disk_inodes_limit=profile["disk_inodes_limit"],
        policy_revision=policy_revision, expires_at=expires_at,
    )
    admission = DownloadExecutionAdmissionModel(
        id=uuid4(), budget_id=budget.id, ingestion_id=ingestion_id, task_id=task_id,
        owner_id=owner_id, project_id=project_id, confirmation_id=confirmation_id,
        request_digest=request_digest, source="direct_link", protocol="http",
        policy_revision=policy_revision, environment_id=environment_id, caller_id=caller_id,
        caller_kind=profile["caller_kind"], tool_digest=profile["tool_digest"],
        source_digest=source_digest, attempt_id=uuid4(), reserved_bytes=limit_bytes,
        allowed_destinations=allowed_destinations, status="READY", expires_at=expires_at,
        execution_epoch=0, revoked=False,
    )
    session.add(budget)
    session.add(admission)
    await session.flush()
    return admission


async def resolve_execution_admission(
    session: AsyncSession, admission_id: UUID, budget_id: UUID, *, task_id: UUID,
    owner_id: UUID, caller_id: str, now: datetime | None = None,
    allow_consumed: bool | None = False,
) -> tuple[DownloadExecutionAdmissionModel, DownloadExecutionBudgetModel]:
    current = _utc(now or datetime.now(UTC))
    pair = (await session.execute(select(
        DownloadExecutionAdmissionModel, DownloadExecutionBudgetModel
    ).join(DownloadExecutionBudgetModel,
        DownloadExecutionBudgetModel.id == DownloadExecutionAdmissionModel.budget_id
    ).where(DownloadExecutionAdmissionModel.id == admission_id,
        DownloadExecutionBudgetModel.id == budget_id
    ).with_for_update())).one_or_none()
    if pair is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_REJECTED")
    admission, budget = pair
    profile = _profile(admission.environment_id)
    allowed_statuses = {"CONSUMED"} if allow_consumed is True else (
        {"READY", "CONSUMED"} if allow_consumed is None else {"READY"}
    )
    if (admission.status not in allowed_statuses or admission.revoked
        or _utc(admission.expires_at) <= current or admission.task_id != task_id
        or admission.owner_id != owner_id or admission.caller_id != caller_id
        or caller_id != profile["caller_id"]
        or admission.protocol != "http" or admission.source != "direct_link"
        or budget.status != "ACTIVE" or _utc(budget.expires_at) <= current
        or budget.owner_id != owner_id or budget.project_id != admission.project_id
        or budget.policy_revision != admission.policy_revision
        or budget.reserved_bytes != admission.reserved_bytes
        or budget.admitted_bytes is not None
        or any(getattr(admission, key) != profile[key] for key in (
            "caller_kind", "tool_digest", "environment_id", "policy_revision",
            "allowed_destinations",
        ))
        or budget.disk_block_limit_bytes != profile["disk_block_limit_bytes"]
        or budget.disk_inodes_limit != profile["disk_inodes_limit"]
        or admission.status == "CONSUMED" and admission.execution_id is None):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_REJECTED")
    source_digest = await _facts(
        session, ingestion_id=admission.ingestion_id, task_id=task_id, owner_id=owner_id,
        project_id=admission.project_id, confirmation_id=admission.confirmation_id,
        request_digest=admission.request_digest, limit_bytes=budget.limit_bytes,
        expires_at=admission.expires_at, now=current,
        allowed_destinations=admission.allowed_destinations,
        task_statuses=("running",) if admission.status == "CONSUMED" else ("queued", "running"),
    )
    if source_digest != admission.source_digest:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_SOURCE_CHANGED")
    return admission, budget


async def consume_execution_admission(
    session: AsyncSession, admission_id: UUID, *, task_id: UUID, owner_id: UUID,
    request_digest: str, caller_id: str, now: datetime | None = None,
    budget_id: UUID | None = None, attempt_id: UUID | None = None,
    expected_epoch: int | None = None, tool_digest: str | None = None,
    environment_id: str | None = None, execution_id: UUID | None = None,
) -> DownloadExecutionAdmissionModel:
    current = _utc(now or datetime.now(UTC))
    if attempt_id is None or expected_epoch is None or tool_digest is None or environment_id is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_BINDING_MISSING")
    row = (await session.execute(select(DownloadExecutionAdmissionModel).where(
        DownloadExecutionAdmissionModel.id == admission_id
    ))).scalar_one_or_none()
    if row is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_NOT_FOUND")
    admission, _ = await resolve_execution_admission(
        session, admission_id, budget_id or row.budget_id, task_id=task_id,
        owner_id=owner_id, caller_id=caller_id, now=current,
    )
    if (admission.tool_digest != tool_digest or admission.environment_id != environment_id
        or admission.request_digest != request_digest
        or expected_epoch != admission.execution_epoch
        or (attempt_id is not None and attempt_id != admission.attempt_id)):
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_REJECTED")
    expected_identity = deterministic_execution_id(
        task_id, admission.attempt_id, expected_epoch + 1
    )
    execution_identity = execution_id or expected_identity
    if execution_identity != expected_identity:
        raise DownloadExecutionAdmissionError("DOWNLOAD_EXECUTION_ID_INVALID")
    changed = (await session.execute(update(DownloadExecutionAdmissionModel).where(
        DownloadExecutionAdmissionModel.id == admission_id,
        DownloadExecutionAdmissionModel.status == "READY",
        DownloadExecutionAdmissionModel.revoked.is_(False),
        DownloadExecutionAdmissionModel.execution_epoch == expected_epoch,
        DownloadExecutionAdmissionModel.attempt_id == admission.attempt_id,
    ).values(
        status="CONSUMED",
        consumed_at=current,
        execution_epoch=expected_epoch + 1,
        execution_id=execution_identity,
    )
        .returning(DownloadExecutionAdmissionModel.id))).scalar_one_or_none()
    if changed is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_REJECTED")
    await session.flush()
    # Keep the identity-map object coherent for callers and lightweight test
    # sessions that intentionally do not implement AsyncSession.refresh().
    admission.status = "CONSUMED"
    admission.consumed_at = current
    admission.execution_epoch = expected_epoch + 1
    admission.execution_id = execution_identity
    return admission


async def reserve_execution_budget(
    session: AsyncSession, budget_id: UUID, *, amount: int, now: datetime | None = None,
) -> DownloadExecutionBudgetModel:
    """Atomic shared-account primitive; subtract first to avoid BIGINT addition overflow."""
    if not _positive(amount):
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_AMOUNT_INVALID")
    current = _utc(now or datetime.now(UTC))
    result = await session.execute(update(DownloadExecutionBudgetModel).where(
        DownloadExecutionBudgetModel.id == budget_id,
        DownloadExecutionBudgetModel.status == "ACTIVE",
        DownloadExecutionBudgetModel.expires_at > current,
        DownloadExecutionBudgetModel.limit_bytes - DownloadExecutionBudgetModel.reserved_bytes
        >= amount,
    ).values(reserved_bytes=DownloadExecutionBudgetModel.reserved_bytes + amount)
        .returning(DownloadExecutionBudgetModel.id)
        .execution_options(synchronize_session=False))
    if result.scalar_one_or_none() is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_EXCEEDED")
    return (await session.execute(select(DownloadExecutionBudgetModel).where(
        DownloadExecutionBudgetModel.id == budget_id
    ).execution_options(populate_existing=True))).scalar_one()


async def _settle_execution_budget(
    session: AsyncSession,
    admission_id: UUID,
    budget_id: UUID,
    *,
    task_id: UUID,
    attempt_id: UUID,
    execution_epoch: int,
    policy_revision: str,
    rx_admitted_bytes: int,
    rx_limit_bytes: int,
    disk_limit_bytes: int,
    inode_limit: int,
) -> DownloadExecutionBudgetModel:
    """Settle a reservation after the receipt repository authenticates it.

    The receipt verifier and this mutation must share the caller's transaction so
    replay protection, terminal admission state, and budget accounting commit or
    roll back together. Keep this low-level mutation private to the repository package.
    """
    if any(not _positive(value) for value in (
        rx_limit_bytes, disk_limit_bytes, inode_limit,
    )) or not isinstance(rx_admitted_bytes, int) or isinstance(rx_admitted_bytes, bool) \
            or rx_admitted_bytes < 0:
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_MEASUREMENT_INVALID")

    pair = (await session.execute(select(
        DownloadExecutionAdmissionModel, DownloadExecutionBudgetModel
    ).join(DownloadExecutionBudgetModel,
        DownloadExecutionBudgetModel.id == DownloadExecutionAdmissionModel.budget_id
    ).where(DownloadExecutionAdmissionModel.id == admission_id,
        DownloadExecutionAdmissionModel.budget_id == budget_id
    ).with_for_update())).one_or_none()
    if pair is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_BINDING_REJECTED")
    admission, budget = pair
    if (
        admission.task_id != task_id
        or admission.attempt_id != attempt_id
        or admission.execution_epoch != execution_epoch
        or admission.policy_revision != policy_revision
        or admission.status not in {"CONSUMED", "RECONCILIATION_REQUIRED"}
        or budget.status != "ACTIVE"
        or budget.policy_revision != policy_revision
        or budget.admitted_bytes is not None and budget.admitted_bytes > budget.reserved_bytes
        or rx_limit_bytes != budget.limit_bytes
        or disk_limit_bytes != budget.disk_block_limit_bytes
        or inode_limit != budget.disk_inodes_limit
        or rx_admitted_bytes > admission.reserved_bytes
    ):
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_BINDING_REJECTED")

    prior_admitted = func.coalesce(DownloadExecutionBudgetModel.admitted_bytes, 0)
    settled = await session.execute(update(DownloadExecutionBudgetModel).where(
        DownloadExecutionBudgetModel.id == budget_id,
        DownloadExecutionBudgetModel.status == "ACTIVE",
        DownloadExecutionBudgetModel.reserved_bytes >= admission.reserved_bytes,
        DownloadExecutionBudgetModel.limit_bytes - prior_admitted >= rx_admitted_bytes,
        DownloadExecutionBudgetModel.reserved_bytes - admission.reserved_bytes
        + rx_admitted_bytes >= prior_admitted + rx_admitted_bytes,
    ).values(
        reserved_bytes=(DownloadExecutionBudgetModel.reserved_bytes
                        - admission.reserved_bytes + rx_admitted_bytes),
        admitted_bytes=prior_admitted + rx_admitted_bytes,
    ).returning(DownloadExecutionBudgetModel.id))
    if settled.scalar_one_or_none() is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_SETTLEMENT_REJECTED")

    changed = await session.execute(update(DownloadExecutionAdmissionModel).where(
        DownloadExecutionAdmissionModel.id == admission_id,
        DownloadExecutionAdmissionModel.budget_id == budget_id,
        DownloadExecutionAdmissionModel.task_id == task_id,
        DownloadExecutionAdmissionModel.attempt_id == attempt_id,
        DownloadExecutionAdmissionModel.execution_epoch == execution_epoch,
        DownloadExecutionAdmissionModel.status.in_({"CONSUMED", "RECONCILIATION_REQUIRED"}),
    ).values(status="SETTLED").returning(DownloadExecutionAdmissionModel.id))
    if changed.scalar_one_or_none() is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_BUDGET_SETTLEMENT_REJECTED")
    await session.flush()
    return (await session.execute(select(DownloadExecutionBudgetModel).where(
        DownloadExecutionBudgetModel.id == budget_id
    ))).scalar_one()


async def revoke_execution_admission(session: AsyncSession, admission_id: UUID) -> None:
    admission = (await session.execute(select(DownloadExecutionAdmissionModel).where(
        DownloadExecutionAdmissionModel.id == admission_id
    ).with_for_update())).scalar_one_or_none()
    if admission is None:
        raise DownloadExecutionAdmissionError("DOWNLOAD_ADMISSION_NOT_FOUND")
    if admission.revoked or admission.status in {"REVOKED", "SETTLED"}:
        return
    admission.revoked = True
    if admission.status == "READY":
        budget = (await session.execute(select(DownloadExecutionBudgetModel).where(
            DownloadExecutionBudgetModel.id == admission.budget_id
        ).with_for_update())).scalar_one()
        if budget.admitted_bytes is not None or budget.reserved_bytes < admission.reserved_bytes:
            admission.status = "RECONCILIATION_REQUIRED"
        else:
            budget.reserved_bytes -= admission.reserved_bytes
            admission.reserved_bytes = 0
            admission.status = "REVOKED"
    else:
        # A DB cancellation is never proof that egress or an OS scope has stopped.
        admission.status = "RECONCILIATION_REQUIRED"
    await session.flush()
