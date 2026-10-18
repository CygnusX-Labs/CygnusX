"""Minimal evidence on existing Task JSON; never a scheduler or runtime attestation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError as SchemaError
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.execution_definition import DefinitionParameter, ExecutionFileRef
from cygnusx.application.schemas.execution_evidence import (
    ExecutionDefinitionV2,
    ExecutionEvidence,
    ExecutionTaskBinding,
    GeneratedExecutionFile,
    WorkerEvidence,
    canonical_digest,
)
from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.services.flow_service import FlowService
from cygnusx.core.exceptions import ConflictError
from cygnusx.domain.task.entities import Task
from cygnusx.infrastructure.database.models.dataset import DatasetAnalysisLinkModel

EVIDENCE_KEY = "_execution_evidence"
# Owner-facing values only. Other approved parameters are bound by digest, not copied.
DISPLAY_PARAMETERS = frozenset({"cores", "threads", "padj", "pvalue", "log2fc", "alpha"})


def parameter_digest(parameters: dict[str, Any]) -> str:
    return canonical_digest({k: v for k, v in parameters.items() if not k.startswith("_")})


def freeze_execution_evidence(
    task_id: UUID,
    owner: UUID,
    request: TaskSubmitRequest,
    flow_payload: dict[str, Any],
    *,
    link: DatasetAnalysisLinkModel | None = None,
    handoff: dict[str, Any] | None = None,
    generated_files: tuple[GeneratedExecutionFile, ...] = (),
) -> dict[str, Any]:
    """Only called after authoritative submission validation; no historical converter."""
    handoff = handoff or {}
    refs = tuple(
        ExecutionFileRef(
            file_record_id=UUID(asset["file_record_id"]),
            sha256=asset["sha256"],
            role="input",
            status="DECLARED",
        )
        for asset in handoff.get("assets", [])
    )
    definition = ExecutionDefinitionV2(
        workflow_id=request.flow_id,
        flow_config_sha256=canonical_digest(flow_payload),
        parameters_sha256=parameter_digest(request.parameters),
        sample_design_digest=canonical_digest(
            {"samples": request.sample_sheet, "comparisons": request.comparisons}
        ),
        dataset_version_id=link.version_id if link else None,
        handoff_digest=link.handoff_hash if link else None,
        input_refs=refs,
        normalized_parameters=tuple(
            DefinitionParameter(name=key, value_json=json.dumps(value, allow_nan=False))
            for key, value in request.parameters.items()
            if key in DISPLAY_PARAMETERS and isinstance(value, (bool, int, float))
        ),
    )
    binding = ExecutionTaskBinding(
        task_id=task_id,
        owner_id=owner,
        definition_digest=definition.content_digest(),
        generated_files_digest=canonical_digest(
            [item.model_dump(mode="json") for item in generated_files]
        ),
    )
    return ExecutionEvidence(
        definition=definition,
        definition_digest=definition.content_digest(),
        binding=binding,
        execution_binding_digest=binding.content_digest(),
        frozen_at=datetime.now(UTC),
        generated_files=generated_files,
    ).model_dump(mode="json")


def capture_generated_files(
    owner: UUID, work_dir: str, files: dict[str, Path]
) -> tuple[GeneratedExecutionFile, ...]:
    from cygnusx.core.config import get_settings
    from cygnusx.domain.dataset.validation import ValidationLimits, checksum, open_owned_file
    from cygnusx.infrastructure.storage import get_path_factory

    factory = get_path_factory()
    limits = ValidationLimits(max_bytes=get_settings().dataset_import_max_bytes)
    result = []
    for path in sorted(set(files.values())):
        if path.parent != Path(work_dir) or path.name in {".", ".."}:
            raise ConflictError("Generated execution file escaped work directory")
        with open_owned_file(path, factory.user_root(str(owner))) as stream:
            actual, _ = checksum(stream, limits)
        result.append(GeneratedExecutionFile(name=path.name, sha256=actual))
    return tuple(result)


def read_execution_evidence(task: Any) -> ExecutionEvidence | None:
    raw = (task.parameters or {}).get(EVIDENCE_KEY)
    if raw is None:
        return None  # History is NOT_OBSERVED, never backfilled from current environment.
    try:
        evidence = ExecutionEvidence.model_validate(raw)
    except (SchemaError, ValueError) as exc:
        raise ConflictError(
            "Execution evidence corrupted", code="EXECUTION_EVIDENCE_INVALID"
        ) from exc
    if evidence.binding.task_id != task.id or evidence.binding.owner_id != task.user_id:
        raise ConflictError("Execution identity mismatch", code="EXECUTION_EVIDENCE_INVALID")
    return evidence


async def observe_execution(
    db: AsyncSession, task: Task, *, after: bool = False, failed: bool = False
) -> None:
    """Append observations; preserve failures before returning to the original Worker."""
    evidence = read_execution_evidence(task)
    if evidence is None:
        return
    from typing import Literal

    from cygnusx.application.services.research_execution_binding import (
        check_inputs,
        worker_preflight,
    )
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl

    integrity: Literal["VERIFIED", "NOT_OBSERVED", "FAILED"] = "NOT_OBSERVED"
    error: Exception | None = None
    try:
        if evidence.definition.parameters_sha256 != parameter_digest(task.parameters):
            raise ConflictError("Parameters changed", code="EXECUTION_BINDING_MISMATCH")
        files = {item.name: Path(task.work_dir) / item.name for item in evidence.generated_files}
        if capture_generated_files(task.user_id, task.work_dir, files) != evidence.generated_files:
            raise ConflictError("Generated execution files changed", code="INPUT_CHANGED")
        flow = FlowService().get_flow_config(task.flow_id)
        if evidence.definition.flow_config_sha256 != canonical_digest(flow.model_dump(mode="json")):
            raise ConflictError("Flow changed", code="FLOW_DEFINITION_CHANGED")
        if evidence.definition.input_refs:
            from sqlalchemy import select

            link = (
                await db.execute(
                    select(DatasetAnalysisLinkModel).where(
                        DatasetAnalysisLinkModel.task_id == task.id
                    )
                )
            ).scalar_one_or_none()
            if link is None or link.version_id != evidence.definition.dataset_version_id:
                raise ConflictError("Dataset binding missing", code="EXECUTION_BINDING_MISMATCH")
            handoff = await check_inputs(db, task.user_id, link)
            observed = {(asset["file_record_id"], asset["sha256"]) for asset in handoff["assets"]}
            expected = {
                (str(ref.file_record_id), ref.sha256) for ref in evidence.definition.input_refs
            }
            if observed != expected or link.handoff_hash != evidence.definition.handoff_digest:
                raise ConflictError("Input binding changed", code="INPUT_CHANGED")
            integrity = "VERIFIED"
        if not after and not failed:
            await worker_preflight(db, task)
    except Exception as exc:
        integrity = "FAILED"
        error = exc
    observation = WorkerEvidence(
        recorded_at=datetime.now(UTC),
        phase="FAILED" if error or failed else "POSTFLIGHT" if after else "PREFLIGHT",
        input_integrity=integrity,
        reason_code="INPUT_OR_BINDING_CHANGED" if error else "EXECUTION_FAILED" if failed else None,
    )
    updated = ExecutionEvidence.model_validate(
        {**evidence.model_dump(), "observations": (*evidence.observations, observation)}
    )
    task.parameters = {**task.parameters, EVIDENCE_KEY: updated.model_dump(mode="json")}
    await TaskRepositoryImpl(db).save(task)
    await db.commit()  # Before execution, reporting, or propagation of a preflight failure.
    if error:
        raise ConflictError(
            "Execution evidence check failed", code="EXECUTION_EVIDENCE_FAILED"
        ) from error


def evidence_projection(task: Any) -> dict[str, Any] | None:
    evidence = read_execution_evidence(task)
    if evidence is None:
        return None
    return {
        "definition_digest": evidence.definition_digest,
        "execution_binding_digest": evidence.execution_binding_digest,
        "schema_version": evidence.schema_version,
        "observations": [item.model_dump(mode="json") for item in evidence.observations],
        "workflow_release": "NOT_OBSERVED",
        "container_image": "NOT_OBSERVED",
        "tools": "NOT_OBSERVED",
        "references": "NOT_OBSERVED",
    }


def retain_preflight_failure(task: Task) -> None:
    evidence = read_execution_evidence(task)
    if evidence is None or evidence.observations and evidence.observations[-1].phase == "FAILED":
        return
    event = WorkerEvidence(
        recorded_at=datetime.now(UTC),
        phase="FAILED",
        reason_code="EXECUTION_FAILED",
        input_integrity=evidence.observations[-1].input_integrity
        if evidence.observations
        else "NOT_OBSERVED",
    )
    updated = ExecutionEvidence.model_validate(
        {**evidence.model_dump(), "observations": (*evidence.observations, event)}
    )
    task.parameters = {**task.parameters, EVIDENCE_KEY: updated.model_dump(mode="json")}


def validate_executor_binding(
    task: Task,
    *,
    snakefile: str,
    work_dir: str,
    config_file: str,
    config_file_param: str,
    cores: int,
) -> None:
    if read_execution_evidence(task) is None:
        return  # Do not invent a historical binding.
    execution = FlowService().get_flow_config(task.flow_id).execution
    expected_cores = execution.default_resources.cores
    if (
        snakefile != execution.snakefile
        or work_dir != task.work_dir
        or Path(config_file) != Path(task.work_dir) / execution.config_file_name
        or config_file_param != (execution.config_file_param or "analysisyaml")
        or cores != expected_cores
    ):
        raise ConflictError("Executor arguments changed", code="EXECUTION_BINDING_MISMATCH")
