"""Bounded project delivery over existing provenance, reports and frozen snapshots.

No report generation, workflow submission, source download or historical backfill.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.project_delivery import (
    CreateProjectExport,
    DeliveryFile,
    DeliveryReference,
    ExportSelection,
    ExportSelectionV2,
    ProjectDeliveryManifest,
    ProjectDeliveryManifestV2,
    ProjectExportStatus,
    parse_delivery_manifest,
)
from cygnusx.application.services.research_provenance_service import (
    ResearchProvenanceService,
    require_research_read,
)
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cygnusx.domain.dataset.validation import open_owned_file
from cygnusx.domain.project_delivery_archive import canonical, verify_archive
from cygnusx.infrastructure.database.models.file import FileRecordModel
from cygnusx.infrastructure.database.models.project_export import (
    ProjectExportJobModel,
    ProjectExportRequestModel,
)
from cygnusx.infrastructure.database.models.report import (
    ReportFileModel,
    ReportModel,
    ReportSnapshotModel,
)
from cygnusx.infrastructure.database.repositories.dataset_repository import DatasetRepository
from cygnusx.infrastructure.storage import get_path_factory, get_storage_backend

README = b"""# Project research delivery

Only explicitly associated, already existing research outputs are included.
Large raw sequencing files are reference-only. Missing evidence is listed in
ProjectDeliveryManifest.json; missing files have no placeholder bytes.
This archive does not establish scientific reproducibility. Reproduction: NOT_RUN.
Existing reports and their historical versions remain unchanged.

Offline verification (Python 3.11+, standard library only):
    python verify_project_delivery.py project-delivery.zip
