"""Build a Supervisor request from the existing persisted download Task.

The Worker may pass identifiers and an execution UUID, but it must not invent
approval, budget, owner, attempt, or epoch values.  This helper is deliberately
read-only: claiming the admission remains the Supervisor authority's atomic
operation.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.infrastructure.database.models.download_execution import (
    DownloadExecutionAdmissionModel,
)
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.download.supervisor_server import SupervisorDeniedError
from cygnusx.infrastructure.download.trusted_execution import (
    ExecutionBoundaryRequest,
    deterministic_execution_id,
)


async def build_execution_boundary_request(
    session: AsyncSession, task_id: UUID, owner_id: UUID
) -> ExecutionBoundaryRequest:
    """Derive one initial HTTP execution request from durable Task bindings."""
    task = await session.get(TaskModel, task_id)
    if task is None or task.user_id != owner_id or task.flow_id != "ebi_download":
        raise SupervisorDeniedError("SUPERVISOR_TASK_BINDING_REJECTED")
    binding = (task.parameters or {}).get("_download_execution_binding")
    if not isinstance(binding, dict) or binding.get("version") != 1:
        raise SupervisorDeniedError("SUPERVISOR_EXECUTION_BINDING_MISSING")
    try:
        admission_ref = UUID(str(binding["admission_ref"]))
        budget_ref = UUID(str(binding["budget_ref"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise SupervisorDeniedError("SUPERVISOR_EXECUTION_BINDING_INVALID") from exc
    admission = (
        await session.execute(
            select(DownloadExecutionAdmissionModel).where(
                DownloadExecutionAdmissionModel.id == admission_ref,
                DownloadExecutionAdmissionModel.budget_id == budget_ref,
                DownloadExecutionAdmissionModel.task_id == task_id,
                DownloadExecutionAdmissionModel.owner_id == owner_id,
            )
        )
    ).scalar_one_or_none()
    if admission is None or admission.revoked or admission.status not in {"READY", "CONSUMED"}:
        raise SupervisorDeniedError("SUPERVISOR_ADMISSION_NOT_READY")
    if admission.protocol != "http":
        raise SupervisorDeniedError("SUPERVISOR_ADMISSION_EPOCH_REJECTED")
    expected_epoch = 0 if admission.status == "READY" else 1
    if admission.execution_epoch != expected_epoch:
        raise SupervisorDeniedError("SUPERVISOR_ADMISSION_EPOCH_REJECTED")
    # The Supervisor scope is deterministic for Task+epoch. Derive the
    # execution identity from the same durable admission facts so a Worker
    # retry can reconcile the original scope instead of creating a new identity.
    execution_id = deterministic_execution_id(task_id, admission.attempt_id, 1)
    if admission.status == "CONSUMED" and admission.execution_id != execution_id:
        raise SupervisorDeniedError("SUPERVISOR_EXECUTION_ID_REJECTED")
    return ExecutionBoundaryRequest(
        task_id=task_id,
        owner_id=owner_id,
        attempt_id=admission.attempt_id,
        execution_id=execution_id,
        execution_epoch=1,
        admission_ref=admission.id,
        budget_ref=admission.budget_id,
        protocol="http",
    )
