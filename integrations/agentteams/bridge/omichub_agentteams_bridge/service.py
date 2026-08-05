"""Business guardrails for Bridge operations; no direct database or task-service access."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .audit import AuditStore
from .case_store import CaseStore
from .client import OmicHubClient
from .config import BridgeSettings
from .models import (
    ApprovalRequest,
    ApprovalResponse,
    CancelTaskRequest,
    CaseCloseRequest,
    CaseCloseResponse,
    CaseCreateRequest,
    CaseEventResponse,
    CaseListResponse,
    CaseRecord,
    CaseStateUpdate,
    EvidenceRequest,
    EvidenceResponse,
    PreflightInputSnapshot,
    PreflightRequest,
    PreflightResponse,
    QualityGateRequest,
    QualityGateResponse,
    SubmitTaskRequest,
    TaskReceipt,
    WorkerInboxItem,
    WorkerInboxResponse,
    WorkItemCreateRequest,
    WorkItemRecord,
    WorkItemUpdateRequest,
)
from .security import ApprovalSigner


class BridgeService:
    _EXTERNAL_WORKERS = frozenset({"agent-code", "agent-viz", "agent-scrna"})
    def __init__(
        self, settings: BridgeSettings, client: OmicHubClient, audit: AuditStore, cases: CaseStore
    ) -> None:
        self._settings = settings
        self._client = client
        self._audit = audit
        self._cases = cases
        self._approval_signer = ApprovalSigner(settings.approval_signing_secret)

    async def assign_work_item(
        self, case_id: str, request: WorkItemCreateRequest, actor: str
    ) -> WorkItemRecord:
        if request.target not in {
            "data-steward",
            "workflow-operator",
            "quality-auditor",
            "delivery-reporter",
            "agent-code",
            "agent-viz",
            "agent-scrna",
        }:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid work item target"
            )
        if request.target in {"agent-code", "agent-viz", "agent-scrna"} and not request.read_only:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Professional agent work items must be read-only",
            )
        work_item = WorkItemRecord(**request.model_dump(), updated_at=datetime.now(UTC))
        case = await self._cases.add_work_item(case_id, work_item)
        await self._audit.record(
            case_id=case.case_id,
            actor=actor,
            event_type="work_item.assigned",
            payload={
                "work_item_id": work_item.work_item_id,
                "target": work_item.target,
                "objective": work_item.objective,
                "skill_name": work_item.skill_name,
                "context_refs": [ref.model_dump() for ref in work_item.context_refs],
            },
        )
        return work_item

    async def reconcile_case(self, case_id: str, actor: str) -> CaseRecord:
        """Advance a submitted Case only from observed OmicHub task state.

        Reconciliation creates the next assigned Work Item but never invents a quality decision
        or delivery manifest. It is safe to call repeatedly from a Manager/Controller poller.
        """
        case = await self._cases.get(case_id)
        if case.status != "executing" or not case.omic_task_ids:
            return case

        task_id = case.omic_task_ids[-1]
        task = await self._client.get_task(task_id)
        task_status = str(task.get("status", "")).lower()
        if task_status == "success":
            case = await self._cases.transition(case_id, "quality_running")
            await self._audit.record(
                case_id=case_id,
                actor=actor,
                event_type="omic_task.completed",
                payload={"omic_task_id": task_id, "status": task_status},
            )
            await self._ensure_work_item(
                case,
                WorkItemRecord(
                    work_item_id="quality-01",
                    parent_work_item_id=self._existing_work_item_id(case, "submit-01"),
                    target="quality-auditor",
                    objective="核对成功任务的 QC、产物完整性和可交付性，提交可追溯质量结论。",
                    skill_name="quality-gate",
                    context_refs=[
                        case.project_ref,
                        {"kind": "task", "id": task_id},
                    ],
                    read_only=True,
                    updated_at=datetime.now(UTC),
                ),
                actor,
            )
            return await self._cases.get(case_id)
        if task_status in {"failed", "error"}:
            case = await self._cases.transition(case_id, "execution_failed")
            await self._audit.record(
                case_id=case_id,
                actor=actor,
                event_type="omic_task.failed",
                payload={"omic_task_id": task_id, "status": task_status},
            )
        return case

    async def update_work_item(
        self, case_id: str, work_item_id: str, request: WorkItemUpdateRequest, actor: str
    ) -> WorkItemRecord:
        work_item = await self._cases.get_work_item(case_id, work_item_id)
        if actor not in {"bioops-manager", work_item.target}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Identity cannot update this work item",
            )
        if request.status == "pending":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot reset work item to pending",
            )
        if actor != "bioops-manager" and request.status == "in_progress":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Use the claim endpoint to start a work item",
            )
        if actor != "bioops-manager" and work_item.status != "in_progress":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Work item must be claimed before completion",
            )
        updated = work_item.model_copy(
            update={
                "status": request.status,
                "summary": request.summary,
                "findings": request.findings,
                "updated_at": datetime.now(UTC),
            }
        )
        await self._cases.update_work_item(case_id, work_item_id, updated)
        event_type = "skill.finished" if request.status == "completed" else "skill.failed"
        await self._audit.record(
            case_id=case_id,
            actor=actor,
            event_type=event_type,
            payload={
                "work_item_id": work_item_id,
                "skill_name": work_item.skill_name,
                "status": request.status,
                "summary": request.summary,
                "findings": [finding.model_dump() for finding in request.findings],
            },
        )
        return updated

    async def claim_work_item(self, case_id: str, work_item_id: str, actor: str) -> WorkItemRecord:
        work_item = await self._cases.claim_work_item(case_id, work_item_id, actor)
        await self._audit.record(
            case_id=case_id,
            actor=actor,
            event_type="work_item.claimed",
            payload={
                "work_item_id": work_item.work_item_id,
                "skill_name": work_item.skill_name,
                "lease_seconds": work_item.deadline_seconds,
            },
        )
        return work_item

    async def create_case(self, request: CaseCreateRequest, actor: str) -> CaseRecord:
        now = datetime.now(UTC)
        case = await self._cases.create(
            CaseRecord(
                case_id=request.case_id,
                project_ref=request.project_ref,
                intent=request.intent,
                requester_ref=request.requester_ref,
                team_id=request.team_id,
                element_room_url=request.element_room_url,
                origin_consultation_id=request.origin_consultation_id,
                consultation_summary=request.consultation_summary,
                created_at=now,
                updated_at=now,
            )
        )
        await self._audit.record(
            case_id=case.case_id,
            actor=actor,
            event_type="case.created",
            payload={
                "project_ref": request.project_ref.model_dump(),
                "intent": request.intent,
                "origin_consultation_id": request.origin_consultation_id,
            },
        )
        return case

    async def get_case(self, case_id: str, actor: str) -> CaseRecord:
        case = await self._cases.get(case_id)
        self._require_case_access(case, actor)
        return case

    async def get_case_view(self, case_id: str, actor: str) -> dict[str, Any]:
        case = await self.get_case(case_id, actor)
        if actor == "bioops-manager":
            return case.model_dump(mode="json")
        return {
            "case_id": case.case_id,
            "project_ref": case.project_ref.model_dump(mode="json"),
            "intent": case.intent,
            "team_id": case.team_id,
            "element_room_url": case.element_room_url,
            "origin_consultation_id": case.origin_consultation_id,
            "consultation_summary": case.consultation_summary,
            "status": case.status,
            "omic_task_ids": case.omic_task_ids,
            "quality_decision": case.quality_decision,
            "manifest_uri": case.manifest_uri,
            "work_items": [
                work_item.model_dump(mode="json")
                for work_item in case.work_items
                if work_item.target == actor
            ],
            "created_at": case.created_at.isoformat(),
            "updated_at": case.updated_at.isoformat(),
        }

    async def list_worker_inbox(self, actor: str) -> WorkerInboxResponse:
        if actor in self._EXTERNAL_WORKERS:
            await self._audit.record(
                case_id="__bridge_health__",
                actor=actor,
                event_type="worker.inbox_polled",
                payload={},
            )
        assignments = await self._cases.list_assigned_work_items(actor, {"pending", "in_progress"})
        if actor in self._EXTERNAL_WORKERS:
            for case, work_item in assignments:
                await self._audit.record(
                    case_id=case.case_id,
                    actor=actor,
                    event_type="worker.inbox_polled",
                    payload={"work_item_id": work_item.work_item_id},
                )
        items = [
            WorkerInboxItem(
                case_id=case.case_id,
                project_ref=case.project_ref,
                intent=case.intent,
                status=case.status,
                omic_task_ids=case.omic_task_ids,
                quality_decision=case.quality_decision,
                work_item=work_item,
            )
            for case, work_item in assignments
        ]
        return WorkerInboxResponse(items=items, total=len(items))

    async def list_cases(
        self,
        requester_ref: str | None = None,
        *,
        case_status: str | None = None,
        project_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CaseListResponse:
        cases = await self._cases.list(requester_ref)
        if case_status is not None:
            cases = [case for case in cases if case.status == case_status]
        if project_id is not None:
            cases = [case for case in cases if case.project_ref.id == project_id]
        total = len(cases)
        if cursor is not None:
            try:
                start = (
                    next(index for index, case in enumerate(cases) if case.case_id == cursor) + 1
                )
            except StopIteration:
                raise HTTPException(status_code=422, detail="Invalid Case cursor") from None
            cases = cases[start:]
        items = cases[:limit]
        next_cursor = items[-1].case_id if len(cases) > len(items) else None
        return CaseListResponse(items=items, total=total, next_cursor=next_cursor)

    async def update_case_state(
        self, case_id: str, request: CaseStateUpdate, actor: str
    ) -> CaseRecord:
        case = await self._cases.transition(case_id, request.status)
        await self._audit.record(
            case_id=case_id,
            actor=actor,
            event_type="case.state_changed",
            payload={
                "status": request.status,
                "reason": request.reason,
                "work_item_id": request.work_item_id,
            },
        )
        return case

    async def get_case_events(
        self, case_id: str, actor: str, *, cursor: str | None = None, limit: int = 100
    ) -> CaseEventResponse:
        case = await self._cases.get(case_id)
        self._require_case_access(case, actor)
        events = await self._audit.list_events(case_id)
        if cursor is not None:
            try:
                start = (
                    next(index for index, event in enumerate(events) if event["event_id"] == cursor)
                    + 1
                )
            except StopIteration:
                raise HTTPException(status_code=422, detail="Invalid event cursor") from None
            events = events[start:]
        items = events[:limit]
        next_cursor = items[-1]["event_id"] if len(events) > len(items) else None
        return CaseEventResponse(case_id=case_id, events=items, next_cursor=next_cursor)

    async def stream_case_events(
        self,
        case_id: str,
        actor: str,
        *,
        cursor: str | None = None,
        watch_seconds: int = 60,
    ) -> AsyncIterator[dict[str, Any]]:
        """Native bounded stream of newly recorded Bridge audit events."""
        await self.get_case(case_id, actor)
        next_cursor = cursor
        for _ in range(max(1, watch_seconds)):
            page = await self.get_case_events(case_id, actor, cursor=next_cursor, limit=100)
            for event in page.events:
                yield event
            if page.events:
                next_cursor = page.events[-1]["event_id"]
            await asyncio.sleep(1)

    async def metrics(self) -> dict[str, int]:
        return await self._audit.metrics()

    async def worker_health(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        configured_identities = self._settings.identity_secrets()
        heartbeats = await self._audit.worker_heartbeats(set(self._EXTERNAL_WORKERS))
        workers = []
        for worker in sorted(self._EXTERNAL_WORKERS):
            last_seen = heartbeats[worker]
            age_seconds = int((now - last_seen).total_seconds()) if last_seen else None
            configured = worker in configured_identities
            active = bool(configured and age_seconds is not None and age_seconds <= self._settings.worker_heartbeat_ttl_seconds)
            workers.append(
                {
                    "identity": worker,
                    "configured": configured,
                    "active": active,
                    "last_seen_at": last_seen.isoformat() if last_seen else None,
                    "age_seconds": age_seconds,
                }
            )
        return {
            "allowed_flows": sorted(self._settings.allowed_flows()),
            "worker_heartbeat_ttl_seconds": self._settings.worker_heartbeat_ttl_seconds,
            "workers": workers,
        }

    async def list_flows(self) -> dict[str, Any]:
        flows = await self._client.list_flows()
        items = flows.get("items", [])
        if not isinstance(items, list):
            raise HTTPException(status_code=502, detail="OmicHub returned malformed flow list")
        allowed = self._settings.allowed_flows()
        flows["items"] = [
            item for item in items if isinstance(item, dict) and item.get("id") in allowed
        ]
        flows["total"] = len(flows["items"])
        return flows

    async def preflight(self, request: PreflightRequest, actor: str) -> PreflightResponse:
        findings = []
        consultation_summary = " ".join(str(request.consultation_summary or "").split())
        if consultation_summary:
            findings.append(
                (
                    "CONSULTATION_CONTEXT",
                    "info",
                    f"预检已引用会诊纪要：{consultation_summary[:300]}",
                )
            )
        if request.flow_id not in self._settings.allowed_flows():
            findings.append(("FLOW_NOT_ALLOWED", "error", "请求的流程不在 Bridge 白名单中。"))
        if not request.sample_sheet:
            findings.append(("MISSING_SAMPLE_SHEET", "error", "提交前必须提供样本表引用或内容。"))
        elif any(not row.get("sample") for row in request.sample_sheet):
            findings.append(("MISSING_SAMPLE", "error", "样本表存在缺少 sample 字段的记录。"))
        if request.comparisons is not None and any(
            not comparison.get("control") or not comparison.get("treatment")
            for comparison in request.comparisons
        ):
            findings.append(
                ("INVALID_COMPARISON", "error", "comparison 必须同时包含 control 和 treatment。")
            )
        has_errors = any(item[1] == "error" for item in findings)
        response = PreflightResponse(
            case_id=request.case_id,
            status="blocked" if has_errors else "passed",
            findings=[
                {
                    "code": code,
                    "severity": severity,
                    "message": message,
                    "evidence_refs": request.context_refs,
                }
                for code, severity, message in findings
            ],
            next_actions=["request_user_correction"] if has_errors else ["request_submission_approval"],
        )
        case = await self._cases.get(request.case_id)
        if case.status == "preflight_blocked":
            await self._cases.transition(request.case_id, "waiting_for_correction")
            case = await self._cases.get(request.case_id)
        if case.status in {"received", "waiting_for_correction"}:
            await self._cases.transition(request.case_id, "preflight_running")
        await self._cases.save_preflight_input(
            request.case_id,
            None
            if has_errors
            else PreflightInputSnapshot(
                flow_id=request.flow_id,
                sample_sheet=request.sample_sheet,
                comparisons=request.comparisons,
                context_refs=request.context_refs,
                consultation_summary=request.consultation_summary,
            ),
        )
        await self._cases.transition(
            request.case_id,
            "preflight_blocked" if has_errors else "approval_pending",
        )
        await self._audit.record(
            case_id=request.case_id,
            actor=actor,
            event_type="skill.finished",
            payload={
                "skill_name": "project-preflight",
                "status": response.status,
                "finding_count": len(findings),
                "summary": (
                    "预检已引用会诊纪要并通过。"
                    if consultation_summary and not has_errors
                    else "预检已引用会诊纪要，但仍需修正输入问题。"
                    if consultation_summary
                    else "预检已通过。"
                    if not has_errors
                    else "预检发现需要修正的输入问题。"
                ),
                "findings": response.findings,
            },
        )
        if request.work_item_id:
            await self._update_bound_work_item(
                request.case_id,
                request.work_item_id,
                actor,
                work_item_status="blocked" if has_errors else "completed",
                summary=response.next_actions[0],
                findings=response.findings,
            )
        return response

    async def issue_approval(self, request: ApprovalRequest, actor: str) -> ApprovalResponse:
        case = await self._cases.get(request.case_id)
        if request.action == "submit_task" and case.status != "approval_pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task submission approval requires a passed preflight",
            )
        if request.action == "submit_task" and (
            case.preflight_input is None or case.preflight_input.flow_id != request.flow_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task submission approval requires a matching preflight input snapshot",
            )
        if request.action == "cancel_task" and request.task_id not in case.omic_task_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Task does not belong to the Case",
            )
        token, approval_id, expires_at = self._approval_signer.issue(
            case_id=request.case_id,
            action=request.action,
            flow_id=request.flow_id,
            task_id=request.task_id,
            ttl_seconds=request.ttl_seconds,
        )
        await self._audit.record(
            case_id=request.case_id,
            actor=actor,
            event_type="approval.resolved",
            payload={
                "approval_id": approval_id,
                "action": request.action,
                "expires_at": expires_at.isoformat(),
            },
        )
        return ApprovalResponse(approval_id=approval_id, token=token, expires_at=expires_at)

    async def submit_task(self, request: SubmitTaskRequest, actor: str) -> TaskReceipt:
        if request.task.flow_id not in self._settings.allowed_flows():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Flow is not allowed")
        self._approval_signer.verify(
            request.approval_token,
            case_id=request.case_id,
            action="submit_task",
            flow_id=request.task.flow_id,
        )
        case = await self._cases.get(request.case_id)
        snapshot = case.preflight_input
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task submission requires a passed preflight input snapshot",
            )
        if (
            request.task.flow_id != snapshot.flow_id
            or request.task.sample_sheet != snapshot.sample_sheet
            or request.task.comparisons != snapshot.comparisons
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Task input differs from the approved preflight snapshot",
            )
        prior = await self._audit.get_receipt(request.idempotency_key)
        if prior is not None:
            return TaskReceipt(**prior).model_copy(update={"idempotent_replay": True})
        task_data = await self._client.submit_task(request.task.model_dump())
        omic_task_id = str(task_data.get("id", ""))
        if not omic_task_id:
            raise HTTPException(status_code=502, detail="OmicHub submit response has no task ID")
        receipt = TaskReceipt(
            case_id=request.case_id,
            omic_task_id=omic_task_id,
            status=str(task_data.get("status", "submitted")),
            submitted_at=datetime.now(UTC),
        )
        await self._audit.save_receipt(request.idempotency_key, receipt.model_dump(mode="json"))
        await self._cases.attach_task(
            request.case_id, omic_task_id, request.task.model_dump(mode="json")
        )
        if case.status == "approval_pending":
            await self._cases.transition(request.case_id, "approved")
            await self._cases.transition(request.case_id, "executing")
        await self._audit.record(
            case_id=request.case_id,
            actor=actor,
            event_type="omic_task.submitted",
            payload={
                "omic_task_id": omic_task_id,
                "flow_id": request.task.flow_id,
                "idempotency_key": request.idempotency_key,
                "receipt": receipt.model_dump(mode="json"),
            },
        )
        if request.work_item_id:
            await self._update_bound_work_item(
                request.case_id,
                request.work_item_id,
                actor,
                work_item_status="completed",
                summary=f"OmicHub task {omic_task_id} submitted",
            )
        return receipt

    async def _ensure_work_item(
        self, case: CaseRecord, work_item: WorkItemRecord, actor: str
    ) -> WorkItemRecord:
        ensured, created = await self._cases.ensure_work_item(case.case_id, work_item)
        if created:
            await self._audit.record(
                case_id=case.case_id,
                actor=actor,
                event_type="work_item.assigned",
                payload={
                    "work_item_id": ensured.work_item_id,
                    "target": ensured.target,
                    "objective": ensured.objective,
                    "skill_name": ensured.skill_name,
                    "context_refs": [ref.model_dump() for ref in ensured.context_refs],
                },
            )
        return ensured

    async def get_task(self, task_id: str, actor: str) -> dict[str, Any]:
        case = await self._cases.get_by_task(task_id)
        self._require_case_access(case, actor)
        task = await self._client.get_task(task_id)
        await self._audit.record(
            case_id=case.case_id,
            actor=actor,
            event_type="omic_task.status_changed",
            payload={"omic_task_id": task_id, "status": task.get("status")},
        )
        return task

    async def get_artifacts(self, task_id: str, actor: str) -> dict[str, Any]:
        case = await self._cases.get_by_task(task_id)
        self._require_case_access(case, actor)
        task = await self._client.get_task(task_id)
        result_available = bool(task.get("result_path")) and task.get("status") == "success"
        artifacts = {
            "task_id": task_id,
            "status": task.get("status"),
            "artifacts": [
                {
                    "kind": "task_result",
                    "uri": f"omic://tasks/{task_id}/result",
                    "available": result_available,
                }
            ]
            if result_available
            else [],
        }
        await self._audit.record(
            case_id=case.case_id,
            actor=actor,
            event_type="skill.finished",
            payload={
                "skill_name": "artifact-inspect",
                "omic_task_id": task_id,
                "artifact_count": len(artifacts["artifacts"]),
            },
        )
        return artifacts

    async def quality_gate(
        self, task_id: str, request: QualityGateRequest, actor: str
    ) -> QualityGateResponse:
        case = await self._cases.get_by_task(task_id)
        self._require_case_access(case, actor)
        if case.case_id != request.case_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Case and task mismatch"
            )
        if case.status == "executing":
            await self._cases.transition(case.case_id, "quality_running")
            case = await self._cases.get(case.case_id)
        if case.status != "quality_running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Task is not ready for quality gate"
            )
        decision = QualityGateResponse(
            case_id=case.case_id,
            task_id=task_id,
            decision=request.decision,
            rule_version=request.rule_version,
            summary=request.summary,
            evidence_refs=request.evidence_refs,
            artifact_hashes=request.artifact_hashes,
            recorded_at=datetime.now(UTC),
        )
        await self._cases.set_quality(case.case_id, request.decision)
        next_status = (
            "delivery_ready"
            if request.decision in {"passed", "warning", "manual_review"}
            else "quality_blocked"
        )
        await self._cases.transition(case.case_id, next_status)
        await self._audit.record(
            case_id=case.case_id,
            actor=actor,
            event_type="quality.decision",
            payload=decision.model_dump(mode="json"),
        )
        if request.work_item_id:
            await self._update_bound_work_item(
                case.case_id,
                request.work_item_id,
                actor,
                work_item_status="blocked" if request.decision == "blocked" else "completed",
                summary=request.summary,
            )
        if next_status == "delivery_ready":
            await self._ensure_work_item(
                await self._cases.get(case.case_id),
                WorkItemRecord(
                    work_item_id="delivery-01",
                    parent_work_item_id=self._existing_work_item_id(
                        await self._cases.get(case.case_id), request.work_item_id
                    ),
                    target="delivery-reporter",
                    objective="汇总审批、任务、质量与产物证据，生成交付 manifest 并关闭 Case。",
                    skill_name="delivery-pack",
                    context_refs=[
                        case.project_ref,
                        {"kind": "task", "id": task_id},
                    ],
                    read_only=True,
                    updated_at=datetime.now(UTC),
                ),
                actor,
            )
        return decision

    async def _update_bound_work_item(
        self,
        case_id: str,
        work_item_id: str,
        actor: str,
        *,
        work_item_status: str,
        summary: str,
        findings: list[Any] | None = None,
    ) -> None:
        work_item = await self._cases.get_work_item(case_id, work_item_id)
        if work_item.target != actor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Work item target mismatch"
            )
        updated = work_item.model_copy(
            update={
                "status": work_item_status,
                "summary": summary,
                "findings": findings or [],
                "updated_at": datetime.now(UTC),
            }
        )
        await self._cases.update_work_item(case_id, work_item_id, updated)
        await self._audit.record(
            case_id=case_id,
            actor=actor,
            event_type="skill.finished" if work_item_status == "completed" else "skill.failed",
            payload={
                "work_item_id": work_item_id,
                "skill_name": work_item.skill_name,
                "status": work_item_status,
                "summary": summary,
            },
        )

    async def close_case(self, request: CaseCloseRequest, actor: str) -> CaseCloseResponse:
        case = await self._cases.get(request.case_id)
        self._require_case_access(case, actor)
        if case.status != "delivery_ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Case is not delivery-ready"
            )
        if case.quality_decision != request.quality_decision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Quality decision mismatch"
            )
        events = await self._audit.list_events(case.case_id)
        task_snapshots: list[dict[str, Any]] = []
        for task_id in case.omic_task_ids:
            try:
                task_snapshots.append(await self._client.get_task(task_id))
            except Exception as exc:
                task_snapshots.append({"id": task_id, "snapshot_error": type(exc).__name__})
        manifest = {
            "schema_version": "1.0",
            "case": case.model_dump(mode="json"),
            "agent_identities": [
                "bioops-manager",
                "data-steward",
                "workflow-operator",
                "quality-auditor",
                "delivery-reporter",
            ],
            "skill_versions": {
                "project-preflight": "1.0",
                "workflow-submit": "1.0",
                "quality-gate": "1.0",
                "delivery-pack": "1.0",
            },
            "input_refs": [case.project_ref.model_dump()],
            "task_ids": case.omic_task_ids,
            "task_specs": case.task_specs,
            "omic_task_snapshots": task_snapshots,
            "quality": {"decision": request.quality_decision},
            "approval_events": [
                event for event in events if event["event_type"].startswith("approval.")
            ],
            "audit_events": events,
            "remediation_summary": request.remediation_summary,
            "runbook_ref": request.runbook_ref.model_dump() if request.runbook_ref else None,
        }
        manifest_dir = Path(self._settings.manifest_dir)
        await asyncio.to_thread(manifest_dir.mkdir, parents=True, exist_ok=True)
        manifest_path = manifest_dir / f"{case.case_id}.delivery_manifest.json"
        await asyncio.to_thread(
            manifest_path.write_text, json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8"
        )
        closed = await self._cases.close(case.case_id, str(manifest_path))
        await self._audit.record(
            case_id=case.case_id,
            actor=actor,
            event_type="case.closed",
            payload={"manifest_uri": str(manifest_path)},
        )
        return CaseCloseResponse(
            case_id=closed.case_id,
            status="closed",
            manifest_uri=str(manifest_path),
            manifest=manifest,
        )

    @staticmethod
    def _existing_work_item_id(case: CaseRecord, work_item_id: str | None) -> str | None:
        if work_item_id and any(item.work_item_id == work_item_id for item in case.work_items):
            return work_item_id
        return None

    @staticmethod
    def _require_case_access(case: CaseRecord, actor: str) -> None:
        if actor == "bioops-manager":
            return
        if any(work_item.target == actor for work_item in case.work_items):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Case is not assigned to this worker identity",
        )

    async def cancel_task(
        self, task_id: str, request: CancelTaskRequest, actor: str
    ) -> dict[str, Any]:
        case = await self._cases.get_by_task(task_id)
        self._require_case_access(case, actor)
        if case.case_id != request.case_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Case and task mismatch"
            )
        self._approval_signer.verify(
            request.approval_token,
            case_id=request.case_id,
            action="cancel_task",
            task_id=task_id,
        )
        task = await self._client.cancel_task(task_id)
        if case.status not in {"closed", "cancelled"}:
            await self._cases.transition(case.case_id, "cancelled")
        await self._audit.record(
            case_id=request.case_id,
            actor=actor,
            event_type="omic_task.cancelled",
            payload={
                "omic_task_id": task_id,
                "reason": request.reason,
                "status": task.get("status"),
            },
        )
        return task

    async def record_evidence(
        self, case_id: str, request: EvidenceRequest, actor: str
    ) -> EvidenceResponse:
        case = await self._cases.get(case_id)
        self._require_case_access(case, actor)
        work_item = await self._cases.get_work_item(case_id, request.work_item_id)
        if actor != "bioops-manager" and work_item.target != actor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Identity cannot record evidence for this work item",
            )
        sanitized_payload = _sanitize_payload(request.payload, self._settings.max_evidence_bytes)
        event_id, recorded_at = await self._audit.record(
            case_id=case_id,
            actor=actor,
            event_type=request.event_type,
            payload={
                "work_item_id": request.work_item_id,
                "summary": request.summary,
                "context_refs": [item.model_dump() for item in request.context_refs],
                "omic_task_id": request.omic_task_id,
                "skill_name": request.skill_name,
                "payload": sanitized_payload,
            },
        )
        return EvidenceResponse(event_id=event_id, recorded_at=recorded_at)


def _sanitize_payload(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    forbidden = {
        "authorization",
        "token",
        "secret",
        "password",
        "api_key",
        "jwt",
        "connection_string",
    }
    cleaned = {
        key: "[redacted]" if key.lower() in forbidden else value for key, value in payload.items()
    }
    if len(str(cleaned).encode()) > max_bytes:
        raise HTTPException(status_code=413, detail="Evidence payload exceeds Bridge size limit")
    return cleaned
