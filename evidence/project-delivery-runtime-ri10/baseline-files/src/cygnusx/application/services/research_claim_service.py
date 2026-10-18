"""Ground references and read statistical values from actual verified output bytes."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import os
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.research_claims import (
    ArtifactCellRequest,
    ClaimAssessment,
    ClaimDraft,
)
from cygnusx.application.services.research_plan_service import require_plan_enabled
from cygnusx.application.services.research_provenance_service import ResearchProvenanceService
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import NotFoundError, ValidationError
from cygnusx.domain.dataset.validation import open_owned_file
from cygnusx.domain.research.scientific_validation import assess_claim
from cygnusx.infrastructure.storage import get_path_factory


class ResearchClaimService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
