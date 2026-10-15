"""Bounded file verification and versioned input manifests; no analysis submission."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.dataset import DataHandoff, HandoffAsset
from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.dataset_import_service import digest
from cygnusx.application.services.managed_file_resolver import ManagedFileResolver
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import ConflictError, ValidationError
from cygnusx.domain.dataset.validation import (
    ValidationLimits,
    checksum,
    inspect_content,
    inspect_sample_metadata,
    open_owned_file,
)
from cygnusx.infrastructure.database.models.dataset import (
    DatasetAnalysisLinkModel,
    DatasetAssetModel,
    DatasetIngestionModel,
    DatasetSampleModel,
    DatasetSourceModel,
)
from cygnusx.infrastructure.database.repositories.dataset_repository import DatasetRepository
from cygnusx.infrastructure.storage import get_path_factory


def validation_limits() -> ValidationLimits:
    settings = get_settings()
    return ValidationLimits(
        max_bytes=settings.dataset_import_max_bytes,
        max_rows=settings.dataset_validation_max_rows,
        max_columns=settings.dataset_validation_max_columns,
        max_line_bytes=settings.dataset_validation_max_line_bytes,
    )


class DatasetHandoffService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DatasetRepository(db)

    async def verify(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> dict[str, Any]:
        version = await self.repo.version(owner, project_id, dataset_id, version_id, mutable=True)
        assets = list(
            (
                await self.db.execute(
                    select(DatasetAssetModel).where(DatasetAssetModel.version_id == version_id)
                )
            )
            .scalars()
            .all()
        )
        samples = list(
            (
                await self.db.execute(
                    select(DatasetSampleModel).where(DatasetSampleModel.version_id == version_id)
                )
            )
            .scalars()
            .all()
        )
        evidence = self._processing_evidence(version.source_snapshot)
        context = ToolInvocationContext(
            user_id=str(owner), session_id="dataset-verification", db=self.db
        )
        factory = get_path_factory()
        for asset in assets:
            record = await self.repo.file(owner, project_id, asset.file_record_id)
            metadata = await ManagedFileResolver().resolve(context, f"file://{record.id}")
            # FileRecord/ManagedFileResolver is authoritative; an arbitrary caller path is never accepted.
            if (
                metadata.internal_path != str((factory.data_root / record.storage_path).resolve())
                or record.storage_backend != "local"
            ):
                raise ValidationError("存储后端或引用尚无验证适配器", code="STORAGE_NOT_VERIFIED")
            if Path(record.storage_path).is_absolute():
                raise ValidationError("FileRecord 必须为受控相对路径", code="PATH_ESCAPE")
            path = factory.data_root / record.storage_path
            try:
                with open_owned_file(path, factory.user_root(str(owner))) as stream:
                    before = os.fstat(stream.fileno())
                    sha256, size = checksum(stream, validation_limits())
                    if size != record.size:
                        raise ValidationError("文件大小与登记不符", code="SIZE_MISMATCH")
                    classification = (
                        inspect_sample_metadata(
                            stream, [s.sample_key for s in samples], limits=validation_limits()
                        )
                        if asset.role == "metadata"
                        else inspect_content(
                            stream,
                            record.original_name,
                            metadata_samples=[s.sample_key for s in samples] or None,
                            source_evidence=evidence,
                            limits=validation_limits(),
                        )
                    )
                    after = os.fstat(stream.fileno())
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ctime_ns,
                    ):
                        raise ConflictError("校验过程中输入发生变化", code="INPUT_CHANGED")
                asset.sha256, asset.size = sha256, size
                asset.checksum_status, asset.availability = "VERIFIED", "AVAILABLE"
                classification["role_review_history"] = asset.classification.get(
                    "role_review_history", []
                )
                asset.classification = classification
                asset.data_type = classification["data_type"]
                asset.compression = (
                    "gzip" if record.original_name.lower().endswith(".gz") else "none"
                )
                asset.format = (
                    "fastq"
                    if asset.data_type == "RAW_FASTQ"
                    else Path(record.original_name.removesuffix(".gz")).suffix.lstrip(".")
                )
            except ValidationError as exc:
                asset.checksum_status, asset.availability = "FAILED", "BLOCKED"
                asset.classification = {
                    "data_type": "UNKNOWN",
                    "status": "BLOCKED",
                    "errors": [exc.code or "VALIDATION_ERROR"],
                }
                asset.data_type = "UNKNOWN"
        await self.db.flush()
        return await self.manifest(owner, project_id, dataset_id, version_id, freeze=False)

    @staticmethod
    def _processing_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
        descriptions = [p for s in snapshot.get("samples", []) for p in s.get("processing", [])]
        refs = snapshot.get("source_evidence", [])
        return {
            "processing_description": "\n".join(descriptions),
            "assay_type": snapshot.get("assay_type", "unknown"),
            "source_url": refs[0].get("url") if refs else None,
            "response_sha256": refs[0].get("response_sha256") if refs else None,
        }

    async def manifest(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        freeze: bool = False,
    ) -> dict[str, Any]:
        version = await self.repo.version(owner, project_id, dataset_id, version_id)
        if version.handoff:
            for asset_ref in version.handoff["assets"]:
                await self.repo.file(owner, project_id, uuid.UUID(asset_ref["file_record_id"]))
            for sample_ref in version.handoff["samples"]:
                await self.repo.sample(owner, uuid.UUID(sample_ref["sample_id"]))
            return dict(version.handoff)
        assets = list(
            (
                await self.db.execute(
                    select(DatasetAssetModel)
                    .where(DatasetAssetModel.version_id == version_id)
                    .order_by(DatasetAssetModel.id)
                )
            )
            .scalars()
            .all()
        )
        samples = list(
            (
                await self.db.execute(
                    select(DatasetSampleModel)
                    .where(DatasetSampleModel.version_id == version_id)
                    .order_by(DatasetSampleModel.sample_key)
                )
            )
            .scalars()
            .all()
        )
        sources = list(
            (
                await self.db.execute(
                    select(DatasetSourceModel)
                    .where(DatasetSourceModel.version_id == version_id)
                    .order_by(DatasetSourceModel.id)
                )
            )
            .scalars()
            .all()
        )
        jobs = list(
            (
                await self.db.execute(
                    select(DatasetIngestionModel)
                    .where(
                        DatasetIngestionModel.version_id == version_id,
                        DatasetIngestionModel.user_id == owner,
                        DatasetIngestionModel.project_id == project_id,
                    )
                    .order_by(DatasetIngestionModel.id)
                )
            )
            .scalars()
            .all()
        )
        dataset = await self.repo.dataset(owner, project_id, dataset_id)
        assay = version.review_annotations.get("assay_type", dataset.assay_type)
        blocking = []
        if assay == "unknown":
            blocking.append("ASSAY_REVIEW_REQUIRED")
        if not assets:
            blocking.append("NO_ASSETS")
        for asset in assets:
            await self.repo.file(owner, project_id, asset.file_record_id)
            if (
                asset.checksum_status != "VERIFIED"
                or not asset.sha256
                or asset.availability != "AVAILABLE"
            ):
                blocking.append("ASSET_NOT_VERIFIED")
            if asset.role != "archive" and (
                asset.data_type == "UNKNOWN" or asset.classification.get("status") != "VALIDATED"
            ):
                blocking.append("SCIENTIFIC_TYPE_NEEDS_REVIEW")
        for sample in samples:
            await self.repo.sample(owner, sample.sample_id)
            if sample.mapping_status != "CONFIRMED" or not sample.user_annotation.get(
                "group_confirmed"
            ):
                blocking.append("SAMPLE_GROUPS_NOT_CONFIRMED")
        if not samples:
            blocking.append("NO_MAPPED_SAMPLES")
        if any(j.state not in {"COMPLETED"} for j in jobs):
            blocking.append("INGESTION_NOT_COMPLETED")
        types = {a.data_type for a in assets if a.role not in {"metadata", "annotation", "archive"}}
        compatible = (
            ["rna_seq"]
            if types == {"RAW_FASTQ"} and assay == "bulk_rnaseq" and not blocking
            else []
        )
        if (
            types == {"RAW_INTEGER_COUNTS"}
            and assay == "bulk_rnaseq"
            and not blocking
            and get_settings().counts_deg_flow_enabled
        ):
            compatible = ["counts_deg"]
        manifest = DataHandoff(
            project_id=project_id,
            dataset_id=dataset_id,
            dataset_version_id=version_id,
            source=[
                {
                    "repository": s.repository,
                    "accession": s.accession,
                    "parent_accession": s.parent_accession,
                    "source_url": s.source_url,
                    "access_status": s.access_status,
                    "evidence": s.evidence,
                }
                for s in sources
            ],
            ingestion=[
                {"job_id": str(j.id), "download_task_ids": j.task_ids, "state": j.state}
                for j in jobs
            ],
            assets=[
                HandoffAsset(
                    asset_id=a.id,
                    file_record_id=a.file_record_id,
                    asset_role=a.role,
                    data_type=a.data_type,
                    format=a.format,
                    size=a.size,
                    sha256=a.sha256,
                    checksum_status=a.checksum_status,
                    availability=a.availability,
                )
                for a in assets
            ],
            samples=[
                {
                    "sample_id": str(s.sample_id),
                    "sample_key": s.sample_key,
                    "source_accessions": s.source_accessions,
                    "file_record_ids": s.file_record_ids,
                    "source_metadata": s.source_metadata,
                    "user_annotation": s.user_annotation,
                    "mapping_status": s.mapping_status,
                }
                for s in samples
            ],
            validation={
                "dataset_ready": not blocking,
                "compatible_flow_ids": compatible,
                "blocking_reasons": sorted(set(blocking)),
                "worker_paths_verified": False,
            },
            provenance={
                "initiated_by": str(version.initiated_by),
                "review_annotations": version.review_annotations,
                "tool_invocation_ids": [str(j.invocation_id) for j in jobs if j.invocation_id],
                "agent_session_ids": [j.agent_session_id for j in jobs if j.agent_session_id],
                "output_state": "NOT_REQUESTED",
            },
        ).model_dump(mode="json")
        manifest["manifest_hash"] = digest(manifest)
        if freeze:
            version.handoff = manifest
            version.asset_fingerprint = digest({"assets": manifest["assets"]})
            version.validation = manifest["validation"]
            version.status = "READY" if not blocking else "REVIEW_REQUIRED"
            await self.db.flush()
        return manifest

    async def provenance(
        self, owner: uuid.UUID, project_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID
    ) -> dict[str, Any]:
        version = await self.repo.version(owner, project_id, dataset_id, version_id)
        links = (
            (
                await self.db.execute(
                    select(DatasetAnalysisLinkModel).where(
                        DatasetAnalysisLinkModel.version_id == version_id
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            "dataset_version_id": str(version.id),
            "handoff": version.handoff,
            "analysis_tasks": [
                {
                    "task_id": str(link.task_id) if link.task_id else None,
                    "analysis_proposal_id": str(link.id),
                    "state": link.state,
                    "flow_id": link.flow_id,
                    "handoff_hash": link.handoff_hash,
                    "result_manifest_status": "UNKNOWN",
                    "report_status": "UNKNOWN",
                }
                for link in links
            ],
        }
