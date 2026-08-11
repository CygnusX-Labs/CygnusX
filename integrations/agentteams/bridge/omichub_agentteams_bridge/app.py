"""FastAPI application for the AgentTeams sidecar Bridge."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, get_args

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from .audit import AuditStore
from .case_store import CaseStore
from .client import GatewayClient, OmicHubClient
from .config import BridgeSettings
from .models import (
    ApprovalRequest,
    CancelTaskRequest,
    CaseCancelRequest,
    CaseCloseRequest,
    CaseCreateRequest,
    CaseStateUpdate,
    CaseStatus,
    EvidenceRequest,
    ExecuteGeneralPlanRequest,
    PlanRevisionRequest,
    PreflightRequest,
    QualityGateRequest,
    QueueApprovedSubmissionRequest,
    ReadOnlyExecutionRequest,
    RetryCaseSubmissionRequest,
    SubmitTaskRequest,
    WorkItemCreateRequest,
    WorkItemHeartbeatRequest,
    WorkItemUpdateRequest,
)
from .security import require_identity, require_role
from .service import BridgeService
from .size_limits import BodySizeLimitMiddleware


async def get_service(request: Request) -> BridgeService:
    return request.app.state.bridge_service


async def authenticate_identity(
    request: Request,
    x_bridge_identity: str | None = Header(default=None),
    x_bridge_token: str | None = Header(default=None),
) -> str:
    return require_identity(request.app.state.bridge_settings, x_bridge_identity, x_bridge_token)


def create_app(
    settings: BridgeSettings | None = None,
    client: OmicHubClient | None = None,
    gateway_client: GatewayClient | None = None,
) -> FastAPI:
    runtime_settings = settings or BridgeSettings()
    runtime_client = client or OmicHubClient(runtime_settings)
    runtime_gateway_client = gateway_client
    if runtime_gateway_client is None and (
        runtime_settings.gateway_url and runtime_settings.gateway_manager_token
    ):
        runtime_gateway_client = GatewayClient(runtime_settings)
    audit_store = AuditStore(
        runtime_settings.audit_log_path,
        runtime_settings.state_store_url,
        f"{runtime_settings.state_store_key_prefix}:audit",
    )
    case_store = CaseStore(
        runtime_settings.case_store_path,
        runtime_settings.state_store_url,
        f"{runtime_settings.state_store_key_prefix}:cases",
    )
    service = BridgeService(
        runtime_settings,
        runtime_client,
        audit_store,
        case_store,
        runtime_gateway_client,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if runtime_settings.omichub_integration_token:
            await service.refresh_capabilities()
        yield
        await runtime_client.aclose()
        if runtime_gateway_client is not None:
            await runtime_gateway_client.aclose()
        await audit_store.aclose()
        await case_store.aclose()

    app = FastAPI(title="OmicHub AgentTeams Bridge", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_request_bytes=runtime_settings.max_request_bytes,
        max_response_bytes=runtime_settings.max_response_bytes,
    )
    app.state.bridge_service = service
    app.state.bridge_settings = runtime_settings

    @app.get("/healthz", tags=["Health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/metrics", tags=["Observability"])
    async def get_metrics(
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict[str, int]:
        require_role(identity, "bioops-manager", "delivery-reporter")
        return await service.metrics()

    @app.get("/v1/health/identity", tags=["Health"])
    async def identity_health(identity: Annotated[str, Depends(authenticate_identity)]) -> dict[str, str]:
        """Authenticated probe used by OmicHub to validate its four Bridge credentials."""
        return {"status": "ok", "identity": identity}

    @app.get("/v1/health/workers", tags=["Health"])
    async def worker_health(
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager")
        return await service.worker_health()

    @app.get("/v1/flows", tags=["Flows"])
    async def list_flows(
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity, "bioops-manager", "data-steward", "workflow-operator", "quality-auditor"
        )
        return await service.list_flows()

    @app.get("/v1/capabilities", tags=["Flows"])
    async def capabilities(
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
        reload: bool = False,
    ) -> dict:
        require_role(identity, "bioops-manager", *service.worker_identities())
        return await service.capabilities(reload=reload)

    @app.post("/v1/cases", status_code=status.HTTP_201_CREATED, tags=["Cases"])
    async def create_case(
        payload: CaseCreateRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager")
        return (await service.create_case(payload, identity)).model_dump(mode="json")

    @app.get("/v1/cases", tags=["Cases"])
    async def list_cases(
        request: Request,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager", "delivery-reporter")
        requester_ref = request.query_params.get("requester_ref")
        if requester_ref is not None and len(requester_ref) > 256:
            raise HTTPException(status_code=422, detail="requester_ref is too long")
        case_status = request.query_params.get("status")
        project_id = request.query_params.get("project_id")
        cursor = request.query_params.get("cursor")
        limit = request.query_params.get("limit", "20")
        if case_status is not None and case_status not in get_args(CaseStatus):
            raise HTTPException(status_code=422, detail="Invalid Case status")
        if project_id is not None and len(project_id) > 256:
            raise HTTPException(status_code=422, detail="project_id is too long")
        if cursor is not None and len(cursor) > 128:
            raise HTTPException(status_code=422, detail="cursor is too long")
        try:
            page_limit = int(limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="limit must be an integer") from exc
        if not 1 <= page_limit <= 100:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
        return (
            await service.list_cases(
                requester_ref,
                case_status=case_status,
                project_id=project_id,
                cursor=cursor,
                limit=page_limit,
            )
        ).model_dump(mode="json")

    @app.get("/v1/cases/{case_id}", tags=["Cases"])
    async def get_case(
        case_id: str,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity,
            "bioops-manager",
            "data-steward",
            "workflow-operator",
            "quality-auditor",
            "delivery-reporter",
            "agent-code",
            "agent-viz",
            "agent-scrna",
            "agent-rnaseq",
            "analysis-worker",
        )
        return await service.get_case_view(case_id, identity)

    @app.get("/v1/work-items/assigned", tags=["Work Items"])
    async def list_assigned_work_items(
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity,
            "data-steward",
            "workflow-operator",
            "quality-auditor",
            "delivery-reporter",
            "agent-code",
            "agent-viz",
            "agent-scrna",
            "agent-rnaseq",
            "analysis-worker",
        )
        return (await service.list_worker_inbox(identity)).model_dump(mode="json")

    @app.post("/v1/cases/{case_id}/state", tags=["Cases"])
    async def update_case_state(
        case_id: str,
        payload: CaseStateUpdate,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager")
        return (await service.update_case_state(case_id, payload, identity)).model_dump(mode="json")

    @app.post("/v1/cases/{case_id}/reconcile", tags=["Cases"])
    async def reconcile_case(
        case_id: str,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager")
        return (await service.reconcile_case(case_id, identity)).model_dump(mode="json")

    @app.post("/v1/cases/{case_id}/plan/revise", tags=["Cases"])
    async def revise_case_plan(
        case_id: str,
        payload: PlanRevisionRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager")
        return (await service.revise_plan(case_id, payload, identity)).model_dump(mode="json")

    @app.post("/v1/maintenance/approval-timeouts", tags=["Maintenance"])
    async def reconcile_approval_timeouts(
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict[str, int]:
        require_role(identity, "bioops-manager")
        return await service.reconcile_approval_timeouts(identity)

    @app.post("/v1/cases/{case_id}/retry", tags=["Cases"])
    async def retry_case_submission(
        case_id: str,
        payload: RetryCaseSubmissionRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager")
        return (
            await service.retry_case_submission(case_id, payload, identity)
        ).model_dump(mode="json")

    @app.post("/v1/cases/{case_id}/work-items", status_code=status.HTTP_201_CREATED, tags=["Cases"])
    async def assign_work_item(
        case_id: str,
        payload: WorkItemCreateRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager")
        return (await service.assign_work_item(case_id, payload, identity)).model_dump(mode="json")

    @app.post("/v1/cases/{case_id}/work-items/{work_item_id}", tags=["Cases"])
    async def update_work_item(
        case_id: str,
        work_item_id: str,
        payload: WorkItemUpdateRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity,
            "bioops-manager",
            "data-steward",
            "workflow-operator",
            "quality-auditor",
            "delivery-reporter",
            "agent-code",
            "agent-viz",
            "agent-scrna",
            "agent-rnaseq",
            "analysis-worker",
        )
        return (
            await service.update_work_item(case_id, work_item_id, payload, identity)
        ).model_dump(mode="json")

    @app.post("/v1/cases/{case_id}/work-items/{work_item_id}/claim", tags=["Work Items"])
    async def claim_work_item(
        case_id: str,
        work_item_id: str,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity,
            "data-steward",
            "workflow-operator",
            "quality-auditor",
            "delivery-reporter",
            "agent-code",
            "agent-viz",
            "agent-scrna",
            "agent-rnaseq",
            "analysis-worker",
        )
        return (await service.claim_work_item(case_id, work_item_id, identity)).model_dump(
            mode="json"
        )

    @app.post("/v1/cases/{case_id}/work-items/{work_item_id}/heartbeat", tags=["Work Items"])
    async def heartbeat_work_item(
        case_id: str,
        work_item_id: str,
        payload: WorkItemHeartbeatRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity,
            "data-steward",
            "workflow-operator",
            "quality-auditor",
            "delivery-reporter",
            "agent-code",
            "agent-viz",
            "agent-scrna",
            "agent-rnaseq",
        )
        return (
            await service.heartbeat_work_item(case_id, work_item_id, payload, identity)
        ).model_dump(mode="json")

    @app.post(
        "/v1/cases/{case_id}/work-items/{work_item_id}/execute-readonly",
        tags=["Work Items"],
    )
    async def execute_readonly_work_item(
        case_id: str,
        work_item_id: str,
        payload: ReadOnlyExecutionRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "agent-code", "agent-viz", "agent-scrna", "agent-rnaseq")
        return (
            await service.execute_readonly_work_item(case_id, work_item_id, payload, identity)
        ).model_dump(mode="json")

    @app.get("/v1/cases/{case_id}/events", tags=["Cases"])
    async def get_case_events(
        case_id: str,
        request: Request,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity,
            "bioops-manager",
            "data-steward",
            "workflow-operator",
            "quality-auditor",
            "delivery-reporter",
        )
        cursor = request.query_params.get("cursor")
        limit = request.query_params.get("limit", "100")
        if cursor is not None and len(cursor) > 128:
            raise HTTPException(status_code=422, detail="cursor is too long")
        try:
            page_limit = int(limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="limit must be an integer") from exc
        if not 1 <= page_limit <= 100:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
        return (
            await service.get_case_events(case_id, identity, cursor=cursor, limit=page_limit)
        ).model_dump(mode="json")

    @app.get("/v1/cases/{case_id}/manifest", tags=["Cases"])
    async def get_manifest(
        case_id: str,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager", "delivery-reporter")
        return await service.get_manifest(case_id, identity)

    @app.get("/v1/cases/{case_id}/events/stream", tags=["Cases"])
    async def stream_case_events(
        case_id: str,
        request: Request,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> StreamingResponse:
        require_role(identity, "bioops-manager", "data-steward", "workflow-operator", "quality-auditor", "delivery-reporter")
        cursor = request.query_params.get("cursor")
        if cursor is not None and len(cursor) > 128:
            raise HTTPException(status_code=422, detail="cursor is too long")
        watch_seconds = request.query_params.get("watch_seconds", "60")
        try:
            duration = int(watch_seconds)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="watch_seconds must be an integer") from exc
        if not 1 <= duration <= 60:
            raise HTTPException(status_code=422, detail="watch_seconds must be between 1 and 60")

        async def event_generator() -> AsyncIterator[str]:
            async for event in service.stream_case_events(
                case_id, identity, cursor=cursor, watch_seconds=duration
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/projects/{project_id}/preflight", tags=["Preflight"])
    async def preflight(
        project_id: str,
        payload: PreflightRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "data-steward")
        if not any(ref.kind == "project" and ref.id == project_id for ref in payload.context_refs):
            payload.context_refs.append({"kind": "project", "id": project_id})
        return (await service.preflight(payload, identity)).model_dump(mode="json")

    @app.post("/v1/approvals", status_code=status.HTTP_201_CREATED, tags=["Approvals"])
    async def create_approval(
        payload: ApprovalRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "approval-authority")
        return (await service.issue_approval(payload, identity)).model_dump(mode="json")

    @app.post("/v1/general-plans/execute", tags=["Approvals"])
    async def execute_general_plan(
        payload: ExecuteGeneralPlanRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "approval-authority")
        return (await service.execute_general_plan(payload.case_id, payload.approval_token, identity)).model_dump(mode="json")

    @app.post("/v1/tasks", status_code=status.HTTP_201_CREATED, tags=["Tasks"])
    async def submit_task(
        payload: SubmitTaskRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "workflow-operator")
        return (await service.submit_task(payload, identity)).model_dump(mode="json")

    @app.post("/v1/approved-submissions", status_code=status.HTTP_201_CREATED, tags=["Approvals"])
    async def queue_approved_submission(
        payload: QueueApprovedSubmissionRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "approval-authority")
        return (await service.queue_approved_submission(payload, identity)).model_dump(mode="json")

    @app.post(
        "/v1/cases/{case_id}/work-items/{work_item_id}/submit-approved",
        status_code=status.HTTP_201_CREATED,
        tags=["Tasks"],
    )
    async def submit_approved_work_item(
        case_id: str,
        work_item_id: str,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "analysis-worker")
        return (
            await service.submit_approved_work_item(case_id, work_item_id, identity)
        ).model_dump(mode="json")

    @app.get("/v1/tasks/{task_id}", tags=["Tasks"])
    async def get_task(
        task_id: str,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity, "bioops-manager", "workflow-operator", "quality-auditor", "delivery-reporter"
        )
        return await service.get_task(task_id, identity)

    @app.get("/v1/tasks/{task_id}/events", tags=["Tasks"])
    async def get_task_events(
        task_id: str,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity, "bioops-manager", "workflow-operator", "quality-auditor", "delivery-reporter"
        )
        return await service.get_task(task_id, identity)

    @app.get("/v1/tasks/{task_id}/artifacts", tags=["Tasks"])
    async def get_task_artifacts(
        task_id: str,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "quality-auditor", "delivery-reporter")
        return await service.get_artifacts(task_id, identity)

    @app.post("/v1/tasks/{task_id}/quality-gate", tags=["Quality"])
    async def quality_gate(
        task_id: str,
        payload: QualityGateRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "quality-auditor")
        return (await service.quality_gate(task_id, payload, identity)).model_dump(mode="json")

    @app.post("/v1/tasks/{task_id}/cancel", tags=["Tasks"])
    async def cancel_task(
        task_id: str,
        payload: CancelTaskRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "workflow-operator")
        return await service.cancel_task(task_id, payload, identity)

    @app.post(
        "/v1/cases/{case_id}/evidence", status_code=status.HTTP_201_CREATED, tags=["Evidence"]
    )
    async def record_evidence(
        case_id: str,
        payload: EvidenceRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(
            identity,
            "bioops-manager",
            "data-steward",
            "workflow-operator",
            "quality-auditor",
            "delivery-reporter",
        )
        return (await service.record_evidence(case_id, payload, identity)).model_dump(mode="json")

    @app.post("/v1/cases/{case_id}/close", tags=["Cases"])
    async def close_case(
        case_id: str,
        payload: CaseCloseRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "delivery-reporter")
        if payload.case_id != case_id:
            raise HTTPException(status_code=400, detail="Case path and payload mismatch")
        return (await service.close_case(payload, identity)).model_dump(mode="json")

    @app.post("/v1/cases/{case_id}/cancel", tags=["Cases"])
    async def cancel_case(
        case_id: str,
        payload: CaseCancelRequest,
        identity: Annotated[str, Depends(authenticate_identity)],
        service: Annotated[BridgeService, Depends(get_service)],
    ) -> dict:
        require_role(identity, "bioops-manager")
        return (await service.cancel_case(case_id, payload, identity)).model_dump(mode="json")

    return app


app = create_app()
