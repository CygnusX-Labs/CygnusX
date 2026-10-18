"""Import proposals reuse existing approval, DownloadService and real Task state.

Execution is source-gated by Phase2 plus independent Phase3 flags. No Agent can
self-certify a GEO transport/Worker or convert metadata into Dataset READY.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.dataset import DatasetCreate, ImportPrepare
from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.services.agent_tool_gateway import require_agent_write_gate
from cygnusx.application.services.dataset_service import DatasetService
from cygnusx.application.services.download_service import DownloadService
from cygnusx.application.services.task_service import TaskService
from cygnusx.application.services.tool_confirmation_service import (
    ConfirmationRecord,
    get_tool_confirmation_service,
)
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cygnusx.infrastructure.database.models.dataset import (
    DatasetIngestionModel,
    DatasetVersionModel,
)
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.infrastructure.database.repositories.dataset_repository import DatasetRepository
from cygnusx.infrastructure.geo.adapter import GeoMetadataAdapter, accession, trusted_url
from cygnusx.infrastructure.storage import get_path_factory


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def require_dataset_read() -> None:
    if not get_settings().dataset_discovery_readonly:
        raise AuthorizationError("Dataset 功能未启用", code="FEATURE_DISABLED")


def require_import_write() -> None:
    # Must run before any confirmation consume, directory, SQL mutation or queue.
    require_agent_write_gate("downloads.submit")
    if not get_settings().dataset_import_write:
        raise AuthorizationError("Dataset 导入运行门禁未通过", code="WRITE_GATE_BLOCKED")


def metadata_adapter() -> GeoMetadataAdapter:
    settings = get_settings()
    return GeoMetadataAdapter(
        max_response_bytes=settings.dataset_geo_max_response_bytes,
        max_samples=settings.dataset_geo_max_samples,
        max_runs=settings.dataset_geo_max_runs,
        request_interval=settings.dataset_geo_request_interval,
    )


class DatasetImportService:
    def __init__(self, db: AsyncSession, *, geo: GeoMetadataAdapter | None = None) -> None:
        self.db = db
        self.repo = DatasetRepository(db)
        self.geo = geo or metadata_adapter()
        self.confirmations = get_tool_confirmation_service()

    async def discover(
        self, owner: uuid.UUID, project_id: uuid.UUID | None, value: str
    ) -> dict[str, Any]:
        require_dataset_read()
        if project_id is not None:
            await self.repo.project(owner, project_id)
        candidate = await self.geo.resolve(value)
        from cygnusx.application.services.geo_processed_data_service import GeoProcessedDataService

        return {
            **candidate,
            "processed": GeoProcessedDataService.candidates(candidate),
            "raw": {
                "runs": candidate["runs"],
                "download_engine": "existing_EBIDownload",
                "runtime_verified": False,
            },
        }

    async def owned(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        ingestion_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> DatasetIngestionModel:
        await self.repo.project(owner, project_id, lock=lock)
        query = select(DatasetIngestionModel).where(
            DatasetIngestionModel.id == ingestion_id,
            DatasetIngestionModel.user_id == owner,
            DatasetIngestionModel.project_id == project_id,
        )
        if lock:
            query = query.with_for_update()
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            raise NotFoundError("导入预案不存在或无权访问")
        return row

    async def list_proposals(self, owner: uuid.UUID, project_id: uuid.UUID) -> list[dict[str, Any]]:
        require_dataset_read()
        await self.repo.project(owner, project_id)
        ids = (
            (
                await self.db.execute(
                    select(DatasetIngestionModel.id)
                    .where(
                        DatasetIngestionModel.user_id == owner,
                        DatasetIngestionModel.project_id == project_id,
                    )
                    .order_by(DatasetIngestionModel.created_at.desc(), DatasetIngestionModel.id)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        return [await self.view(owner, project_id, key) for key in ids]

    async def prepare(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        req: ImportPrepare,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        require_dataset_read()
        project = await self.repo.project(owner, project_id)
        await self.repo.require_module(owner, "downloads")
        if req.dataset_id is not None:
            await self.repo.dataset(owner, project_id, req.dataset_id)
        input_request = req.model_dump(mode="json")
        existing = (
            await self.db.execute(
                select(DatasetIngestionModel).where(
                    DatasetIngestionModel.user_id == owner,
                    DatasetIngestionModel.project_id == project_id,
                    DatasetIngestionModel.request_key == str(req.request_key),
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.normalized_request.get("input") != input_request:
                raise ConflictError("同一请求键不可更换参数", code="IDEMPOTENCY_CONFLICT")
            return await self.view(owner, project_id, existing.id)
        candidate = await self.geo.resolve(accession(req.accession))
        if candidate["status"] == "UNAVAILABLE":
            return {
                "state": "UNAVAILABLE",
                "error_code": candidate.get("error_code"),
                "candidate": candidate,
                "write_enabled": False,
            }
        selected: list[dict[str, Any]] = []
        requests: list[dict[str, Any]] = []
        directory = f"projects/{project.slug}/downloads"
        # Existing normalizer + real containment; no mkdir/dry_run/Task at prepare.
        directory = DownloadService._normalize_directory(directory)
        root = get_path_factory().user_root(str(owner)).resolve()
        try:
            (root / directory).resolve().relative_to(root)
        except ValueError as exc:
            raise ValidationError("目标路径逃逸", code="PATH_ESCAPE") from exc
        if req.mode == "raw":
            runs = {r["run_accession"]: r for r in candidate["runs"]}
            for key in dict.fromkeys(req.selected_ids):
                if key not in runs or not key.startswith("SRR"):
                    raise ValidationError(
                        "原始数据仅允许权威解析的 SRR；GSE 不能直接下载", code="RUN_NOT_RESOLVED"
                    )
                selected.append(runs[key])
                requests.append(
                    DownloadRequest(
                        source="sra",
                        accession=key,
                        download_method="ftp",
                        target_directory=directory,
                    ).model_dump(mode="json")
                )
        else:
            files = {f["url"]: f for f in candidate["files"]}
            for key in dict.fromkeys(req.selected_ids):
                key = trusted_url(key, source_ftp=True)
                if key not in files:
                    raise ValidationError("附件不是本次权威解析的候选", code="SOURCE_MISMATCH")
                selected.append(files[key])
            requests.append(
                DownloadRequest(
                    source="direct_link",
                    links=[f["url"] for f in selected],
                    target_directory=directory,
                    overwrite_policy="auto_rename",
                ).model_dump(mode="json")
            )
        limit = min(req.max_bytes, get_settings().dataset_import_max_bytes)
        sizes = [f.get("size") for r in selected for f in (r.get("files") or [r])]
        known_size = (
            sum(sizes) if sizes and all(isinstance(n, int) and n >= 0 for n in sizes) else None
        )
        if known_size is not None and known_size > limit:
            raise ValidationError("候选数据超过导入预算", code="IMPORT_LIMIT")
        user = await self.db.get(UserModel, owner)
        assert user is not None  # repository validated active user
        reserved = known_size if known_size is not None else limit
        if user.used_storage + reserved > user.storage_quota:
            raise ValidationError("存储配额不足", code="QUOTA_EXCEEDED")
        # No assumption that the worker can see this filesystem; report it unknown.
        disk_available = shutil.disk_usage(root).free if root.exists() else None
        if disk_available is not None and reserved > disk_available:
            raise ValidationError("可用空间不足", code="INSUFFICIENT_SPACE")
        iid = uuid.uuid4()
        normalized = {
            "owner_id": str(owner),
            "project_id": str(project_id),
            "proposal_id": str(iid),
            "operation": "dataset.execute_import",
            "input": input_request,
            "candidate": candidate,
            "selected": selected,
            "requests": requests,
            "max_bytes": limit,
            "session_id": session_id,
        }
        record = await self.confirmations.create_for_tool(
            str(owner), "dataset.execute_import", normalized, session_id=session_id or ""
        )
        row = DatasetIngestionModel(
            id=iid,
            user_id=owner,
            project_id=project_id,
            request_key=str(req.request_key),
            parameters_hash=record.parameter_hash,
            normalized_request=normalized,
            confirmation_id=record.confirmation_id,
            agent_session_id=session_id,
            state="PREPARED",
            preview={
                "name": req.name,
                "accession": candidate["primary_accession"],
                "mode": req.mode,
                "selected": selected,
                "expected_bytes": known_size,
                "max_bytes": limit,
                "quota_checked": True,
                "worker_storage_verified": False,
                "runtime_verified": False,
                "source_hosts_checked": True,
                "groups_confirmed": False,
                "duplicate_policy": "new_version_no_overwrite",
                "target_directory": directory,
                "limitations": [
                    "unknown_size_uses_max_budget"
                    if known_size is None
                    else "known_metadata_size_not_final_bytes",
                    "worker_download_budget_and_redirect_controls_not_runtime_verified",
                    "scientific_sample_groups_need_human_review",
                ],
            },
        )
        self.db.add(row)
        await self.db.flush()
        return await self.view(owner, project_id, row.id)

    async def view(
        self, owner: uuid.UUID, project_id: uuid.UUID, ingestion_id: uuid.UUID
    ) -> dict[str, Any]:
        row = await self.owned(owner, project_id, ingestion_id)
        confirmation = (
            await self.confirmations.get_status(str(owner), row.confirmation_id)
            if row.confirmation_id
            else None
        )
        state = row.state
        if state == "PREPARED":
            state = (
                confirmation.status
                if confirmation and datetime.now(UTC) <= confirmation.expires_at
                else "EXPIRED"
            )
        tasks = []
        for task_id in row.task_ids:
            task = await TaskService(self.db).get_task(uuid.UUID(task_id), str(owner))
            tasks.append({"task_id": str(task.id), "status": task.status, "progress": None})
        return {
            "proposal_id": str(row.id),
            "ingestion_id": str(row.id),
            "project_id": str(project_id),
            "dataset_version_id": str(row.version_id) if row.version_id else None,
            "state": state,
            "preview": row.preview,
            "parameters_hash": row.parameters_hash,
            "normalized_parameters": {
                "operation": "dataset.execute_import",
                "requests": row.normalized_request["requests"],
                "max_bytes": row.normalized_request["max_bytes"],
            },
            "confirmation_id": row.confirmation_id,
            "expires_at": confirmation.expires_at.isoformat() if confirmation else None,
            "tasks": tasks,
            "errors": row.errors,
            "write_enabled": False,
            "gate": "WRITE_GATE_BLOCKED",
        }

    async def decide(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        ingestion_id: uuid.UUID,
        approve: bool,
        *,
        auth_session_or_jti_hash: str | None = None,
    ) -> dict[str, Any]:
        row = await self.owned(owner, project_id, ingestion_id, lock=True)
        record = await self.confirmations.get_status(str(owner), row.confirmation_id or "")
        if (
            record is None
            or record.parameter_hash != row.parameters_hash
            or record.normalized_request != row.normalized_request
        ):
            raise ConflictError("预案过期或参数已变化", code="CONFIRMATION_MISMATCH")
        if approve:
            if (
                not auth_session_or_jti_hash
                or len(auth_session_or_jti_hash) != 64
                or any(c not in "0123456789abcdef" for c in auth_session_or_jti_hash)
            ):
                raise AuthorizationError(
                    "审批需要已认证 JWT 来源", code="APPROVAL_IDENTITY_REQUIRED"
                )
            if row.approval_snapshot is not None:
                self.validate_approval_snapshot(row, record, owner, project_id)
                return await self.view(owner, project_id, ingestion_id)
            if record.status != "PENDING":
                # Redis success followed by SQL failure must not reconstruct provenance.
                raise ConflictError(
                    "审批持久记录缺失，请重新生成预案", code="APPROVAL_SNAPSHOT_MISSING"
                )
            approved = await self.confirmations.approve_by_human(
                user_id=str(owner), confirmation_id=record.confirmation_id
            )
            now = datetime.now(UTC).isoformat()
            row.approval_snapshot = {
                "approval_id": approved.confirmation_id,
                "approval_version": 1,
                "actor_id": str(owner),
                "owner_id": str(owner),
                "project_id": str(project_id),
                "ingestion_id": str(row.id),
                "approved_at": now,
                "auth_session_or_jti_hash": auth_session_or_jti_hash,
                "proposal_digest": digest(row.normalized_request),
                "request_digest": row.parameters_hash,
                "source_digest": digest(row.normalized_request["candidate"]),
                "method": "processed_http"
                if row.normalized_request["input"]["mode"] == "processed"
                else "unsupported_raw",
                "max_budget": row.normalized_request["max_bytes"],
                "scope": "dataset.execute_import",
                "expires_at": approved.expires_at.isoformat(),
                "revoked_at": None,
                "nonce_hash": hashlib.sha256(approved.confirmation_id.encode()).hexdigest(),
                "nonce_status": "APPROVED",
                "status": "APPROVED",
                "consumed_at": None,
            }
        else:
            await self.confirmations.reject(
                user_id=str(owner), confirmation_id=record.confirmation_id
            )
            if row.approval_snapshot is not None:
                row.approval_snapshot = {
                    **row.approval_snapshot,
                    "status": "REJECTED",
                    "revoked_at": datetime.now(UTC).isoformat(),
                    "nonce_status": "REJECTED",
                }
        await self.db.flush()
        return await self.view(owner, project_id, ingestion_id)

    @staticmethod
    def validate_approval_snapshot(
        row: DatasetIngestionModel,
        record: ConfirmationRecord,
        owner: uuid.UUID,
        project_id: uuid.UUID,
    ) -> None:
        """Both durable provenance and the live one-use confirmation are required."""
        snapshot = row.approval_snapshot
        if not snapshot:
            raise ConflictError(
                "审批持久记录缺失，请重新生成预案", code="APPROVAL_SNAPSHOT_MISSING"
            )
        expected = {
            "approval_id": record.confirmation_id,
            "approval_version": 1,
            "actor_id": str(owner),
            "owner_id": str(owner),
            "project_id": str(project_id),
            "ingestion_id": str(row.id),
            "proposal_digest": digest(row.normalized_request),
            "request_digest": row.parameters_hash,
            "source_digest": digest(row.normalized_request["candidate"]),
            "method": "processed_http"
            if row.normalized_request["input"]["mode"] == "processed"
            else "unsupported_raw",
            "max_budget": row.normalized_request["max_bytes"],
            "scope": "dataset.execute_import",
            "expires_at": record.expires_at.isoformat(),
            "revoked_at": None,
            "nonce_hash": hashlib.sha256(record.confirmation_id.encode()).hexdigest(),
            "nonce_status": "APPROVED",
            "status": "APPROVED",
            "consumed_at": None,
        }
        identity_hash = snapshot.get("auth_session_or_jti_hash")
        if (
            any(snapshot.get(key) != value for key, value in expected.items())
            or not isinstance(identity_hash, str)
            or len(identity_hash) != 64
            or any(c not in "0123456789abcdef" for c in identity_hash)
            or record.status != "APPROVED"
            or datetime.now(UTC) > record.expires_at
            or record.user_id != str(owner)
            or record.kind != "tool"
            or record.tool_name != "dataset.execute_import"
        ):
            raise ConflictError("审批持久记录与确认不匹配", code="APPROVAL_SNAPSHOT_MISMATCH")

    async def execute(
        self, owner: uuid.UUID, project_id: uuid.UUID, ingestion_id: uuid.UUID
    ) -> dict[str, Any]:
        require_import_write()
        row = await self.owned(owner, project_id, ingestion_id, lock=True)
        await self.repo.require_module(owner, "downloads")
        if row.task_ids and row.state != "SUBMITTING":
            return await self.view(owner, project_id, row.id)
        if row.state in {"SUBMITTING", "RECONCILIATION_REQUIRED"}:
            raise ConflictError(
                "投递结果不明，需人工对账，禁止重放", code="RECONCILIATION_REQUIRED"
            )
        record = await self.confirmations.get_status(str(owner), row.confirmation_id or "")
        if (
            record is None
            or record.parameter_hash != row.parameters_hash
            or record.normalized_request != row.normalized_request
        ):
            raise ConflictError("预案参数或确认发生变化", code="CONFIRMATION_MISMATCH")
        bound = row.normalized_request
        self.validate_approval_snapshot(row, record, owner, project_id)
        if (
            bound["owner_id"] != str(owner)
            or bound["project_id"] != str(project_id)
            or bound["proposal_id"] != str(row.id)
        ):
            raise AuthorizationError("审批上下文不匹配")
        requests = bound.get("requests", [])
        profiles = get_settings().download_admission_profiles
        if (
            bound.get("input", {}).get("mode") != "processed"
            or len(requests) != 1
            or requests[0].get("source") != "direct_link"
            or not requests[0].get("links")
            or any(urlsplit(url).scheme != "http" for url in requests[0]["links"])
        ):
            raise ConflictError(
                "仅支持单一 processed HTTP 预案", code="DOWNLOAD_ADMISSION_MODE_BLOCKED"
            )
        if len(profiles) != 1:
            raise ConflictError("可信执行身份未配置", code="DOWNLOAD_ADMISSION_PROFILE_BLOCKED")
        environment_id, profile = next(iter(profiles.items()))
        # Source snapshot change/removal after approval invalidates old proposal.
        candidate = await self.geo.resolve(bound["input"]["accession"], refresh=True)
        refs = {e["url"]: e["response_sha256"] for e in candidate["source_evidence"]}
        old_refs = {e["url"]: e["response_sha256"] for e in bound["candidate"]["source_evidence"]}
        if candidate["status"] == "UNAVAILABLE" or refs != old_refs:
            raise ConflictError("权威来源发生变化，请重新生成预案", code="SOURCE_CHANGED")
        user = await self.db.get(UserModel, owner)
        if user is None or user.used_storage + bound["max_bytes"] > user.storage_quota:
            raise ValidationError("审批后配额不足，请重新生成预案", code="QUOTA_EXCEEDED")
        root = get_path_factory().user_root(str(owner))
        if root.exists() and shutil.disk_usage(root).free < bound["max_bytes"]:
            raise ValidationError("审批后可用空间不足", code="INSUFFICIENT_SPACE")
        consumed = await self.confirmations.consume_tool_confirmation(
            str(owner), row.confirmation_id or "", "dataset.execute_import", bound
        )
        row.approval_snapshot = {
            **(row.approval_snapshot or {}),
            "nonce_status": "CONSUMED",
            "consumed_at": (consumed.consumed_at or datetime.now(UTC)).isoformat(),
        }
        row.state = "SUBMITTING"
        await self.db.flush()
        try:
            if row.version_id is None:
                target = bound["input"].get("dataset_id")
                if target:
                    version = await DatasetService(self.db).new_version(
                        owner,
                        project_id,
                        uuid.UUID(target),
                        "Explicit new ingestion: " + bound["input"]["accession"],
                        copy_latest=False,
                    )
                else:
                    ds = await DatasetService(self.db).create(
                        owner, project_id, DatasetCreate(name=bound["input"]["name"])
                    )
                    version = (
                        await self.db.execute(
                            select(DatasetVersionModel).where(
                                DatasetVersionModel.dataset_id == ds.id
                            )
                        )
                    ).scalar_one()
                version.source_snapshot = bound["candidate"]
                row.version_id = version.id
                await self.db.flush()
            for index, request in enumerate(bound["requests"]):
                task = await DownloadService(self.db).submit(
                    str(owner),
                    DownloadRequest.model_validate(
                        {**request, "request_key": f"ingestion:{row.id}:{index}"}
                    ),
                    project_id=project_id,
                )
                row.task_ids = [*row.task_ids, str(task.id)]
                await self.db.flush()
                from cygnusx.infrastructure.database.repositories.download_execution_admission import (
                    issue_processed_http_admission,
                )

                await issue_processed_http_admission(
                    self.db,
                    ingestion_id=row.id,
                    task_id=task.id,
                    owner_id=owner,
                    project_id=project_id,
                    confirmation_id=row.confirmation_id or "",
                    request_digest=row.parameters_hash,
                    limit_bytes=bound["max_bytes"],
                    policy_revision=profile.get("policy_revision", ""),
                    environment_id=environment_id,
                    caller_id=profile.get("caller_id", ""),
                    allowed_destinations=profile.get("allowed_destinations", []),
                    expires_at=record.expires_at,
                )
            row.state = "QUEUED"
            # The existing request dependency owns commit and after_commit dispatch.
            await self.db.flush()
        except Exception:
            await self.db.rollback()
            raise ConflictError(
                "投递结果需人工对账，禁止自动重放", code="RECONCILIATION_REQUIRED"
            ) from None
        return await self.view(owner, project_id, row.id)

    async def reconcile(
        self, owner: uuid.UUID, project_id: uuid.UUID, ingestion_id: uuid.UUID
    ) -> dict[str, Any]:
        """Worker/human reconciliation only; never resubmit a possibly delivered task."""
        from cygnusx.application.schemas.dataset import AssetAttach, SampleAttach
        from cygnusx.application.services.dataset_handoff_service import DatasetHandoffService
        from cygnusx.infrastructure.database.models.dataset import DatasetSourceModel
        from cygnusx.infrastructure.database.models.file import FileRecordModel, SampleModel

        require_import_write()
        row = await self.owned(owner, project_id, ingestion_id, lock=True)
        if (
            row.state in {"SUBMITTING", "RECONCILIATION_REQUIRED"}
            or not row.task_ids
            or row.version_id is None
        ):
            raise ConflictError("请先对账 Task 投递，禁止自动重放", code="RECONCILIATION_REQUIRED")
        version = await self.db.get(DatasetVersionModel, row.version_id)
        assert version is not None
        if row.state == "COMPLETED":
            return await self.view(owner, project_id, row.id)
        tasks = [
            await TaskService(self.db).get_task(uuid.UUID(tid), str(owner)) for tid in row.task_ids
        ]
        states = [getattr(task.status, "value", task.status) for task in tasks]
        if any(state in {"pending", "queued", "running"} for state in states):
            row.state = "RUNNING"
            await self.db.flush()
            return await self.view(owner, project_id, row.id)
        row.state = "VERIFYING"
        records = list(
            (
                await self.db.execute(
                    select(FileRecordModel).where(
                        FileRecordModel.user_id == owner,
                        FileRecordModel.task_id.in_([uuid.UUID(tid) for tid in row.task_ids]),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not records:
            row.state = "RECONCILIATION_REQUIRED"
            row.errors = [
                {
                    "code": "DOWNLOAD_FILES_NOT_REGISTERED",
                    "retry_scope": "file_registration_only_no_download",
                }
            ]
            await self.db.flush()
            return await self.view(owner, project_id, row.id)
        if sum(record.size for record in records) > row.normalized_request["max_bytes"]:
            row.state = "PARTIAL"
            row.errors = [{"code": "IMPORT_LIMIT", "retry_scope": "manual_review_no_redownload"}]
            await self.db.flush()
            return await self.view(owner, project_id, row.id)
        registry = DatasetService(self.db)
        for record in records:
            asset = await registry.attach_asset(
                owner,
                project_id,
                version.dataset_id,
                version.id,
                AssetAttach(
                    file_record_id=record.id,
                    role="raw_reads" if row.preview["mode"] == "raw" else "other",
                ),
            )
            asset.download_task_id = record.task_id
        snapshot = row.normalized_request["candidate"]
        # Persist source graph once; never change original evidence after registration.
        if not (
            await self.db.execute(
                select(DatasetSourceModel.id)
                .where(DatasetSourceModel.version_id == version.id)
                .limit(1)
            )
        ).scalar_one_or_none():
            edges = [
                {"to": snapshot["primary_accession"], "from": None},
                *snapshot["related_accessions"],
            ]
            seen = set()
            for edge in edges:
                identity = (edge["to"], edge.get("from"))
                if identity in seen:
                    continue
                seen.add(identity)
                self.db.add(
                    DatasetSourceModel(
                        version_id=version.id,
                        repository=snapshot["repository"],
                        accession=edge["to"],
                        parent_accession=edge.get("from"),
                        source_url=f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={snapshot['primary_accession']}"
                        if snapshot["repository"] == "GEO"
                        else f"https://www.ebi.ac.uk/ena/browser/view/{snapshot['primary_accession']}",
                        evidence={
                            "source_evidence": snapshot["source_evidence"],
                            "relation": edge.get("relation"),
                        },
                        access_status="UNKNOWN",
                    )
                )
        from cygnusx.infrastructure.database.models.dataset import DatasetSampleModel

        has_samples = (
            await self.db.execute(
                select(DatasetSampleModel.id)
                .where(DatasetSampleModel.version_id == version.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not has_samples:
            for source_sample in snapshot["samples"]:
                key = source_sample["sample_key"]
                descendants = {key}
                for _ in range(4):
                    descendants.update(
                        e["to"] for e in snapshot["related_accessions"] if e["from"] in descendants
                    )
                mapped_tasks = {
                    tid
                    for tid, request in zip(
                        row.task_ids, row.normalized_request["requests"], strict=False
                    )
                    if request.get("accession") in descendants
                }
                file_ids = [
                    r.id
                    for r in records
                    if row.preview["mode"] == "processed" or str(r.task_id) in mapped_tasks
                ]
                sample = SampleModel(
                    user_id=owner,
                    name=key,
                    species="; ".join(source_sample.get("organism", [])),
                    meta={
                        "title": source_sample.get("title"),
                        "characteristics": source_sample.get("characteristics"),
                        "processing": source_sample.get("processing"),
                        "source_url": source_sample.get("source_url"),
                    },
                    file_ids=[str(fid) for fid in file_ids],
                )
                self.db.add(sample)
                await self.db.flush()
                await registry.attach_sample(
                    owner,
                    project_id,
                    version.dataset_id,
                    version.id,
                    SampleAttach(
                        sample_id=sample.id,
                        sample_key=key,
                        file_record_ids=file_ids,
                        source_accessions=sorted(descendants),
                    ),
                )
        validation = await DatasetHandoffService(self.db).verify(
            owner, project_id, version.dataset_id, version.id
        )
        failed_integrity = any(a["checksum_status"] != "VERIFIED" for a in validation["assets"])
        row.state = (
            "PARTIAL"
            if failed_integrity or any(state not in {"success", "completed"} for state in states)
            else "COMPLETED"
        )
        if row.state == "PARTIAL":
            row.errors = [
                {"code": "PARTIAL_IMPORT", "retry_scope": "verified_assets_retained_manual_review"}
            ]
        version.status = "REVIEW_REQUIRED"
        await self.db.flush()
        return await self.view(owner, project_id, row.id)