You can additionally compare the downloaded ZIP SHA-256 with the authenticated
job status. Checksums are integrity checks, not digital signatures.
"""
ACTIVE = ("queued", "collecting", "validating", "packaging", "verifying", "publishing")


def export_enabled() -> None:
    require_research_read()
    if not get_settings().project_export_enabled:
        raise AuthorizationError("Project export is not enabled", code="FEATURE_DISABLED")


def verifier_bytes() -> bytes:
    from cygnusx.domain import project_delivery_archive

    return Path(project_delivery_archive.__file__).read_bytes()


def read_bounded(path: Path, owner: UUID, maximum: int) -> bytes:
    with open_owned_file(path, get_path_factory().user_root(str(owner))) as stream:
        before = os.fstat(stream.fileno())
        if before.st_size > maximum:
            raise ValidationError("Project export file budget exceeded", code="EXPORT_LIMIT")
        content = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        if (
            len(content) != before.st_size
            or len(content) > maximum
            or (before.st_ino, before.st_mtime_ns, before.st_ctime_ns, before.st_size)
            != (after.st_ino, after.st_mtime_ns, after.st_ctime_ns, after.st_size)
        ):
            raise ConflictError("File changed during export", code="EXPORT_DRIFT")
        return content


class ProjectDeliveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DatasetRepository(db)

    async def authorize(self, owner: UUID, project: UUID, *, lock: bool = False) -> Any:
        require_research_read()
        from cygnusx.infrastructure.database.models.user import UserModel

        # Bypass identity cache when rechecking module revocation across stage commits.
        await self.db.get(UserModel, owner, populate_existing=True)
        await self.repo.require_module(owner, "reports")
        await self.repo.require_module(owner, "tasks")
        await self.repo.project(owner, project, lock=lock)
        from cygnusx.infrastructure.database.models.project import ProjectModel

        row = await self.db.get(ProjectModel, project, populate_existing=True)
        if row is None or row.user_id != owner:
            raise NotFoundError("Project unavailable")
        if row.status not in {None, "active", "completed", "handed_over"}:
            raise AuthorizationError("Project is inactive", code="PROJECT_INACTIVE")
        return row

    async def validate_associations(self, manifest: ProjectDeliveryManifest | ProjectDeliveryManifestV2) -> None:
        from cygnusx.infrastructure.database.models.dataset import (
            DatasetAnalysisLinkModel,
            DatasetModel,
            DatasetVersionModel,
        )
        from cygnusx.infrastructure.database.models.task import TaskModel

        if isinstance(manifest, ProjectDeliveryManifestV2):
            from cygnusx.application.services.project_report_delivery import (
                validate_report_delivery,
            )

            await validate_report_delivery(self, manifest)
        expected = {
            ref.id: (ref.dataset_version_id, ref.analysis_link_id)
            for ref in manifest.references
            if ref.kind == "task" and ref.id is not None
        }
        for task_id in manifest.selection.task_ids:
            rows = (
                await self.db.execute(
                    select(DatasetVersionModel.id, DatasetAnalysisLinkModel.id)
                    .join(DatasetModel, DatasetModel.id == DatasetVersionModel.dataset_id)
                    .join(
                        DatasetAnalysisLinkModel,
                        DatasetAnalysisLinkModel.version_id == DatasetVersionModel.id,
                    )
                    .join(TaskModel, TaskModel.id == DatasetAnalysisLinkModel.task_id)
                    .where(
                        TaskModel.id == task_id,
                        TaskModel.user_id == manifest.owner_id,
                        DatasetModel.user_id == manifest.owner_id,
                        DatasetModel.project_id == manifest.project_id,
                    )
                )
            ).all()
            if len(rows) != 1 or (rows[0][0], rows[0][1]) != expected.get(task_id):
                raise ConflictError("Task project association changed", code="EXPORT_DRIFT")
        for ref in manifest.references:
            if ref.kind != "report" or ref.disposition != "reference_only":
                continue
            report = await self.db.get(ReportModel, ref.id, populate_existing=True)
            if (
                not report
                or report.user_id != manifest.owner_id
                or report.task_id != ref.task_id
                or (
                    report.version,
                    report.snapshot_id,
                    report.result_observation_id,
                    report.parent_id,
                )
                != (ref.version, ref.snapshot_id, ref.result_observation_id, ref.parent_id)
            ):
                raise ConflictError("Frozen report association changed", code="EXPORT_DRIFT")

    async def inventory(self, owner: UUID, project: UUID) -> dict[str, Any]:
        await self.authorize(owner, project)
        graph = await ResearchProvenanceService(self.db).project(
            owner, project, tolerate_unavailable=True
        )
        # Enrich only this new inventory DTO. Do not change historical snapshot DTO defaults.
        report_refs = [
            r for d in graph["datasets"] for a in d["analyses"] for r in a.get("reports", [])
        ]
        ids = {UUID(r["report_id"]) for r in report_refs}
        if ids:
            version_rows = await self.db.execute(
                select(ReportModel.id, ReportModel.version).where(
                    ReportModel.user_id == owner, ReportModel.id.in_(ids)
                )
            )
            versions = {row[0]: row[1] for row in version_rows.all()}
            for report in report_refs:
                report["version"] = versions.get(UUID(report["report_id"]))
        return {
            **graph,
            "association_status": "PARTIAL_ASSOCIATION"
            if graph["truncated"]
            or any(
                a.get("association_status") == "UNAVAILABLE"
                for d in graph["datasets"]
                for a in d["analyses"]
            )
            else "VERIFIED_ASSOCIATION",
            "association_scope": "explicit_dataset_links_only",
            "historical_tasks": {"status": "NOT_RECORDED", "reason": "NO_PROJECT_FK_NO_BACKFILL"},
            "export_enabled": get_settings().project_export_enabled,
        }

    async def prepare(
        self, owner: UUID, project: UUID, selection: ExportSelection | ExportSelectionV2
    ) -> ProjectDeliveryManifest | ProjectDeliveryManifestV2:
        if isinstance(selection, ExportSelectionV2):
            from cygnusx.application.services.project_report_delivery import prepare_report_delivery

            return await prepare_report_delivery(self, owner, project, selection)
        graph = await self.inventory(owner, project)
        if graph["truncated"]:
            raise ValidationError(
                "Project inventory exceeds first release capacity", code="EXPORT_LIMIT"
            )
        analyses = {
            UUID(a["task_id"]): a
            for d in graph["datasets"]
            for a in d["analyses"]
            if a.get("task_id")
        }
        selected = set(selection.task_ids) if selection.task_ids else set(analyses)
        if not selected.issubset(analyses):
            raise NotFoundError("Selection has no trusted project association")
        normalized = selection.model_copy(
            update={
                "task_ids": tuple(sorted(selected)),
                "report_ids": tuple(sorted(selection.report_ids)),
            }
        )
        refs = [DeliveryReference(kind="project", id=project)]
        refs.append(
            DeliveryReference(
                kind="historical_association",
                status="NOT_RECORDED",
                disposition="unverified",
                reason="NO_PROJECT_FK_NO_BACKFILL",
            )
        )
        gaps: set[str] = {"HISTORICAL_ASSOCIATION_COVERAGE_NOT_RECORDED", "REPRODUCTION_NOT_RUN"}
        for dataset in graph["datasets"]:
            for analysis in dataset["analyses"]:
                if not analysis.get("task_id"):
                    gaps.update(analysis.get("gaps", ["TASK_NOT_CREATED"]))
                    refs.append(
                        DeliveryReference(
                            kind="task",
                            status="UNAVAILABLE"
                            if analysis.get("association_status") == "UNAVAILABLE"
                            else "NOT_RECORDED",
                            disposition="missing",
                            reason="LINKED_TASK_UNAVAILABLE_OR_NOT_CREATED",
                        )
                    )
        files: list[DeliveryFile] = []
        found_reports: set[UUID] = set()
        for dataset in graph["datasets"]:
            if not selection.task_ids or any(
                a.get("task_id") and UUID(a["task_id"]) in selected for a in dataset["analyses"]
            ):
                refs.append(
                    DeliveryReference(
                        kind="dataset_version",
                        id=UUID(dataset["dataset_version_id"]),
                        digest=dataset.get("handoff_hash"),
                    )
                )
        snapshot_paths: dict[UUID, str] = {}
        for task_index, task_id in enumerate(sorted(selected), 1):
            task_prefix = f"analyses/analysis-{task_index:03d}"
            analysis = analyses[task_id]
            if analysis.get("project_id") != str(project):
                raise ConflictError("Project association changed", code="EXPORT_DRIFT")
            refs.append(
                DeliveryReference(
                    kind="task",
                    id=task_id,
                    task_id=task_id,
                    dataset_version_id=UUID(analysis["dataset_version_id"]),
                    analysis_link_id=UUID(analysis["analysis_link_id"]),
                )
            )
            gaps.update(f"{task_id}:{gap}" for gap in analysis["gaps"])
            for kind, field in (("run", "run_id"), ("result_observation", "result_observation_id")):
                refs.append(
                    DeliveryReference(
                        kind=kind,
                        id=UUID(analysis[field]) if analysis.get(field) else None,
                        task_id=task_id,
                        status="VERIFIED_ASSOCIATION" if analysis.get(field) else "NOT_RECORDED",
                    )
                )
            for item in analysis["inputs"]:
                refs.append(
                    DeliveryReference(
                        kind="file_record",
                        id=UUID(item["file_record_id"]) if item.get("file_record_id") else None,
                        task_id=task_id,
                        reason="RAW_INPUT_REFERENCE_ONLY",
                        digest=item.get("sha256"),
                    )
                )
            reports = list(
                (
                    await self.db.scalars(
                        select(ReportModel)
                        .where(ReportModel.task_id == task_id, ReportModel.user_id == owner)
                        .order_by(ReportModel.id)
                        .limit(201)
                    )
                ).all()
            )
            if len(reports) > 200:
                raise ValidationError("Too many report versions", code="EXPORT_LIMIT")
            kinds = set()
            for report_index, report in enumerate(reports, 1):
                if normalized.report_ids and report.id not in normalized.report_ids:
                    continue
                found_reports.add(report.id)
                kinds.add(report.report_kind)
                refs.append(
                    DeliveryReference(
                        kind="report",
                        id=report.id,
                        task_id=task_id,
                        version=report.version,
                        snapshot_id=report.snapshot_id,
                        result_observation_id=report.result_observation_id,
                        parent_id=report.parent_id,
                    )
                )
                if (
                    report.report_kind not in {"scientific", "reproducibility", "delivery"}
                    or report.status != "completed"
                ):
                    refs.append(
                        DeliveryReference(
                            kind="report",
                            id=report.id,
                            task_id=task_id,
                            disposition="excluded",
                            reason="REPORT_NOT_PUBLISHED",
                        )
                    )
                    gaps.add(f"{report.id}:REPORT_NOT_PUBLISHED")
                    continue
                if report.evidence_partial:
                    gaps.add(f"{report.id}:REPORT_PARTIAL")
                if report.result_observation_id:
                    from cygnusx.infrastructure.database.models.result_observation import (
                        ResultObservationModel,
                    )

                    observation = await self.db.get(
                        ResultObservationModel, report.result_observation_id
                    )
                    if (
                        not observation
                        or observation.user_id != owner
                        or observation.task_id != task_id
                        or observation.project_id != project
                    ):
                        raise ConflictError("Report observation identity mismatch")
                    refs.append(
                        DeliveryReference(
                            kind="result_observation",
                            id=observation.id,
                            task_id=task_id,
                            digest=observation.evidence_digest,
                        )
                    )
                if report.snapshot_id:
                    snapshot = await self.db.get(ReportSnapshotModel, report.snapshot_id)
                    if not snapshot or snapshot.user_id != owner or snapshot.task_id != task_id:
                        raise ConflictError("Snapshot identity mismatch")
                    from cygnusx.application.services.reproducible_report_service import (
                        validate_snapshot_row,
                    )

                    validate_snapshot_row(snapshot)
                    content = canonical(snapshot.payload)
                    refs.append(
                        DeliveryReference(
                            kind="report_snapshot",
                            id=snapshot.id,
                            task_id=task_id,
                            digest=snapshot.snapshot_digest,
                        )
                    )
                    name = snapshot_paths.setdefault(
                        snapshot.id, f"{task_prefix}/snapshots/snapshot-{report_index:03d}.json"
                    )
                    if not any(f.path == name for f in files):
                        files.append(
                            self.file(name, "report_snapshot", snapshot.id, task_id, content)
                        )
                else:
                    gaps.add(f"{report.id}:REPORT_SNAPSHOT_MISSING")
                    refs.append(
                        DeliveryReference(
                            kind="report_snapshot",
                            task_id=task_id,
                            status="NOT_RECORDED",
                            disposition="missing",
                            reason="REPORT_SNAPSHOT_MISSING",
                        )
                    )
                report_files = list(
                    (
                        await self.db.scalars(
                            select(ReportFileModel)
                            .where(ReportFileModel.report_id == report.id)
                            .order_by(ReportFileModel.id)
                            .limit(201)
                        )
                    ).all()
                )
                if len(report_files) > 200:
                    raise ValidationError("Report file budget", code="EXPORT_LIMIT")
                if not report_files:
                    gaps.add(f"{report.id}:REPORT_FILES_MISSING")
                for file_index, source in enumerate(report_files, 1):
                    ext = Path(source.name).suffix.lower()
                    if ext not in {".html", ".pdf", ".json", ".md", ".zip", ".png", ".svg"}:
                        refs.append(
                            DeliveryReference(
                                kind="report",
                                id=report.id,
                                task_id=task_id,
                                disposition="excluded",
                                reason="FILE_TYPE_EXCLUDED",
                            )
                        )
                        continue
                    name = f"{task_prefix}/reports/report-{report_index:03d}/file-{file_index:03d}{ext}"
                    try:
                        content = await self.source_bytes(owner, selected, "report_file", source.id)
                        if source.sha256 is None:
                            gaps.add(f"{source.id}:LEGACY_FINGERPRINT_CAPTURE_TIME_ONLY")
                        if ext == ".zip":
                            import tempfile

                            from cygnusx.application.services.research_delivery_service import (
                                ResearchDeliveryBuilder,
                            )

                            with tempfile.TemporaryDirectory() as directory:
                                nested = Path(directory) / "delivery.zip"
                                nested.write_bytes(content)
                                evidence = ResearchDeliveryBuilder.verify_package(nested)
                                with zipfile.ZipFile(nested) as package:
                                    allowed = {
                                        "Scientific_Report.html",
                                        "Scientific_Report.pdf",
                                        "Reproducibility_Record.html",
                                        "Reproducibility_Record.pdf",
                                        "ReportSnapshot.json",
                                        "README.md",
                                        "EvidenceManifest.json",
                                        "checksums.sha256",
                                    }
                                    if not set(package.namelist()).issubset(allowed):
                                        raise ValidationError(
                                            "Nested delivery contains excluded content",
                                            code="EXPORT_CONTENT_EXCLUDED",
                                        )
                                    evidence_digest = hashlib.sha256(
                                        package.read("EvidenceManifest.json")
                                    ).hexdigest()
                            if evidence.task_id != task_id:
                                raise ConflictError("Evidence manifest task mismatch")
                            if evidence.snapshot_id != report.snapshot_id:
                                raise ConflictError("Evidence manifest snapshot mismatch")
                            refs.append(
                                DeliveryReference(
                                    kind="evidence_manifest",
                                    id=report.id,
                                    task_id=task_id,
                                    digest=evidence_digest,
                                )
                            )
                            if evidence.evidence_status != "complete":
                                gaps.add(f"{report.id}:EVIDENCE_MANIFEST_PARTIAL")
                        files.append(self.file(name, "report_file", source.id, task_id, content))
                    except (OSError, ValidationError) as exc:
                        # A known missing source permits partial; policy/budget failures do not.
                        if isinstance(exc, ValidationError) and exc.code not in {"UNSAFE_FILE"}:
                            raise
                        refs.append(
                            DeliveryReference(
                                kind="report",
                                id=report.id,
                                task_id=task_id,
                                status="UNAVAILABLE",
                                disposition="missing",
                                reason="REPORT_FILE_UNAVAILABLE",
                            )
                        )
                        gaps.add(f"{source.id}:REPORT_FILE_UNAVAILABLE")
                self.budget(files)
            for kind in {"scientific", "reproducibility"} - kinds:
                gaps.add(f"{task_id}:{kind.upper()}_REPORT_MISSING")
            if normalized.kind == "results":
                for artifact_index, artifact in enumerate(analysis["artifacts"], 1):
                    if not artifact.get("file_record_id"):
                        gaps.add(f"{task_id}:RESULT_FILE_NOT_REGISTERED")
                        continue
                    source_id = UUID(artifact["file_record_id"])
                    record = await self.db.get(FileRecordModel, source_id, populate_existing=True)
                    if not record:
                        gaps.add(f"{source_id}:RESULT_FILE_MISSING")
                        continue
                    ext = Path(record.original_name).suffix.lower()
                    if (
                        ext not in {".tsv", ".csv", ".json", ".png", ".pdf", ".svg"}
                        or artifact["integrity"] != "VERIFIED"
                    ):
                        refs.append(
                            DeliveryReference(
                                kind="file_record",
                                id=source_id,
                                task_id=task_id,
                                disposition="excluded",
                                reason="RAW_OR_UNVERIFIED_RESULT_EXCLUDED",
                            )
                        )
                        continue
                    content = await self.source_bytes(owner, selected, "file_record", source_id)
                    files.append(
                        self.file(
                            f"{task_prefix}/results/result-{artifact_index:03d}{ext}",
                            "file_record",
                            source_id,
                            task_id,
                            content,
                        )
                    )
                    self.budget(files)
        if normalized.report_ids and found_reports != set(normalized.report_ids):
            raise NotFoundError("Report selection outside trusted project tasks")
        files += [
            self.file("README.md", "instructions", None, None, README),
            self.file("verify_project_delivery.py", "verifier", None, None, verifier_bytes()),
        ]
        self.budget(files)
        # Sort every unordered collection once. The frozen digest includes the exact selection.
        unique_refs = {canonical(r.model_dump(mode="json")): r for r in refs}
        return ProjectDeliveryManifest(
            project_id=project,
            owner_id=owner,
            selection=normalized,
            files=tuple(sorted(files, key=lambda f: f.path)),
            references=tuple(unique_refs[k] for k in sorted(unique_refs)),
            gaps=tuple(sorted(gaps)),
        )

    @staticmethod
    def file(
        name: str, kind: Any, source: UUID | None, task: UUID | None, content: bytes
    ) -> DeliveryFile:
        return DeliveryFile(
            path=name,
            source_kind=kind,
            source_id=source,
            task_id=task,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    @staticmethod
    def budget(files: list[DeliveryFile] | tuple[DeliveryFile, ...]) -> None:
        settings = get_settings()
        if (
            len(files) > settings.project_export_max_files
            or sum(f.size for f in files) > settings.project_export_max_bytes
            or any(f.size > settings.project_export_file_max_bytes for f in files)
        ):
            raise ValidationError(
                "First release project export capacity exceeded", code="EXPORT_LIMIT"
            )

    async def source_bytes(
        self, owner: UUID, tasks: set[UUID], kind: str, source_id: UUID | None
    ) -> bytes:
        if kind == "instructions":
            return README
        if kind == "verifier":
            return verifier_bytes()
        limit = get_settings().project_export_file_max_bytes
        if kind == "report_snapshot":
            row = await self.db.get(ReportSnapshotModel, source_id, populate_existing=True)
            if not row or row.user_id != owner or row.task_id not in tasks:
                raise NotFoundError("Snapshot unavailable")
            from cygnusx.application.services.reproducible_report_service import (
                validate_snapshot_row,
            )

            validate_snapshot_row(row)
            return canonical(row.payload)
        if kind == "report_file":
            file = await self.db.get(ReportFileModel, source_id, populate_existing=True)
            if file and file.project_report_job_id:
                from cygnusx.application.services.project_report_service import ProjectReportService
                from cygnusx.infrastructure.database.models.project_report import (
                    ProjectReportJobModel,
                )

                job = await self.db.get(ProjectReportJobModel, file.project_report_job_id)
                if not job or job.user_id != owner:
                    raise NotFoundError("Project report unavailable")
                return await ProjectReportService(self.db).download(owner, job.project_id, job.id, file.type)
            report = (
                await self.db.get(ReportModel, file.report_id, populate_existing=True)
                if file
                else None
            )
            if (
                not file
                or not report
                or report.user_id != owner
                or report.task_id not in tasks
                or report.status != "completed"
            ):
                raise NotFoundError("Report unavailable")
            path, size, sha = Path(file.path), file.size, file.sha256
            if file.file_record_id:
                record = await self.db.get(
                    FileRecordModel, file.file_record_id, populate_existing=True
                )
                if (
                    not record
                    or record.user_id != owner
                    or record.owner_scope != "personal"
                    or record.status != "active"
                    or record.lifecycle_status != "active"
                ):
                    raise NotFoundError("Report file registration unavailable")
                expected_path = get_path_factory().data_root / record.storage_path
                actual_path = path if path.is_absolute() else get_path_factory().data_root / path
                if (
                    actual_path != expected_path
                    or record.size != size
                    or record.checksum
                    and sha
                    and record.checksum != sha
                ):
                    raise ConflictError("Report registration mismatch")
        else:
            record = await self.db.get(FileRecordModel, source_id, populate_existing=True)
            if (
                not record
                or record.user_id != owner
                or record.task_id not in tasks
                or record.owner_scope != "personal"
                or record.status != "active"
                or record.lifecycle_status != "active"
            ):
                raise NotFoundError("Result file unavailable")
            path, size, sha = Path(record.storage_path), record.size, record.checksum
        if size > limit:
            raise ValidationError("File capacity exceeded", code="EXPORT_LIMIT")
        path = path if path.is_absolute() else get_path_factory().data_root / path
        content = await asyncio.to_thread(read_bounded, path, owner, limit)
        if len(content) != size or sha and hashlib.sha256(content).hexdigest() != sha:
            raise ConflictError("Registered file content drifted", code="EXPORT_DRIFT")
        return content

    async def create(
        self, owner: UUID, project: UUID, request: CreateProjectExport
    ) -> ProjectExportJobModel:
        export_enabled()
        await self.authorize(owner, project, lock=True)
        existing = (
            await self.db.scalars(
                select(ProjectExportJobModel)
                .join(
                    ProjectExportRequestModel,
                    ProjectExportRequestModel.job_id == ProjectExportJobModel.id,
                )
                .where(
                    ProjectExportRequestModel.user_id == owner,
                    ProjectExportRequestModel.project_id == project,
                    ProjectExportRequestModel.request_key == str(request.request_key),
                )
            )
        ).one_or_none()
        if existing:
            if existing.manifest_digest != request.manifest_digest:
                raise ConflictError("Request key already binds another scope", code="EXPORT_DRIFT")
            return existing
        manifest = await self.prepare(owner, project, request.selection)
        if manifest.content_digest() != request.manifest_digest:
            raise ConflictError("Preview changed; review scope again", code="EXPORT_DRIFT")
        existing = (
            await self.db.scalars(
                select(ProjectExportJobModel).where(
                    ProjectExportJobModel.user_id == owner,
                    ProjectExportJobModel.project_id == project,
                    ProjectExportJobModel.manifest_digest == request.manifest_digest,
                )
            )
        ).one_or_none()
        if existing:
            self.db.add(
                ProjectExportRequestModel(
                    user_id=owner,
                    project_id=project,
                    request_key=str(request.request_key),
                    job_id=existing.id,
                )
            )
            await self.db.commit()
            return existing
        job = ProjectExportJobModel(
            user_id=owner,
            project_id=project,
            request_key=str(request.request_key),
            manifest_digest=manifest.content_digest(),
            manifest=manifest.model_dump(mode="json"),
            status="queued",
        )
        self.db.add(job)
        await self.db.flush()
        self.db.add(
            ProjectExportRequestModel(
                user_id=owner,
                project_id=project,
                request_key=str(request.request_key),
                job_id=job.id,
            )
        )
        await self.db.commit()  # Durable outbox; broker outage leaves a recoverable queued row.
        await dispatch_export(job.id)
        return job

    async def job(self, owner: UUID, project: UUID, job_id: UUID) -> ProjectExportJobModel:
        export_enabled()
        await self.authorize(owner, project)
        job = await self.db.get(ProjectExportJobModel, job_id)
        if not job or job.user_id != owner or job.project_id != project:
            raise NotFoundError("Project export not found")
        return job

    @staticmethod
    def status(job: ProjectExportJobModel) -> ProjectExportStatus:
        return ProjectExportStatus.model_validate(
            {
                key: getattr(job, key)
                for key in ProjectExportStatus.model_fields
                if key != "evidence_partial"
            }
            | {"evidence_partial": job.manifest.get("evidence_status") != "complete"}
        )

    async def download(self, owner: UUID, project: UUID, job_id: UUID) -> bytes:
        export_enabled()
        job = await self.job(owner, project, job_id)
        frozen = parse_delivery_manifest(job.manifest)
        if (
            frozen.content_digest() != job.manifest_digest
            or frozen.owner_id != owner
            or frozen.project_id != project
        ):
            raise ConflictError("Frozen manifest integrity failed")
        await self.validate_associations(frozen)
        if job.status != "ready" or not job.archive_path or not job.file_record_id:
            raise ConflictError("Export is not ready")
        record = await self.db.get(FileRecordModel, job.file_record_id, populate_existing=True)
        if (
            not record
            or record.user_id != owner
            or record.storage_path != job.archive_path
            or record.owner_scope != "personal"
            or record.status != "active"
            or record.lifecycle_status != "active"
            or record.checksum != job.archive_sha256
            or record.size != job.archive_size
        ):
            raise ConflictError("Export registration unavailable")
        cap = get_settings().project_export_archive_max_bytes
        if job.archive_size is None or job.archive_size > cap:
            raise ValidationError("Archive capacity exceeded", code="EXPORT_LIMIT")
        backend, factory = get_storage_backend(), get_path_factory()
        if backend.name == "local":
            content = await asyncio.to_thread(
                read_bounded, factory.data_root / job.archive_path, owner, cap
            )
        else:
            content = await backend.read(job.archive_path, limit=cap + 1)
        if (
            len(content) != job.archive_size
            or hashlib.sha256(content).hexdigest() != job.archive_sha256
        ):
            raise ConflictError("Export archive drifted", code="EXPORT_DRIFT")
        document = verify_archive(
            io.BytesIO(content), max_bytes=get_settings().project_export_archive_max_bytes
        )
        if document["manifest_digest"] != job.manifest_digest:
            raise ConflictError("Export manifest mismatch")
        await self.authorize(owner, project)
        return content


async def dispatch_export(job_id: UUID) -> None:
    from cygnusx.infrastructure.celery_app.tasks.project_exports import generate_project_export

    try:
        await asyncio.to_thread(
            generate_project_export.apply_async, args=[str(job_id)], retry=False
        )
    except Exception:
        logger.warning("Project export remains queued for reconciliation: {}", job_id)


async def run_project_export(db: AsyncSession, job_id: UUID) -> None:
    """Caller holds a dedicated per-job advisory lock across all commits."""
    export_enabled()
    job = await db.get(ProjectExportJobModel, job_id)
    if job is None or job.status == "ready" or job.status == "failed" and not job.retryable:
        return
    settings = get_settings()
    if job.attempt_count >= settings.project_export_max_attempts:
        job.status, job.retryable, job.error_code = "failed", False, "EXPORT_ATTEMPTS_EXHAUSTED"
        await db.commit()
        return
    service = ProjectDeliveryService(db)
    project = await service.authorize(job.user_id, job.project_id)
    manifest = parse_delivery_manifest(job.manifest)
    if (
        manifest.content_digest() != job.manifest_digest
        or manifest.project_id != job.project_id
        or manifest.owner_id != job.user_id
    ):
        raise ConflictError("Frozen export scope corrupted")
    await service.validate_associations(manifest)
    job.attempt_count += 1
    job.status, job.retryable, job.error_code = "collecting", False, None
    await db.commit()
    service.budget(manifest.files)
    content_by_name = {}
    for file in manifest.files:
        content = await service.source_bytes(
            job.user_id, set(manifest.selection.task_ids), file.source_kind, file.source_id
        )
        if len(content) != file.size or hashlib.sha256(content).hexdigest() != file.sha256:
            raise ConflictError("Frozen export content changed", code="EXPORT_DRIFT")
        content_by_name[file.path] = content
    job.status = "validating"
    await db.commit()
    document = {
        "manifest": manifest.model_dump(mode="json"),
        "manifest_digest": job.manifest_digest,
    }
    content_by_name["ProjectDeliveryManifest.json"] = canonical(document)
    hashes = {
        name: hashlib.sha256(content).hexdigest() for name, content in content_by_name.items()
    }
    content_by_name["checksums.sha256"] = "".join(
        f"{hashes[name]}  {name}\n" for name in sorted(hashes)
    ).encode()
    if sum(map(len, content_by_name.values())) > settings.project_export_archive_max_bytes:
        raise ValidationError("Archive capacity exceeded", code="EXPORT_LIMIT")
    job.status = "packaging"
    await db.commit()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(content_by_name):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content_by_name[name])
    content_by_name.clear()
    data = output.getvalue()
    if len(data) > settings.project_export_archive_max_bytes:
        raise ValidationError("Archive capacity exceeded", code="EXPORT_LIMIT")
    job.status = "verifying"
    await db.commit()
    verify_archive(io.BytesIO(data), max_bytes=settings.project_export_archive_max_bytes)
    await service.authorize(job.user_id, job.project_id)
    await service.validate_associations(manifest)
    factory = get_path_factory()
    if job.archive_path is None:
        run = factory.create_project_run_dir(str(job.user_id), project.slug, "research-delivery")
        job.archive_path = (
            (run / "output/project-delivery.zip").relative_to(factory.data_root).as_posix()
        )
    job.status = "publishing"
    await db.commit()
    from cygnusx.application.services.file_service import ensure_directory_chain
    from cygnusx.application.services.report_archive import publish_archive
    from cygnusx.domain.file.value_objects import FileSource
    from cygnusx.infrastructure.storage.file_registry import FileRegistry

    directory = (
        (factory.data_root / job.archive_path)
        .parent.relative_to(factory.user_root(str(job.user_id)))
        .as_posix()
    )
    await ensure_directory_chain(db, job.user_id, directory)
    from cygnusx.core.exceptions import QuotaExceededError
    from cygnusx.infrastructure.database.models.user import UserModel

    await db.execute(select(UserModel.id).where(UserModel.id == job.user_id).with_for_update())
    user = await db.get(UserModel, job.user_id, populate_existing=True)
    existing = (
        await db.scalars(
            select(FileRecordModel).where(
                FileRecordModel.user_id == job.user_id,
                FileRecordModel.storage_path == job.archive_path,
            )
        )
    ).one_or_none()
    additional = 0 if existing else len(data)
    if user is None or user.used_storage + additional > user.storage_quota:
        raise QuotaExceededError("Project export storage quota exceeded")
    await publish_archive(get_storage_backend(), factory, job.archive_path, data)
    backend = get_storage_backend()
    if backend.name == "local":
        published = await asyncio.to_thread(
            read_bounded,
            factory.data_root / job.archive_path,
            job.user_id,
            settings.project_export_archive_max_bytes,
        )
    else:
        published = await backend.read(
            job.archive_path, limit=settings.project_export_archive_max_bytes + 1
        )
    sha = hashlib.sha256(data).hexdigest()
    if len(published) != len(data) or hashlib.sha256(published).hexdigest() != sha:
        raise ConflictError("Published export fingerprint mismatch")
    await service.authorize(job.user_id, job.project_id)
    record = await FileRegistry(db).register(
        job.user_id,
        factory.data_root / job.archive_path,
        source=FileSource.REPORT,
        checksum=sha,
        directory=directory,
    )
    if (
        record.user_id != job.user_id
        or record.size != len(data)
        or record.checksum != sha
        or record.status != "active"
        or record.lifecycle_status != "active"
        or record.owner_scope != "personal"
        or record.task_id is not None
        or record.source != "report"
    ):
        raise ConflictError("Published registration mismatch")
    user.used_storage += additional
    job.file_record_id, job.archive_size, job.archive_sha256 = record.id, len(data), sha
    job.status = "ready"
    await db.commit()
