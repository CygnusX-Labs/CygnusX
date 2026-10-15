"""Shared controlled tool boundary; no new downloader, workflow or task engine."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.agent_tools import (
    CAPABILITY_MODELS,
    GatewayResult,
    TaskStatusView,
    ToolProposal,
    capability_catalog,
)
from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.analysis_flow_tool_service import AnalysisFlowToolService
from cygnusx.application.services.download_service import DownloadService
from cygnusx.application.services.task_service import TaskService
from cygnusx.application.services.tool_confirmation_service import (
    get_tool_confirmation_service,
)
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cygnusx.infrastructure.database.models.agent_tool_invocation import AgentToolInvocationModel
from cygnusx.infrastructure.database.models.chat import ChatSessionModel
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.infrastructure.storage import get_path_factory

# Reviewed runtime evidence is absent. Environment flags alone cannot certify G0.
# This release intentionally has no enabled write path. Replacing this value requires
# the separate gate/release review documented in the Phase 2 report.
WRITE_RUNTIME_ACCEPTED = False


def require_agent_write_gate(operation: str) -> None:
    settings = get_settings()
    requested = {
        "downloads.submit": settings.agent_download_write_enabled,
        "analysis.submit": settings.agent_analysis_write_enabled,
        "tasks.cancel": settings.agent_task_cancel_enabled,
    }.get(operation, False)
    if not WRITE_RUNTIME_ACCEPTED or not requested:
        raise AuthorizationError("Agent 写操作运行门禁未通过", code="WRITE_GATE_BLOCKED")


def digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


class AgentToolGateway:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.confirmations = get_tool_confirmation_service()

    async def context(
        self,
        user_id: str,
        session_id: str,
        *,
        expected_agent: str | None = None,
    ) -> ToolInvocationContext:
        if not get_settings().tool_gateway_read_enabled:
            raise AuthorizationError("共享工具入口未启用", code="FEATURE_DISABLED")
        user = await self.db.get(UserModel, uuid.UUID(user_id))
        if user is None or user.status != "active":
            raise AuthorizationError("用户不可用")
        result = await self.db.execute(
            select(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.status == "active",
            )
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError("会话不存在或无权访问")
        kind = (
            "research_treasure_mouse"
            if (session.sandbox_meta or {}).get("research_agent")
            else "platform_ai"
        )
        if expected_agent and kind != expected_agent:
            raise AuthorizationError("Agent 上下文不匹配")
        project = None
        if session.project_id:
            project = await self.db.get(ProjectModel, uuid.UUID(session.project_id))
            if project is None or str(project.user_id) != user_id:
                raise AuthorizationError("项目不存在或授权已撤销")
        denied = set(user.disabled_modules or []) if user.role != "admin" else set()
        if ("treasure-mouse" if kind == "research_treasure_mouse" else "ai-assistant") in denied:
            raise AuthorizationError("Agent 入口权限已撤销")
        scopes = {
            "read:discovery",
            "read:tasks",
            "read:datasets",
            "read:workflows",
            "prepare:download",
            "prepare:analysis",
        }
        if "flows" in denied:
            scopes -= {"read:workflows", "prepare:analysis"}
        if "tasks" in denied:
            scopes.discard("read:tasks")
        if "files" in denied:
            scopes -= {"prepare:download", "prepare:analysis", "read:datasets"}
        if "downloads" in denied:
            scopes -= {"read:discovery", "prepare:download"}
        return ToolInvocationContext(
            user_id=user_id,
            session_id=session_id,
            agent_id=session.agent_id,
            db=self.db,
            extra={
                "project_id": session.project_id,
                "project_slug": project.slug if project else None,
                "agent_kind": kind,
                "scopes": sorted(scopes),
            },
        )

    @staticmethod
    def catalog(context: ToolInvocationContext) -> list[dict[str, Any]]:
        dataset_enabled = getattr(get_settings(), "dataset_discovery_readonly", False)
        return [
            c.model_dump()
            for c in capability_catalog(include_dataset=dataset_enabled)
            if c.scope in context.extra["scopes"]
            and (
                dataset_enabled
                or not (
                    c.capability_id.startswith("dataset.")
                    or c.capability_id
                    in {"analysis.list_compatible_workflows", "analysis.prepare_from_dataset"}
                )
            )
        ]

    async def invoke(
        self,
        context: ToolInvocationContext,
        capability_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        # Even builtin callers get a fresh user/session/project check at execution.
        context = await self.context(context.user_id, context.session_id)
        if capability_id not in CAPABILITY_MODELS:
            raise ValidationError("未注册工具", code="VALIDATION_ERROR")
        if capability_id == "dataset.execute_import":
            from cygnusx.application.services.dataset_import_service import require_import_write

            require_import_write()
        if capability_id in {"downloads.submit", "analysis.submit", "tasks.cancel"}:
            require_agent_write_gate(capability_id)  # before records, directories or queue
        allowed = {c["capability_id"] for c in self.catalog(context)}
        if capability_id not in allowed:
            raise AuthorizationError("工具未获授权", code="FORBIDDEN")
        args = CAPABILITY_MODELS[capability_id].model_validate(arguments).model_dump()
        invocation = AgentToolInvocationModel(
            id=uuid.uuid4(),
            owner_id=context.user_id,
            project_id=context.extra["project_id"],
            conversation_id=context.session_id,
            agent_kind=context.extra["agent_kind"],
            capability_id=capability_id,
            request_id=context.request_id,
            parameters_hash=digest(args),
            status="INSPECTED",
            preview={},
        )
        analysis_context = context.model_copy(
            update={
                "extra": {**context.extra, "strict_input_paths": True},
            }
        )
        analysis = AnalysisFlowToolService(analysis_context)
        if capability_id == "downloads.describe_capabilities":
            result: Any = {
                "candidate_accessions": ["SRR", "PRJNA"],
                "runtime_verified_accessions": [],
                "runtime_status": "BLOCKED",
                "write_enabled": False,
                "unsupported": ["GSE", "GSM", "direct_link", "processed_matrix"],
                "limits": {"bytes_estimate": None, "quota_enforced_for_preview": False},
            }
        elif capability_id == "downloads.prepare":
            result = await self._download_proposal(context, invocation, args)
        elif capability_id == "analysis.list_workflows":
            result = await analysis.discover()
        elif capability_id == "analysis.get_workflow_schema":
            result = await analysis.describe(args["flow_id"])
        elif capability_id == "analysis.prepare":
            if not context.extra["project_id"]:
                raise ValidationError("准备分析需要选择获授权项目")
            prepared = await analysis.prepare(
                args["flow_id"], args["arguments"], create_confirmation=False
            )
            if not prepared["valid"]:
                result = prepared
            else:
                result = await self._proposal(
                    context,
                    invocation,
                    "analysis.submit",
                    prepared["normalized_request"],
                    {k: v for k, v in prepared.items() if k != "normalized_request"},
                )
        elif capability_id.startswith("dataset.") or capability_id in {
            "analysis.list_compatible_workflows",
            "analysis.prepare_from_dataset",
        }:
            result = await self._dataset_tool(context, invocation, capability_id, args)
        elif capability_id == "tasks.get_status":
            result = await self.task_status(context, args["task_id"])
        else:
            result = await self.related(context)
        self.db.add(invocation)
        await self.db.flush()
        return GatewayResult(invocation_id=str(invocation.id), result=result).model_dump()

    async def _dataset_tool(
        self,
        context: ToolInvocationContext,
        invocation: AgentToolInvocationModel,
        capability: str,
        args: dict[str, Any],
    ) -> Any:
        from cygnusx.application.schemas.dataset import DatasetAnalysisPrepare, ImportPrepare
        from cygnusx.application.services.dataset_analysis_service import DatasetAnalysisService
        from cygnusx.application.services.dataset_handoff_service import DatasetHandoffService
        from cygnusx.application.services.dataset_import_service import DatasetImportService
        from cygnusx.application.services.dataset_service import DatasetService

        if not context.extra["project_id"]:
            raise ValidationError("Dataset 工具需要当前获授权项目")
        owner, project = uuid.UUID(context.user_id), uuid.UUID(context.extra["project_id"])
        if capability == "dataset.discover":
            return await DatasetImportService(self.db).discover(owner, project, args["accession"])
        if capability == "dataset.list_project_assets":
            dataset_service = DatasetService(self.db)
            return [
                {"id": str(d.id), "name": d.name, "status": d.status}
                for d in await dataset_service.repo.list(owner, project)
            ]
        if capability == "dataset.prepare_import":
            service = DatasetImportService(self.db)
            result = await service.prepare(
                owner,
                project,
                ImportPrepare.model_validate(args["request"]),
                session_id=context.session_id,
            )
            if result.get("ingestion_id"):
                row = await service.owned(owner, project, uuid.UUID(result["ingestion_id"]))
                self.db.add(invocation)
                await self.db.flush()
                # Do not overwrite the original session/call of a deduped proposal.
                if row.invocation_id is None:
                    row.invocation_id = invocation.id
            return result
        if capability == "dataset.execute_import":
            importer = DatasetImportService(self.db)
            proposal_id = uuid.UUID(args["proposal_id"])
            ingestion = await importer.owned(owner, project, proposal_id)
            if ingestion.agent_session_id != context.session_id:
                raise NotFoundError("当前会话没有该导入关联")
            return await importer.execute(owner, project, proposal_id)
        dataset_id, version_id = uuid.UUID(args["dataset_id"]), uuid.UUID(args["version_id"])
        if capability == "analysis.list_compatible_workflows":
            return await DatasetAnalysisService(self.db).compatible(
                owner, project, dataset_id, version_id
            )
        if capability == "analysis.prepare_from_dataset":
            return await DatasetAnalysisService(
                self.db, session_id=context.session_id, invocation_id=invocation.id
            ).prepare(
                owner,
                project,
                dataset_id,
                version_id,
                DatasetAnalysisPrepare.model_validate(args["request"]),
            )
        manifest = await DatasetHandoffService(self.db).manifest(
            owner, project, dataset_id, version_id
        )
        return (
            manifest
            if capability == "dataset.inspect"
            else {"assets": manifest["assets"], "validation": manifest["validation"]}
        )

    async def _download_proposal(
        self,
        context: ToolInvocationContext,
        invocation: AgentToolInvocationModel,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        accession = args["accession"].strip().upper()
        if re.fullmatch(r"GS[EM]\d+", accession):
            return {
                "validation": "NEEDS_METADATA_RESOLUTION",
                "accession": accession,
                "write_enabled": False,
                "limitations": [
                    "GEO 需先解析为受支持 Run；processed-data 需使用获授权的 dataset.discover / prepare_import"
                ],
            }
        if not re.fullmatch(r"(?:SRR|PRJNA)\d+", accession):
            raise ValidationError("只接受候选 SRR/PRJNA 编号；任意 URL 不受支持")
        if not context.extra["project_id"]:
            raise ValidationError("准备下载需要选择获授权项目")
        directory = DownloadService._normalize_directory(
            f"projects/{context.extra['project_slug']}/downloads"
        )
        root = get_path_factory().user_root(context.user_id).resolve()
        if not (root / directory).resolve().is_relative_to(root):
            raise ValidationError("下载目录越出用户存储空间")
        request = DownloadRequest(
            accession=accession, download_method=args["download_method"], target_directory=directory
        )
        return await self._proposal(
            context,
            invocation,
            "downloads.submit",
            request.model_dump(mode="json"),
            {
                "accession": accession,
                "target_directory": directory,
                "bytes_estimate": None,
                "runtime_verified": False,
                "limitations": ["规模/预算未知，仅预案；Worker/配额运行验收未通过"],
            },
        )

    async def _proposal(
        self,
        context: ToolInvocationContext,
        invocation: AgentToolInvocationModel,
        operation: str,
        parameters: dict[str, Any],
        preview: dict[str, Any],
    ) -> dict[str, Any]:
        if operation == "analysis.submit":
            parameters = {**parameters, "idempotency_key": "bioops:" + str(invocation.id)}
        bound = {
            "owner_id": context.user_id,
            "project_id": context.extra["project_id"],
            "conversation_id": context.session_id,
            "operation": operation,
            "proposal_id": str(invocation.id),
            "parameters": parameters,
        }
        confirmation = await self.confirmations.create_for_tool(
            context.user_id,
            "bioops:" + operation,
            bound,
            session_id=context.session_id,
            agent_id=context.agent_id,
        )
        invocation.confirmation_id = confirmation.confirmation_id
        invocation.parameters_hash = confirmation.parameter_hash
        invocation.status = "AWAITING_APPROVAL"
        safe_fields = {
            "flow_id",
            "flow_name",
            "sample_count",
            "comparison_count",
            "resource_hint",
            "accession",
            "target_directory",
            "bytes_estimate",
            "runtime_verified",
            "limitations",
        }
        invocation.preview = {
            "operation": operation,
            **{k: v for k, v in preview.items() if k in safe_fields},
        }
        return ToolProposal(
            **{
                "proposal_id": str(invocation.id),
                "operation": operation,
                "conversation_id": context.session_id,
                "project_id": invocation.project_id,
                "parameters_hash": invocation.parameters_hash,
                "preview": invocation.preview,
                "normalized_parameters": parameters,
                "confirmation_id": confirmation.confirmation_id,
                "expires_at": confirmation.expires_at.isoformat(),
                "state": confirmation.status,
                "write_enabled": False,
                "gate": "WRITE_GATE_BLOCKED",
            }
        ).model_dump()

    async def proposal(
        self,
        context: ToolInvocationContext,
        proposal_id: str,
        *,
        lock: bool = False,
    ) -> AgentToolInvocationModel:
        try:
            proposal_uuid = uuid.UUID(proposal_id)
        except ValueError as exc:
            raise NotFoundError("预案不存在") from exc
        query = select(AgentToolInvocationModel).where(
            AgentToolInvocationModel.id == proposal_uuid,
            AgentToolInvocationModel.owner_id == context.user_id,
            AgentToolInvocationModel.conversation_id == context.session_id,
        )
        if lock:
            query = query.with_for_update()
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None or row.project_id != context.extra["project_id"]:
            raise NotFoundError("预案不存在或上下文已变更")
        return row

    async def decide(
        self,
        context: ToolInvocationContext,
        proposal_id: str,
        *,
        approve: bool,
    ) -> dict[str, Any]:
        context = await self.context(context.user_id, context.session_id)
        row = await self.proposal(context, proposal_id, lock=True)
        scope = (
            "prepare:download"
            if row.preview.get("operation") == "downloads.submit"
            else "prepare:analysis"
        )
        if scope not in context.extra["scopes"]:
            raise AuthorizationError("预案工具权限已撤销")
        if not row.confirmation_id:
            raise ValidationError("该记录不是可批准预案")
        record = await self.confirmations.get_status(context.user_id, row.confirmation_id)
        if record is None or record.parameter_hash != row.parameters_hash:
            raise ConflictError("确认记录丢失或参数不一致")
        if approve:
            record = await self.confirmations.approve_by_human(
                user_id=context.user_id, confirmation_id=row.confirmation_id
            )
        else:
            await self.confirmations.reject(context.user_id, row.confirmation_id)
            record = await self.confirmations.get_status(context.user_id, row.confirmation_id)
        row.status = record.status if record else "EXPIRED"
        await self.db.flush()
        return {"state": row.status, "write_enabled": False, "gate": "WRITE_GATE_BLOCKED"}

    async def task_status(self, context: ToolInvocationContext, task_id: str) -> dict[str, Any]:
        task = await TaskService(self.db).get_task(uuid.UUID(task_id), context.user_id)
        # A guessed owner Task ID does not imply project/session membership.
        link = (
            await self.db.execute(
                select(AgentToolInvocationModel.id)
                .where(
                    AgentToolInvocationModel.owner_id == context.user_id,
                    AgentToolInvocationModel.conversation_id == context.session_id,
                    AgentToolInvocationModel.project_id == context.extra["project_id"],
                    AgentToolInvocationModel.task_id == uuid.UUID(task_id),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if link is None and getattr(get_settings(), "dataset_discovery_readonly", False):
            from cygnusx.infrastructure.database.models.dataset import DatasetIngestionModel

            ingestions = (
                (
                    await self.db.execute(
                        select(DatasetIngestionModel).where(
                            DatasetIngestionModel.user_id == uuid.UUID(context.user_id),
                            DatasetIngestionModel.project_id
                            == uuid.UUID(context.extra["project_id"]),
                            DatasetIngestionModel.agent_session_id == context.session_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            link = next((row.id for row in ingestions if task_id in row.task_ids), None)
            if link is None:
                from cygnusx.infrastructure.database.models.dataset import DatasetAnalysisLinkModel

                proposals = (
                    (
                        await self.db.execute(
                            select(DatasetAnalysisLinkModel).where(
                                DatasetAnalysisLinkModel.task_id == uuid.UUID(task_id)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                link = next(
                    (
                        row.id
                        for row in proposals
                        if row.normalized_request.get("owner_id") == context.user_id
                        and row.normalized_request.get("project_id") == context.extra["project_id"]
                        and row.normalized_request.get("session_id") == context.session_id
                    ),
                    None,
                )
        if link is None:
            raise NotFoundError("当前会话没有该任务关联")
        return TaskStatusView(
            **{
                "task_id": str(task.id),
                "status": task.status,
                "progress": None,
                "progress_status": "unavailable",
                "error_summary": task.error_message,
                "task_url": f"/tasks/{task.id}",
            }
        ).model_dump()

    async def related(self, context: ToolInvocationContext) -> list[dict[str, Any]]:
        rows = (
            (
                await self.db.execute(
                    select(AgentToolInvocationModel)
                    .where(
                        AgentToolInvocationModel.owner_id == context.user_id,
                        AgentToolInvocationModel.conversation_id == context.session_id,
                        AgentToolInvocationModel.project_id == context.extra["project_id"],
                    )
                    .order_by(AgentToolInvocationModel.created_at.desc())
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        result = []
        for row in rows:
            state = row.status
            record = None
            if row.confirmation_id and not row.task_id:
                record = await self.confirmations.get_status(context.user_id, row.confirmation_id)
                state = (
                    record.status
                    if record and datetime.now(UTC) <= record.expires_at
                    else "EXPIRED"
                )
            item = {
                "invocation_id": str(row.id),
                "capability_id": row.capability_id,
                "project_id": row.project_id,
                "state": state,
                "preview": row.preview,
                "parameters_hash": row.parameters_hash,
                "task_id": str(row.task_id) if row.task_id else None,
                "error_code": row.error_code,
                "write_enabled": False,
            }
            if row.task_id:
                item["task"] = await self.task_status(context, str(row.task_id))
            if (
                record
                and datetime.now(UTC) <= record.expires_at
                and record.parameter_hash == row.parameters_hash
            ):
                item["proposal"] = {
                    "proposal_id": str(row.id),
                    "conversation_id": context.session_id,
                    "operation": row.preview.get("operation"),
                    "project_id": row.project_id,
                    "parameters_hash": row.parameters_hash,
                    "preview": row.preview,
                    "normalized_parameters": record.normalized_request.get("parameters", {}),
                    "confirmation_id": row.confirmation_id,
                    "expires_at": record.expires_at.isoformat(),
                    "state": state,
                    "write_enabled": False,
                    "gate": "WRITE_GATE_BLOCKED",
                }
            if row.capability_id == "dataset.prepare_import" and row.project_id:
                from cygnusx.application.services.dataset_import_service import DatasetImportService
                from cygnusx.infrastructure.database.models.dataset import DatasetIngestionModel

                ingestion = (
                    await self.db.execute(
                        select(DatasetIngestionModel).where(
                            DatasetIngestionModel.invocation_id == row.id,
                            DatasetIngestionModel.user_id == uuid.UUID(context.user_id),
                            DatasetIngestionModel.project_id == uuid.UUID(row.project_id),
                            DatasetIngestionModel.agent_session_id == context.session_id,
                        )
                    )
                ).scalar_one_or_none()
                if ingestion:
                    item["dataset_import"] = await DatasetImportService(self.db).view(
                        uuid.UUID(context.user_id), uuid.UUID(row.project_id), ingestion.id
                    )
            if row.capability_id == "analysis.prepare_from_dataset" and row.project_id:
                from cygnusx.application.services.dataset_analysis_service import (
                    DatasetAnalysisService,
                )
                from cygnusx.infrastructure.database.models.dataset import DatasetAnalysisLinkModel

                proposals = (
                    (
                        await self.db.execute(
                            select(DatasetAnalysisLinkModel).where(
                                DatasetAnalysisLinkModel.normalized_request[
                                    "invocation_id"
                                ].as_string()
                                == str(row.id)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for proposal in proposals:
                    bound = proposal.normalized_request
                    if (
                        bound.get("owner_id") == context.user_id
                        and bound.get("project_id") == row.project_id
                        and bound.get("session_id") == context.session_id
                    ):
                        item["dataset_analysis"] = await DatasetAnalysisService(self.db).view(
                            uuid.UUID(context.user_id),
                            uuid.UUID(row.project_id),
                            uuid.UUID(bound["dataset_id"]),
                            proposal.version_id,
                            proposal.id,
                        )
            result.append(item)
        return result

    async def execute(self, context: ToolInvocationContext, proposal_id: str) -> dict[str, Any]:
        """Durable dedupe protocol, unreachable until runtime gates are reviewed.

        A separate committed SUBMITTING reservation prevents retries after ambiguous
        DB/queue failures. No automatic replay or exactly-once claim.
        """
        if not WRITE_RUNTIME_ACCEPTED:
            require_agent_write_gate("analysis.submit")
        context = await self.context(context.user_id, context.session_id)
        row = await self.proposal(context, proposal_id, lock=True)
        operation = row.preview.get("operation", "")
        require_agent_write_gate(operation)
        if row.task_id:
            return await self.task_status(context, str(row.task_id))
        if row.status in {"SUBMITTING", "RECONCILIATION_REQUIRED"}:
            raise ConflictError(
                "提交结果未知，需人工对账，禁止自动重放", code="RECONCILIATION_REQUIRED"
            )
        if not row.confirmation_id:
            raise ValidationError("缺少人工确认")
        record = await self.confirmations.get_status(context.user_id, row.confirmation_id)
        if record is None or record.parameter_hash != row.parameters_hash:
            raise ConflictError("确认已过期或参数摘要不一致")
        bound = record.normalized_request
        if any(
            bound.get(k) != v
            for k, v in {
                "owner_id": context.user_id,
                "project_id": row.project_id,
                "conversation_id": context.session_id,
                "proposal_id": proposal_id,
                "operation": operation,
            }.items()
        ):
            raise AuthorizationError("确认上下文不匹配")
        await self.confirmations.consume_tool_confirmation(
            context.user_id, row.confirmation_id, "bioops:" + operation, bound
        )
        row.status = "SUBMITTING"
        await self.db.commit()
        try:
            if operation == "downloads.submit":
                task = await DownloadService(self.db).submit(
                    context.user_id, DownloadRequest.model_validate(bound["parameters"])
                )
            elif operation == "analysis.submit":
                request = TaskSubmitRequest.model_validate(bound["parameters"])
                task = await TaskService(self.db).submit(context.user_id, request)
            else:
                raise ValidationError("取消未实现，保持禁止")
            row.task_id = task.id
            row.status = "QUEUED"
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            # The committed SUBMITTING record remains authoritative even if this
            # process cannot persist a more specific error after the side effect.
            raise ConflictError("提交结果需要人工对账", code="RECONCILIATION_REQUIRED") from None
        return await self.task_status(context, str(task.id))
