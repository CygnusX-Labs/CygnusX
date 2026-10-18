"""Final Dataset input checks shared by TaskService and the real Worker boundary."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.services.dataset_import_service import digest
from cygnusx.application.services.flow_service import FlowService
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import ConflictError, ValidationError
from cygnusx.domain.dataset.validation import ValidationLimits, checksum, open_owned_file
from cygnusx.domain.task.entities import Task
from cygnusx.infrastructure.database.models.dataset import DatasetAnalysisLinkModel
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.database.repositories.dataset_repository import DatasetRepository
from cygnusx.infrastructure.storage import get_path_factory


def execution_binding(flow_id: str, request: dict[str, Any], handoff_hash: str) -> dict[str, Any]:
    flow = FlowService().get_flow_config(flow_id)
    return {
        "schema_version": "cygnusx.execution_binding.v1",
        "flow_id": flow_id,
        "flow_version": flow.meta.version,
        "flow_config_sha256": digest(flow.model_dump(mode="json")),
        "parameters_sha256": digest(request),
        "handoff_hash": handoff_hash,
        "runtime_environment": "NOT_OBSERVED",
        "workflow_release_digest": None,
    }


async def check_inputs(
    db: AsyncSession, owner: UUID, link: DatasetAnalysisLinkModel, *, require_worker: bool = True
) -> dict[str, Any]:
    bound = link.normalized_request
    repo = DatasetRepository(db)
    project_id, dataset_id = UUID(bound["project_id"]), UUID(bound["dataset_id"])
    await repo.require_module(owner, "flows")
    version = await repo.version(owner, project_id, dataset_id, link.version_id)
    if bound.get("owner_id") != str(owner) or bound.get("dataset_version_id") != str(version.id):
        raise ConflictError("Dataset execution identity changed", code="EXECUTION_BINDING_MISMATCH")
    handoff = version.handoff
    if (
        not handoff
        or not handoff.get("assets")
        or handoff["manifest_hash"] != link.handoff_hash
        or digest({**handoff, "manifest_hash": None}) != link.handoff_hash
    ):
        raise ConflictError("Frozen input evidence changed", code="HANDOFF_CHANGED")
    if require_worker and not handoff["validation"].get("worker_paths_verified"):
        raise ValidationError("Worker input paths not accepted", code="WORKER_PATHS_NOT_VERIFIED")
    factory = get_path_factory()
    settings = get_settings()
    deadline = time.monotonic() + settings.research_capture_timeout_seconds
    remaining = settings.research_artifact_max_bytes
    if len(handoff["assets"]) > settings.research_artifact_max_files:
        raise ValidationError("Input capture count budget", code="VALIDATION_LIMIT")
    for asset in handoff["assets"]:
        if time.monotonic() > deadline:
            raise ValidationError("Input capture time budget", code="VALIDATION_LIMIT")
        record = await repo.file(owner, project_id, UUID(asset["file_record_id"]))
        if record.storage_backend != "local":
            raise ValidationError("Input storage not verified", code="STORAGE_NOT_VERIFIED")
        with open_owned_file(
            factory.data_root / record.storage_path, factory.user_root(str(owner))
        ) as stream:
            actual, size = checksum(
                stream,
                ValidationLimits(
                    max_bytes=min(settings.dataset_import_max_bytes, max(0, remaining))
                ),
            )
        remaining -= size
        if actual != asset["sha256"] or size != asset["size"]:
            raise ConflictError("Input file changed", code="INPUT_CHANGED")
    return handoff


async def validate_dataset_submission(
    db: AsyncSession, owner: UUID, req: TaskSubmitRequest
) -> DatasetAnalysisLinkModel | None:
    if not req.idempotency_key or not req.idempotency_key.startswith("dataset:"):
        return None
    from cygnusx.application.services.agent_tool_gateway import require_agent_write_gate

    require_agent_write_gate("analysis.submit")
    try:
        key = UUID(req.idempotency_key.removeprefix("dataset:"))
    except ValueError as exc:
        raise ValidationError("Invalid Dataset request key") from exc
    link = (
        await db.execute(
            select(DatasetAnalysisLinkModel)
            .where(DatasetAnalysisLinkModel.id == key)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        link is None
        or link.state not in {"SUBMITTING", "QUEUED"}
        or (link.state == "QUEUED" and link.task_id is None)
        or link.normalized_request.get("request") != req.model_dump(mode="json")
    ):
        raise ConflictError(
            "Dataset request is not an approved submission", code="EXECUTION_BINDING_MISMATCH"
        )
    expected = execution_binding(req.flow_id, req.model_dump(mode="json"), link.handoff_hash)
    if not link.execution_binding or link.execution_binding != expected:
        raise ConflictError("Flow definition or parameters changed", code="FLOW_DEFINITION_CHANGED")
    await check_inputs(db, owner, link)
    return link


async def worker_preflight(db: AsyncSession, task: TaskModel | Task) -> None:
    if not task.idempotency_key or not task.idempotency_key.startswith("dataset:"):
        return
    from cygnusx.application.services.agent_tool_gateway import require_agent_write_gate

    require_agent_write_gate("analysis.submit")
    link = (
        await db.execute(
            select(DatasetAnalysisLinkModel).where(DatasetAnalysisLinkModel.task_id == task.id)
        )
    ).scalar_one_or_none()
    if link is None or link.flow_id != task.flow_id:
        raise ConflictError("Worker Task has no trusted Dataset binding")
    expected = execution_binding(
        task.flow_id, link.normalized_request["request"], link.handoff_hash
    )
    if link.execution_binding != expected:
        raise ConflictError("Worker Flow definition changed", code="FLOW_DEFINITION_CHANGED")
    await check_inputs(db, task.user_id, link)
