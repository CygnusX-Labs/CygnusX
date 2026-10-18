"""Ground references and read statistical values from actual verified output bytes."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import os
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.claim_provenance import ClaimProvenance, ClaimProvenanceRequest
from cygnusx.application.schemas.research_claims import (
    ArtifactCellRequest,
    ClaimAssessment,
    ClaimDraft,
)
from cygnusx.application.services.research_plan_service import require_plan_enabled
from cygnusx.application.services.research_provenance_service import ResearchProvenanceService
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import ConflictError, NotFoundError, ValidationError
from cygnusx.domain.dataset.validation import open_owned_file
from cygnusx.domain.research.scientific_validation import assess_claim
from cygnusx.infrastructure.storage import get_path_factory


class ResearchClaimService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def provenance(
        self,
        owner: UUID,
        project: UUID,
        request: ClaimProvenanceRequest,
    ) -> ClaimProvenance:
        from cygnusx.application.schemas.execution_evidence import canonical_digest
        from cygnusx.application.services.dataset_import_service import digest
        from cygnusx.application.services.execution_evidence_service import read_execution_evidence
        from cygnusx.application.services.project_delivery_service import ProjectDeliveryService
        from cygnusx.application.services.reproducible_report_service import validate_snapshot_row
        from cygnusx.infrastructure.database.models.report import ReportModel, ReportSnapshotModel
        from cygnusx.infrastructure.database.models.result_observation import ResultObservationModel
        from cygnusx.infrastructure.database.models.task import TaskModel

        require_plan_enabled()
        await ProjectDeliveryService(self.db).authorize(owner, project)
        report = None
        snapshot = None
        frozen = None
        gaps: set[str] = set()
        observation_id = None
        if request.source_report_id:
            report = await self.db.get(
                ReportModel, request.source_report_id, populate_existing=True
            )
            if (
                not report
                or report.user_id != owner
                or report.task_id != request.task_id
                or report.status != "completed"
                or report.report_kind not in {"scientific", "reproducibility"}
            ):
                raise NotFoundError("Report not available for this task/project")
            observation_id = report.result_observation_id
            if report.snapshot_id:
                snapshot = await self.db.get(
                    ReportSnapshotModel, report.snapshot_id, populate_existing=True
                )
                if not snapshot or snapshot.user_id != owner or snapshot.task_id != request.task_id:
                    raise ConflictError("Report snapshot association mismatch")
                frozen = validate_snapshot_row(snapshot)
                if (
                    frozen.source_execution.project_id is not None
                    and frozen.source_execution.project_id != project
                ):
                    raise ConflictError("Snapshot project identity mismatch")
                if frozen.research_delivery:
                    saved_id = frozen.research_delivery.result_observation_id
                    if observation_id and saved_id != observation_id:
                        raise ConflictError("Report observation association mismatch")
                    observation_id = saved_id
            else:
                gaps.add("REPORT_SNAPSHOT_NOT_RECORDED")
        else:
            gaps.update({"SOURCE_REPORT_NOT_SELECTED", "REPORT_SNAPSHOT_NOT_RECORDED"})

        # Reuse the original authoritative parser. Never accept a caller-supplied value or SHA.
        cell = await self.cell(owner, project, request)
        from cygnusx.infrastructure.database.models.file import FileRecordModel

        record = await self.db.get(FileRecordModel, request.file_record_id, populate_existing=True)
        if (
            not record
            or record.user_id != owner
            or record.task_id != request.task_id
            or record.owner_scope != "personal"
            or record.status != "active"
            or record.lifecycle_status != "active"
        ):
            raise NotFoundError("Result file unavailable")
        if record.checksum and record.checksum != cell["sha256"]:
            raise ConflictError("Registered result fingerprint changed", code="ARTIFACT_CHANGED")
        graph = await ResearchProvenanceService(self.db).task(owner, request.task_id)
        if frozen:
            saved_scope = frozen.research_delivery
            if saved_scope and (
                saved_scope.project_id is not None
                and saved_scope.project_id != project
                or saved_scope.dataset_version_id is not None
                and saved_scope.dataset_version_id != graph.dataset_version_id
            ):
                raise ConflictError("Report snapshot project/version mismatch")
            if (
                not saved_scope
                or saved_scope.project_id is None
                or saved_scope.dataset_version_id is None
            ):
                gaps.add("SNAPSHOT_DATASET_BINDING_NOT_RECORDED")
        if graph.project_id != project or not any(
            a.file_record_id == request.file_record_id
            and a.sha256 == cell["sha256"]
            and a.integrity == "VERIFIED"
            for a in graph.artifacts
        ):
            raise ConflictError("Cell provenance changed during capture", code="ARTIFACT_CHANGED")
        if report is None:
            observation_id = graph.result_observation_id
        # A legacy report never borrows the newest observation or snapshot.
        observation = (
            await self.db.get(ResultObservationModel, observation_id, populate_existing=True)
            if observation_id
            else None
        )
        if observation:
            if (
                observation.user_id != owner
                or observation.project_id != project
                or observation.task_id != request.task_id
                or observation.analysis_link_id != graph.analysis_link_id
                or digest(observation.payload) != observation.evidence_digest
            ):
                raise ConflictError("Result observation identity/integrity mismatch")
            saved = observation.payload
            from pydantic import ValidationError as SchemaError

            from cygnusx.application.schemas.research_delivery import ResearchProvenance

            try:
                ResearchProvenance.model_validate(saved)
            except SchemaError as exc:
                raise ConflictError("Saved observation contract invalid") from exc
            if saved.get("dataset_version_id") != str(graph.dataset_version_id) or not any(
                a.get("file_record_id") == str(request.file_record_id)
                and a.get("sha256") == cell["sha256"]
                and a.get("integrity") == "VERIFIED"
                for a in saved.get("artifacts", [])
            ):
                raise ConflictError(
                    "Report observation does not bind the requested cell",
                    code="OBSERVATION_ARTIFACT_MISMATCH",
                )
        elif observation_id:
            raise ConflictError("Referenced observation unavailable")
        else:
            gaps.add("RESULT_OBSERVATION_NOT_RECORDED")
        saved_execution = (
            (observation.payload.get("runtime", {}).get("execution_evidence") or {})
            if observation
            else {}
        )
        if not isinstance(saved_execution, dict):
            raise ConflictError("Saved execution observation contract invalid")
        definition = saved_execution.get("definition_digest")
        binding = saved_execution.get("execution_binding_digest")
        definition_status: Literal["NOT_RECORDED", "REFERENCE_ONLY", "VERIFIED_DOCUMENT"] = (
            "NOT_RECORDED"
        )
        if definition:
            task = await self.db.get(TaskModel, request.task_id, populate_existing=True)
            if task is None:
                raise NotFoundError("Task unavailable")
            evidence = read_execution_evidence(task)
            if evidence is None:
                definition_status = "REFERENCE_ONLY"
                gaps.add("EXECUTION_DEFINITION_DOCUMENT_UNAVAILABLE")
            elif (
                evidence.definition_digest != definition
                or evidence.execution_binding_digest != binding
            ):
                raise ConflictError("Observed execution definition changed")
            else:
                definition_status = "VERIFIED_DOCUMENT"
        else:
            gaps.add("EXECUTION_DEFINITION_NOT_RECORDED_IN_OBSERVATION")
        gaps.update(graph.gaps)
        gaps.update(cell["gaps"])
        statement = (
            f"{request.feature_id} / {request.column} = {cell['value']}"
            if cell["value"] is not None
            else None
        )
        identity = {
            "owner_id": str(owner),
            "project_id": str(project),
            "task_id": str(request.task_id),
            "report_id": str(report.id) if report else None,
            "report_version": report.version if report else None,
            "snapshot_id": str(snapshot.id) if snapshot else None,
            "snapshot_digest": snapshot.snapshot_digest if snapshot else None,
            "dataset_version_id": str(graph.dataset_version_id)
            if graph.dataset_version_id
            else None,
            "analysis_link_id": str(graph.analysis_link_id) if graph.analysis_link_id else None,
            "definition_digest": definition,
            "execution_binding_digest": binding,
            "observation_id": str(observation_id) if observation_id else None,
            "file_id": str(request.file_record_id),
            "sha256": cell["sha256"],
            "row": request.feature_id,
            "column": request.column,
            "value": cell["value"],
            "interpretation": request.claim.model_dump(mode="json") if request.claim else None,
        }
        return ClaimProvenance(
            claim_id=canonical_digest(identity),
            claim_text=request.claim.claim_text
            if request.claim
            else statement or "Value not recorded",
            project_id=project,
            source_report_id=report.id if report else None,
            report_version=report.version if report else None,
            report_snapshot_id=snapshot.id if snapshot else None,
            snapshot_digest=snapshot.snapshot_digest if snapshot else None,
            task_id=request.task_id,
            result_observation_id=observation_id,
            observation_digest=observation.evidence_digest if observation else None,
            observation_binding="VERIFIED_ASSOCIATION" if observation else "NOT_RECORDED",
            file_record_id=request.file_record_id,
            file_sha256=cell["sha256"],
            row_identifier=request.feature_id,
            row_number=cell["row"],
            column_identifier=request.column,
            value=cell["value"],
            verification_status="VERIFIED_VALUE" if statement else "NOT_VERIFIED",
            supported_statement=statement,
            supported_statement_status="SUPPORTED_CLAIM" if statement else "NOT_VERIFIED",
            interpretation_status="AI_INTERPRETATION" if request.claim else None,
            dataset_version_id=graph.dataset_version_id,
            analysis_link_id=graph.analysis_link_id,
            definition_digest=definition,
            execution_binding_digest=binding,
            definition_status=definition_status,
            input_file_record_ids=tuple(a.file_record_id for a in graph.inputs if a.file_record_id),
            missing_evidence=tuple(sorted(gaps)),
        )

    async def assessment(
        self,
        owner: UUID,
        project: UUID,
        task_id: UUID,
        claim: ClaimDraft,
    ) -> ClaimAssessment:
        require_plan_enabled()
        graph = await ResearchProvenanceService(self.db).task(owner, task_id)
        if graph.project_id != project:
            raise NotFoundError("Task 不属于当前项目")
        available: set[tuple[str, str]] = set()
        if graph.dataset_version_id and graph.input_integrity == "VERIFIED":
            available.add(("DATASET_VERSION", str(graph.dataset_version_id)))
        if graph.manifest_sha256 and graph.result_integrity == "VERIFIED":
            available.add(("RESULT_MANIFEST", graph.manifest_sha256))
        available.update(
            ("ARTIFACT", str(a.file_record_id))
            for a in graph.artifacts
            if a.file_record_id and a.integrity == "VERIFIED"
        )
        # Source URLs and article prose are not independently fact-checked by this adapter.
        return assess_claim(claim, available)

    async def cell(
        self,
        owner: UUID,
        project: UUID,
        request: ArtifactCellRequest,
    ) -> dict[str, Any]:
        require_plan_enabled()
        service = ResearchProvenanceService(self.db)
        graph = await service.task(owner, request.task_id)
        if graph.project_id != project:
            raise NotFoundError("Task 不属于当前项目")
        if (
            graph.result_integrity != "VERIFIED"
            or graph.input_integrity != "VERIFIED"
            or graph.compute_state not in {"success", "completed"}
        ):
            raise ValidationError("统计结果缺少已核验产物", code="STATISTICAL_EVIDENCE_REQUIRED")
        matching = [
            (path, artifact)
            for path, artifact in service._verified_paths
            if artifact.file_record_id == request.file_record_id and path.name == "deg.tsv"
        ]
        if len(matching) != 1:
            raise NotFoundError("未找到已核验的差异分析表")
        path, artifact = matching[0]
        with open_owned_file(path, get_path_factory().user_root(str(owner))) as stream:
            before = os.fstat(stream.fileno())
            content = stream.read(get_settings().research_artifact_max_bytes + 1)
            after = os.fstat(stream.fileno())
        if (
            len(content) > get_settings().research_artifact_max_bytes
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or hashlib.sha256(content).hexdigest() != artifact.sha256
        ):
            raise ValidationError("产物在读取期间变化", code="ARTIFACT_CHANGED")
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter="\t")
            if (
                reader.fieldnames is None
                or len(set(reader.fieldnames)) != len(reader.fieldnames)
                or "gene_id" not in reader.fieldnames
                or request.column not in reader.fieldnames
            ):
                raise ValueError("invalid schema")
            matched = None
            for line_number, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("ragged table row")
                if row.get("gene_id") == request.feature_id:
                    if matched is not None:
                        raise ValueError("ambiguous feature")
                    raw = row.get(request.column)
                    value = None if raw in {None, "", "NA"} else float(raw)
                    if value is not None and not math.isfinite(value):
                        raise ValueError("nonfinite result")
                    matched = {"row": line_number, "value": value}
            if matched is None:
                raise NotFoundError("结果中没有该 feature")
        except (UnicodeError, ValueError, csv.Error) as exc:
            raise ValidationError("结果表不能安全解释", code="STATISTICAL_TABLE_INVALID") from exc
        return {
            "task_id": str(request.task_id),
            "project_id": str(project),
            "file_record_id": str(request.file_record_id),
            "sha256": artifact.sha256,
            "feature_id": request.feature_id,
            "column": request.column,
            **matched,
            "analysis_parameters": graph.analysis_parameters,
            "result_observation_id": str(graph.result_observation_id)
            if graph.result_observation_id
            else None,
            "scope": "verified_artifact_cell_not_causal_inference",
            "gaps": ["STATISTICAL_VALUE_MISSING"] if matched["value"] is None else [],
        }
