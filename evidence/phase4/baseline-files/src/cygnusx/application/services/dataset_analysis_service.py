"""Dataset-to-Flow preparation reuses the final Flow validator and TaskService."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.dataset import DatasetAnalysisPrepare
from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.agent_tool_gateway import require_agent_write_gate
from cygnusx.application.services.analysis_flow_tool_service import AnalysisFlowToolService
from cygnusx.application.services.dataset_handoff_service import DatasetHandoffService
from cygnusx.application.services.dataset_import_service import require_dataset_read
from cygnusx.application.services.task_service import TaskService
from cygnusx.application.services.tool_confirmation_service import get_tool_confirmation_service
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cygnusx.domain.dataset.validation import checksum, open_owned_file
from cygnusx.infrastructure.database.models.dataset import (
    DatasetAnalysisLinkModel,
    DatasetAssetModel,
    DatasetVersionModel,
)
from cygnusx.infrastructure.database.repositories.dataset_repository import DatasetRepository
from cygnusx.infrastructure.storage import get_path_factory


class DatasetAnalysisService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        session_id: str | None = None,
        invocation_id: uuid.UUID | None = None,
    ) -> None:
        self.db = db
        self.session_id = session_id
        self.invocation_id = invocation_id
        self.repo = DatasetRepository(db)
        self.confirmations = get_tool_confirmation_service()

    async def compatible(
        self, owner: uuid.UUID, project_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID
    ) -> dict[str, Any]:
        require_dataset_read()
        await self.repo.require_module(owner, "flows")
        manifest = await DatasetHandoffService(self.db).manifest(
            owner, project_id, dataset_id, version_id
        )
        context = ToolInvocationContext(
            user_id=str(owner), session_id="dataset-analysis", db=self.db
        )
        discovered = await AnalysisFlowToolService(context).discover()
        potential = manifest["validation"]["compatible_flow_ids"]
        return {
            "dataset_version_id": str(version_id),
            "workflows": [w for w in discovered if w["flow_id"] in potential],
            "validation": manifest["validation"],
            "write_enabled": False,
            "counts_flow_status": "NOT_RUNTIME_ACCEPTED",
        }

    async def prepare(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        request: DatasetAnalysisPrepare,
    ) -> dict[str, Any]:
        require_dataset_read()
        await self.repo.require_module(owner, "flows")
        version = await self.repo.version(owner, project_id, dataset_id, version_id)
        dataset = await self.repo.dataset(owner, project_id, dataset_id)
        if not version.handoff:
            raise ValidationError("请先审查并冻结数据交接版本", code="HANDOFF_NOT_FROZEN")
        manifest = await DatasetHandoffService(self.db).manifest(
            owner, project_id, dataset_id, version_id
        )
        if request.flow_id not in manifest["validation"]["compatible_flow_ids"]:
            return {
                "validation": manifest["validation"],
                "error_code": "NO_COMPATIBLE_FLOW",
                "write_enabled": False,
            }
        assay = version.review_annotations.get("assay_type", dataset.assay_type)
        if request.flow_id == "counts_deg" and assay == "bulk_rnaseq":
            return await self._prepare_counts(
                owner, project_id, dataset_id, version, manifest, request
            )
        if request.flow_id != "rna_seq" or assay != "bulk_rnaseq":
            raise ValidationError(
                "数据 assay 与当前已验证流程输入不匹配", code="ASSAY_REVIEW_REQUIRED"
            )
        if any(key not in {"parameters", "comparisons"} for key in request.options):
            raise ValidationError("仅允许人工选择流程参数与比较组")
        params = dict(request.options.get("parameters", {}))
        if any(
            key in params
            for key in {"raw_data_path", "data_deliver", "user_id", "project_id", "workflow"}
        ):
            raise ValidationError("受管输入路径不可由调用者覆盖", code="PATH_OVERRIDE_FORBIDDEN")
        missing = [
            key for key in ("Genome_Version", "species", "Library_Types") if not params.get(key)
        ]
        if missing:
            return {
                "error_code": "INPUT_REVIEW_REQUIRED",
                "missing_fields": missing,
                "write_enabled": False,
            }
        organism_values = set(version.source_snapshot.get("organism", []))
        if organism_values and organism_values != {params["species"]}:
            raise ValidationError("选择的物种与来源不一致", code="ORGANISM_MISMATCH")
        factory = get_path_factory()
        parents = set()
        files = {
            asset["file_record_id"]: await self.repo.file(
                owner, project_id, uuid.UUID(asset["file_record_id"])
            )
            for asset in manifest["assets"]
            if asset["data_type"] == "RAW_FASTQ"
        }
        sample_rows = []
        linked_files = set()
        for sample in manifest["samples"]:
            key = sample["sample_key"]
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
                raise ValidationError("样本 ID 不能安全用于 FlowFrame", code="SAMPLE_NAME_UNSAFE")
            refs = sample["file_record_ids"]
            if len(refs) not in {1, 2}:
                raise ValidationError(
                    "需明确 SE/PE 文件配对，多 Run 需要人工整理",
                    code="READ_PAIRING_REVIEW_REQUIRED",
                )
            suffixes = set()
            for file_id in refs:
                if file_id not in files or file_id in linked_files:
                    raise ValidationError("FASTQ 样本文件映射不唯一", code="SAMPLE_FILE_MISMATCH")
                linked_files.add(file_id)
                record = files[file_id]
                path = factory.data_root / record.storage_path
                # RNAFlow sample prefix contract. Do not rename/link files during prepare.
                match = re.fullmatch(re.escape(key) + r"_R([12])\.(?:fastq|fq)(?:\.gz)?", path.name)
                if not match:
                    raise ValidationError(
                        "FASTQ 名称与样本前缀不匹配", code="READ_NAMING_REVIEW_REQUIRED"
                    )
                suffixes.add(match.group(1))
                parents.add(path.parent)
            if suffixes != ({"1", "2"} if len(refs) == 2 else {"1"}):
                raise ValidationError("FASTQ 双端配对不完整", code="READ_PAIRING_REVIEW_REQUIRED")
            sample_rows.append(
                {
                    "sample": key,
                    "sample_name": sample["source_metadata"].get("name") or key,
                    "group": sample["user_annotation"]["group"],
                }
            )
        if len(parents) != 1 or linked_files != set(files):
            raise ValidationError(
                "输入需处于同一受控目录且每个文件匹配样本", code="INPUT_LAYOUT_REVIEW_REQUIRED"
            )
        directory = parents.pop()
        try:
            relative = directory.relative_to(factory.user_root(str(owner))).as_posix()
        except ValueError as exc:
            raise ValidationError("数据目录超出 owner 根", code="PATH_ESCAPE") from exc
        params = {
            "project_name": dataset.name,
            "client": "Dataset import",
            **params,
            "raw_data_path": relative,
        }
        context = ToolInvocationContext(
            user_id=str(owner),
            session_id="dataset-analysis",
            db=self.db,
            extra={"strict_input_paths": True},
        )
        prepared = await AnalysisFlowToolService(context).prepare(
            request.flow_id,
            {
                "name": dataset.name + " RNA-seq",
                "parameters": params,
                "sample_sheet": sample_rows,
                "comparisons": request.options.get("comparisons", []),
            },
            create_confirmation=False,
        )
        if not prepared.get("valid"):
            return {"validation": prepared, "write_enabled": False}
        return await self._store_proposal(
            owner,
            project_id,
            dataset_id,
            version,
            request.flow_id,
            prepared,
            {**params, "raw_data_path": "directory://" + relative},
            sample_rows,
            request.options.get("comparisons", []),
        )

    async def _store_proposal(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version: DatasetVersionModel,
        flow_id: str,
        prepared: dict[str, Any],
        public_parameters: dict[str, Any],
        sample_rows: list[dict[str, Any]],
        comparisons: list[dict[str, Any]],
    ) -> dict[str, Any]:
        version_id = version.id
        assert version.handoff is not None
        pid = uuid.uuid4()
        normalized = prepared["normalized_request"]
        normalized["idempotency_key"] = f"dataset:{pid}"
        bound = {
            "owner_id": str(owner),
            "project_id": str(project_id),
            "dataset_id": str(dataset_id),
            "dataset_version_id": str(version_id),
            "handoff_hash": version.handoff["manifest_hash"],
            "operation": "dataset.analysis.submit",
            "session_id": self.session_id,
            "invocation_id": str(self.invocation_id) if self.invocation_id else None,
            "public_preview": {
                "parameters": public_parameters,
                "sample_sheet": sample_rows,
                "comparisons": comparisons,
                "resource_hint": prepared["resource_hint"],
            },
            "request": normalized,
        }
        confirmation = await self.confirmations.create_for_tool(
            str(owner), "dataset.analysis.submit", bound, session_id=self.session_id or ""
        )
        row = DatasetAnalysisLinkModel(
            id=pid,
            version_id=version_id,
            flow_id=flow_id,
            handoff_hash=version.handoff["manifest_hash"],
            confirmation_id=confirmation.confirmation_id,
            parameters_hash=confirmation.parameter_hash,
            normalized_request=bound,
        )
        self.db.add(row)
        await self.db.flush()
        # Return controlled refs instead of the internal normalized submission paths.
        return {
            "analysis_proposal_id": str(pid),
            "dataset_version_id": str(version_id),
            "flow_id": flow_id,
            "parameters": public_parameters,
            "sample_sheet": sample_rows,
            "comparisons": comparisons,
            "parameters_hash": confirmation.parameter_hash,
            "confirmation_id": confirmation.confirmation_id,
            "expires_at": confirmation.expires_at.isoformat(),
            "resource_hint": prepared["resource_hint"],
            "worker_paths_verified": False,
            "write_enabled": False,
            "gate": "WRITE_GATE_BLOCKED",
        }

    async def _prepare_counts(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version: DatasetVersionModel,
        manifest: dict[str, Any],
        request: DatasetAnalysisPrepare,
    ) -> dict[str, Any]:
        if set(request.options) - {"parameters"}:
            raise ValidationError("counts-only 仅接受显式统计参数")
        parameters = dict(request.options.get("parameters", {}))
        allowed = {"design", "reference", "treatment", "alpha", "fit_type", "project_name"}
        if set(parameters) - allowed:
            raise ValidationError("输入文件、数据类型与审查标志必须由服务端确定")
        missing = [key for key in ("design", "reference", "treatment") if not parameters.get(key)]
        if missing:
            return {
                "error_code": "INPUT_REVIEW_REQUIRED",
                "missing_fields": missing,
                "write_enabled": False,
            }
        groups = {
            sample["sample_key"]: sample["user_annotation"].get("group")
            for sample in manifest["samples"]
        }
        if any(count < 2 for count in Counter(groups.values()).values()):
            raise ValidationError(
                "差异分析要求每组至少两个生物学重复", code="BIOLOGICAL_REPLICATION_REQUIRED"
            )
        counts = [
            asset for asset in manifest["assets"] if asset["data_type"] == "RAW_INTEGER_COUNTS"
        ]
        metadata = [
            asset for asset in manifest["assets"] if asset["data_type"] == "SAMPLE_METADATA"
        ]
        if len(counts) != 1 or len(metadata) != 1:
            raise ValidationError(
                "需一份已验证 counts 与一份样本表", code="COUNTS_METADATA_REQUIRED"
            )
        metadata_asset = (
            await self.db.execute(
                select(DatasetAssetModel).where(
                    DatasetAssetModel.version_id == version.id,
                    DatasetAssetModel.file_record_id == uuid.UUID(metadata[0]["file_record_id"]),
                )
            )
        ).scalar_one()
        rows = metadata_asset.classification.get("rows", [])
        if {row["sample_id"]: row["group"] for row in rows} != groups:
            raise ValidationError("物理样本表与人工确认分组不一致", code="GROUP_METADATA_MISMATCH")
        params = {
            "project_name": "Dataset counts DEG",
            "alpha": 0.05,
            "fit_type": "parametric",
            **parameters,
            "input_type": "raw_integer_counts",
            "source_reviewed": True,
            "count_matrix": "file://" + counts[0]["file_record_id"],
            "sample_metadata": "file://" + metadata[0]["file_record_id"],
        }
        context = ToolInvocationContext(
            user_id=str(owner),
            session_id="dataset-analysis",
            db=self.db,
            extra={"strict_input_paths": True},
        )
        prepared = await AnalysisFlowToolService(context).prepare(
            "counts_deg",
            {"name": "Dataset counts DEG", "parameters": params},
            create_confirmation=False,
        )
        if not prepared.get("valid"):
            return {"validation": prepared, "write_enabled": False}
        return await self._store_proposal(
            owner, project_id, dataset_id, version, "counts_deg", prepared, params, [], []
        )

    async def owned_proposal(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        proposal_id: uuid.UUID,
        *,
        lock: bool = False,
    ) -> DatasetAnalysisLinkModel:
        await self.repo.version(owner, project_id, dataset_id, version_id)
        query = select(DatasetAnalysisLinkModel).where(
            DatasetAnalysisLinkModel.id == proposal_id,
            DatasetAnalysisLinkModel.version_id == version_id,
        )
        if lock:
            query = query.with_for_update()
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            raise NotFoundError("分析预案不存在")
        return row

    async def view(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        proposal_id: uuid.UUID,
    ) -> dict[str, Any]:
        row = await self.owned_proposal(owner, project_id, dataset_id, version_id, proposal_id)
        approval = await self.confirmations.get_status(str(owner), row.confirmation_id or "")
        task = await TaskService(self.db).get_task(row.task_id, str(owner)) if row.task_id else None
        return {
            "analysis_proposal_id": str(row.id),
            "dataset_version_id": str(version_id),
            "parameters_hash": row.parameters_hash,
            "state": task.status
            if task
            else (
                "EXPIRED"
                if approval and datetime.now(UTC) >= approval.expires_at
                else approval.status
                if approval
                else row.state
            ),
            "task_id": str(task.id) if task else None,
            "preview": row.normalized_request.get("public_preview", {}),
            "write_enabled": False,
            "gate": "WRITE_GATE_BLOCKED",
        }

    async def approve(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        proposal_id: uuid.UUID,
    ) -> dict[str, Any]:
        row = await self.owned_proposal(
            owner, project_id, dataset_id, version_id, proposal_id, lock=True
        )
        record = await self.confirmations.get_status(str(owner), row.confirmation_id or "")
        if (
            not record
            or record.parameter_hash != row.parameters_hash
            or record.normalized_request != row.normalized_request
        ):
            raise ConflictError("预案过期或变更", code="CONFIRMATION_MISMATCH")
        await self.confirmations.approve_by_human(
            user_id=str(owner), confirmation_id=record.confirmation_id
        )
        return {"analysis_proposal_id": str(row.id), "state": "APPROVED", "write_enabled": False}

    async def execute(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        proposal_id: uuid.UUID,
    ) -> dict[str, Any]:
        require_agent_write_gate("analysis.submit")
        if not get_settings().analysis_submit_from_dataset:
            raise AuthorizationError("Dataset 分析运行门禁未通过", code="WRITE_GATE_BLOCKED")
        row = await self.owned_proposal(
            owner, project_id, dataset_id, version_id, proposal_id, lock=True
        )
        if row.task_id:
            task = await TaskService(self.db).get_task(row.task_id, str(owner))
            return {
                "task_id": str(task.id),
                "status": task.status,
                "dataset_version_id": str(version_id),
            }
        if row.state == "SUBMITTING":
            raise ConflictError("提交结果不明，请人工对账", code="RECONCILIATION_REQUIRED")
        version = await self.repo.version(owner, project_id, dataset_id, version_id)
        if not version.handoff or version.handoff["manifest_hash"] != row.handoff_hash:
            raise ConflictError("Handoff 版本变化，请重新预检", code="HANDOFF_CHANGED")
        if not version.handoff["validation"].get("worker_paths_verified"):
            raise ValidationError("Worker 输入挂载尚未验收", code="WORKER_PATHS_NOT_VERIFIED")
        from cygnusx.application.services.dataset_handoff_service import validation_limits

        factory = get_path_factory()
        for asset in version.handoff["assets"]:
            record = await self.repo.file(owner, project_id, uuid.UUID(asset["file_record_id"]))
            with open_owned_file(
                factory.data_root / record.storage_path, factory.user_root(str(owner))
            ) as stream:
                actual, _ = checksum(stream, validation_limits())
            if actual != asset["sha256"]:
                raise ConflictError("Handoff 文件内容变化", code="INPUT_CHANGED")
        bound = row.normalized_request
        if any(
            bound.get(key) != value
            for key, value in {
                "owner_id": str(owner),
                "project_id": str(project_id),
                "dataset_version_id": str(version_id),
                "handoff_hash": row.handoff_hash,
            }.items()
        ):
            raise AuthorizationError("分析确认上下文不匹配")
        approval_record = await self.confirmations.get_status(str(owner), row.confirmation_id or "")
        if (
            not approval_record
            or approval_record.parameter_hash != row.parameters_hash
            or approval_record.normalized_request != bound
        ):
            raise ConflictError("预案参数变更", code="CONFIRMATION_MISMATCH")
        await self.confirmations.consume_tool_confirmation(
            str(owner), row.confirmation_id or "", "dataset.analysis.submit", bound
        )
        row.state = "SUBMITTING"
        await self.db.commit()
        try:
            task = await TaskService(self.db).submit(
                str(owner), TaskSubmitRequest.model_validate(bound["request"])
            )
            row.task_id, row.state = task.id, "QUEUED"
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise ConflictError(
                "提交结果不明，请人工对账", code="RECONCILIATION_REQUIRED"
            ) from None
        return {
            "task_id": str(task.id),
            "status": task.status,
            "dataset_version_id": str(version_id),
        }


async def validate_counts_task_request(
    db: AsyncSession, owner: uuid.UUID, request: TaskSubmitRequest
) -> None:
    """Final counts Task boundary: a model's source_reviewed boolean is never proof."""
    if not request.idempotency_key or not request.idempotency_key.startswith("dataset:"):
        raise AuthorizationError(
            "counts-only 必须来自已批准 Dataset Handoff", code="HANDOFF_REQUIRED"
        )
    try:
        proposal_id = uuid.UUID(request.idempotency_key.removeprefix("dataset:"))
    except ValueError as exc:
        raise AuthorizationError("无效 Dataset 预案引用", code="HANDOFF_REQUIRED") from exc
    row = await db.get(DatasetAnalysisLinkModel, proposal_id)
    if row is None or row.state != "SUBMITTING" or row.flow_id != "counts_deg":
        raise AuthorizationError("缺少正在消费的人工批准", code="CONFIRMATION_REQUIRED")
    bound = row.normalized_request
    if bound.get("owner_id") != str(owner) or bound.get("request") != request.model_dump(
        mode="json"
    ):
        raise AuthorizationError("Dataset 审批参数不匹配", code="CONFIRMATION_MISMATCH")
    await DatasetRepository(db).version(
        owner, uuid.UUID(bound["project_id"]), uuid.UUID(bound["dataset_id"]), row.version_id
    )
