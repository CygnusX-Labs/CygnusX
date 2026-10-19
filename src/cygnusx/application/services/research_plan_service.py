"""Versioned plan metadata and bounded read/prepare coordination via existing Gateway.

No new analysis/download execution adapter. Human plan review never approves a tool.
"""

from __future__ import annotations

import asyncio
import builtins
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.research_delivery import ResearchProvenance
from cygnusx.application.schemas.research_plan import (
    STEP_CONTRACTS,
    Effect,
    PlanPrepare,
    PlanRevision,
    PlanStatus,
    ResearchPlanDraft,
    ResearchPlanView,
    StepStatus,
    StepView,
)
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cygnusx.domain.research.plan_state import plan_digest, ready_steps
from cygnusx.infrastructure.database.models.research_plan import ResearchPlanModel
from cygnusx.infrastructure.database.repositories.dataset_repository import DatasetRepository


def require_plan_enabled() -> None:
    if not get_settings().research_plan_enabled:
        raise AuthorizationError("科研计划功能未启用", code="FEATURE_DISABLED")


class ResearchPlanService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DatasetRepository(db)

    async def scope(self, owner: UUID, project: UUID) -> None:
        require_plan_enabled()
        await self.repo.project(owner, project)
        await self.repo.require_module(owner, "tasks")
        await self.repo.require_module(owner, "reports")

    async def validate_resources(
        self, owner: UUID, project: UUID, draft: ResearchPlanDraft
    ) -> list[str]:
        await self.scope(owner, project)
        settings = get_settings()
        if (
            len(draft.steps) > settings.research_plan_max_steps
            or draft.budget.max_tool_calls > settings.research_plan_max_tool_calls
            or len(draft.model_dump_json().encode()) > settings.research_plan_max_payload_bytes
        ):
            raise ValidationError("计划超出服务器预算", code="PLAN_BUDGET_EXCEEDED")
        gaps = ["LIVE_EXECUTION_BLOCKED"]
        for step in draft.steps:
            args = step.arguments
            if "dataset_id" in args and "version_id" in args:
                version = await self.repo.version(
                    owner, project, UUID(args["dataset_id"]), UUID(args["version_id"])
                )
                if version.handoff is None:
                    gaps.append(f"{step.step_id}:HANDOFF_NOT_FROZEN")
                elif step.kind.value == "ANALYSIS_PREPARE":
                    from cygnusx.application.schemas.dataset import DataHandoff
                    from cygnusx.domain.research.scientific_validation import (
                        check_scientific_inputs,
                    )

                    flow_id = args.get("request", {}).get("flow_id", "")
                    eligibility = check_scientific_inputs(
                        DataHandoff.model_validate(version.handoff), flow_id
                    )
                    gaps.extend(f"{step.step_id}:{gap}" for gap in eligibility.gaps)
            if "task_id" in args:
                from cygnusx.application.services.research_provenance_service import (
                    ResearchProvenanceService,
                )

                graph = await ResearchProvenanceService(self.db).task(owner, UUID(args["task_id"]))
                if graph.project_id != project:
                    raise NotFoundError("Task 不属于当前项目")
            if STEP_CONTRACTS[step.kind][1] in {Effect.MUTATING, Effect.REPORT_PUBLISH}:
                gaps.append(f"{step.step_id}:INDEPENDENT_HUMAN_TOOL_APPROVAL_REQUIRED")
        return sorted(set(gaps))

    async def prepare(
        self,
        owner: UUID,
        project: UUID,
        request: PlanPrepare,
        *,
        previous: ResearchPlanModel | None = None,
    ) -> ResearchPlanView:
        await self.scope(owner, project)
        # Serialize request-key creation and version allocation within the owned project.
        await self.repo.project(owner, project, lock=True)
        digest = plan_digest(request.draft)
        existing = (
            await self.db.execute(
                select(ResearchPlanModel).where(
                    ResearchPlanModel.user_id == owner,
                    ResearchPlanModel.project_id == project,
                    ResearchPlanModel.request_key == str(request.request_key),
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.digest != digest or (
                previous is not None and existing.series_id != previous.series_id
            ):
                raise ConflictError("request_key 已绑定不同计划")
            return await self.view(owner, project, existing.id)
        gaps = await self.validate_resources(owner, project, request.draft)
        plan_id = uuid4()
        steps = [
            StepView(
                step_id=s.step_id,
                kind=s.kind,
                capability_id=STEP_CONTRACTS[s.kind][0],
                effect=STEP_CONTRACTS[s.kind][1],
                approval_required=STEP_CONTRACTS[s.kind][1]
                in {Effect.MUTATING, Effect.REPORT_PUBLISH},
                expected_output=STEP_CONTRACTS[s.kind][2],
                status=StepStatus.WAITING_INPUT,
            ).model_dump(mode="json")
            for s in request.draft.steps
        ]
        row = ResearchPlanModel(
            id=plan_id,
            user_id=owner,
            project_id=project,
            series_id=previous.series_id if previous else plan_id,
            version=previous.version + 1 if previous else 1,
            request_key=str(request.request_key),
            draft=request.draft.model_dump(mode="json"),
            digest=digest,
            status=PlanStatus.READY_FOR_REVIEW,
            steps=steps,
            gaps=gaps,
            events=[{"kind": "PLAN_PREPARED", "at": datetime.now(UTC).isoformat()}],
        )
        self.db.add(row)
        # Persist the referenced version before updating the immediate self-FK.
        # Both flushes remain in the caller's transaction and roll back together.
        await self.db.flush()
        if previous:
            previous.superseded_by = plan_id
            await self.db.flush()
        return await self.view(owner, project, plan_id)

    async def owned(
        self,
        owner: UUID,
        project: UUID,
        plan_id: UUID,
        *,
        lock: bool = False,
    ) -> ResearchPlanModel:
        await self.scope(owner, project)
        query = select(ResearchPlanModel).where(
            ResearchPlanModel.id == plan_id,
            ResearchPlanModel.user_id == owner,
            ResearchPlanModel.project_id == project,
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            raise NotFoundError("计划不存在或无权访问")
        if plan_digest(ResearchPlanDraft.model_validate(row.draft)) != row.digest:
            raise ConflictError("计划摘要不一致", code="PLAN_DIGEST_MISMATCH")
        return row

    async def view(self, owner: UUID, project: UUID, plan_id: UUID) -> ResearchPlanView:
        row = await self.owned(owner, project, plan_id)
        # Every read rechecks resource ownership, even for historical versions.
        await self.validate_resources(owner, project, ResearchPlanDraft.model_validate(row.draft))
        return ResearchPlanView(
            plan_id=row.id,
            project_id=row.project_id,
            version=row.version,
            digest=row.digest,
            status=PlanStatus(row.status),
            draft=ResearchPlanDraft.model_validate(row.draft),
            steps=[StepView.model_validate(s) for s in row.steps],
            gaps=row.gaps,
            created_at=row.created_at,
            reviewed_at=row.reviewed_at,
            superseded_by=row.superseded_by,
        )

    async def list(self, owner: UUID, project: UUID) -> list[ResearchPlanView]:
        await self.scope(owner, project)
        ids = (
            (
                await self.db.execute(
                    select(ResearchPlanModel.id)
                    .where(
                        ResearchPlanModel.user_id == owner,
                        ResearchPlanModel.project_id == project,
                    )
                    .order_by(ResearchPlanModel.created_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        return [await self.view(owner, project, plan_id) for plan_id in ids]

    async def revise(
        self,
        owner: UUID,
        project: UUID,
        plan_id: UUID,
        request: PlanRevision,
    ) -> ResearchPlanView:
        await self.scope(owner, project)
        await self.repo.project(owner, project, lock=True)
        old = await self.owned(owner, project, plan_id, lock=True)
        if old.digest != request.expected_digest or old.superseded_by is not None:
            raise ConflictError("计划版本已变化")
        if old.status in {PlanStatus.RUNNING, PlanStatus.RECONCILIATION_REQUIRED}:
            raise ConflictError("执行中或待对账计划不可修改")
        return await self.prepare(owner, project, request, previous=old)

    async def review(
        self,
        owner: UUID,
        project: UUID,
        plan_id: UUID,
        expected_digest: str,
    ) -> ResearchPlanView:
        """Trusted JWT caller only; review intent, never consume business confirmation."""
        row = await self.owned(owner, project, plan_id, lock=True)
        if row.digest != expected_digest or row.superseded_by:
            raise ConflictError("计划已变化，需重新审阅")
        if row.status not in {PlanStatus.READY_FOR_REVIEW, PlanStatus.APPROVED}:
            raise ConflictError("当前计划不可审阅")
        await self.validate_resources(owner, project, ResearchPlanDraft.model_validate(row.draft))
        if row.reviewed_at is None:
            row.reviewed_at = datetime.now(UTC)
            row.status = PlanStatus.APPROVED
            self.event(row, "HUMAN_PLAN_REVIEWED")
        await self.db.flush()
        return await self.view(owner, project, plan_id)

    @staticmethod
    def event(row: ResearchPlanModel, kind: str, **facts: Any) -> None:
        if len(row.events) >= get_settings().research_plan_max_events:
            raise ConflictError("计划审计预算已耗尽，需要人工封存", code="PLAN_BUDGET_EXCEEDED")
        row.events = [*row.events, {"kind": kind, "at": datetime.now(UTC).isoformat(), **facts}]

    async def resolved_arguments(
        self,
        owner: UUID,
        project: UUID,
        draft: ResearchPlanDraft,
        steps: builtins.list[StepView],
        step_id: str,
    ) -> dict[str, Any]:
        from cygnusx.application.schemas.agent_tools import CAPABILITY_MODELS
        from cygnusx.application.schemas.research_plan import StepKind

        definitions = {s.step_id: s for s in draft.steps}
        views = {s.step_id: s for s in steps}
        step = definitions[step_id]
        args = dict(step.arguments)
        for binding in step.bindings:
            parent = definitions[binding.from_step]
            observed = views[binding.from_step]
            if observed.status != StepStatus.COMPLETE:
                raise ConflictError("上游后置条件未满足")
            if binding.output == "dataset_version" and parent.kind == StepKind.DATASET_INSPECT:
                source = await self.resolved_arguments(owner, project, draft, steps, parent.step_id)
                args[binding.argument] = source[binding.argument]
            elif binding.output == "task_id" and observed.task_id is not None:
                args[binding.argument] = str(observed.task_id)
            else:
                raise ConflictError("上游缺少可核验资源引用，需要人工补全计划")
        capability = STEP_CONTRACTS[step.kind][0]
        normalized = CAPABILITY_MODELS[capability].model_validate(args).model_dump(mode="json")
        # Re-resolve dynamic IDs as well as literal references under the current principal.
        if "dataset_id" in normalized and "version_id" in normalized:
            await self.repo.version(
                owner, project, UUID(normalized["dataset_id"]), UUID(normalized["version_id"])
            )
        return normalized

    async def advance(
        self,
        owner: UUID,
        project: UUID,
        plan_id: UUID,
        session_id: str,
    ) -> ResearchPlanView:
        """At most one ready read/prepare step. No loop, no execute or publication."""
        from cygnusx.application.services.agent_tool_gateway import AgentToolGateway

        gateway = AgentToolGateway(self.db)
        context = await gateway.context(str(owner), session_id)
        if context.extra["project_id"] != str(project):
            raise AuthorizationError("会话项目不匹配")
        row = await self.owned(owner, project, plan_id, lock=True)
        if row.superseded_by or row.reviewed_at is None:
            raise ConflictError("需审阅当前计划版本")
        reviewed = (
            row.reviewed_at.replace(tzinfo=UTC)
            if row.reviewed_at.tzinfo is None
            else row.reviewed_at
        )
        if datetime.now(UTC) >= reviewed + timedelta(
            seconds=get_settings().research_plan_review_ttl_seconds
        ):
            raise ConflictError("计划审阅已过期，请创建新版本重新审阅", code="PLAN_REVIEW_EXPIRED")
        if row.status not in {PlanStatus.APPROVED, PlanStatus.RUNNING}:
            return await self.view(owner, project, plan_id)
        draft = ResearchPlanDraft.model_validate(row.draft)
        await self.validate_resources(owner, project, draft)
        steps = [StepView.model_validate(s) for s in row.steps]
        states = {s.step_id: s.status for s in steps}
        if any(s.status == StepStatus.SUBMITTING for s in steps):
            # One in-flight reservation per plan: concurrent requests cannot overwrite
            # independent step projections. Crash reconciliation is an explicit operation.
            return await self.view(owner, project, plan_id)
        ready = ready_steps(draft, states)
        if not ready:
            if any(s.status == StepStatus.SUBMITTING for s in steps):
                row.status = PlanStatus.RECONCILIATION_REQUIRED
                self.event(row, "RECONCILIATION_REQUIRED")
            await self.db.flush()
            return await self.view(owner, project, plan_id)
        index = next(i for i, s in enumerate(steps) if s.step_id == ready[0])
        step = steps[index]
        if step.effect in {Effect.MUTATING, Effect.REPORT_PUBLISH}:
            # Deliberately before any business confirmation consumption or dispatch.
            step.status = StepStatus.WAITING_APPROVAL
            row.steps = [s.model_dump(mode="json") for s in steps]
            await self.db.flush()
            return await self.view(owner, project, plan_id)
        arguments = await self.resolved_arguments(owner, project, draft, steps, step.step_id)
        calls = sum(e["kind"] == "STEP_RESERVED" for e in row.events)
        used_seconds = sum(float(e.get("elapsed_seconds", 0)) for e in row.events)
        if used_seconds >= draft.budget.max_elapsed_seconds:
            raise ConflictError("计划工具时间预算已耗尽")
        if calls >= draft.budget.max_tool_calls:
            raise ConflictError("计划工具预算已耗尽")
        context = context.model_copy(
            update={"request_id": str(uuid5(row.id, step.step_id + row.digest))}
        )
        step.status = StepStatus.SUBMITTING
        row.status = PlanStatus.RUNNING
        row.steps = [s.model_dump(mode="json") for s in steps]
        self.event(row, "STEP_RESERVED", step_id=step.step_id, request_id=context.request_id)
        await self.db.commit()  # crash recovery must not auto-replay uncertain prepare calls
        started = time.monotonic()
        try:
            timeout = min(
                draft.budget.max_elapsed_seconds - used_seconds,
                get_settings().research_plan_tool_timeout_seconds,
            )
            async with asyncio.timeout(timeout):
                result = await gateway.invoke(context, step.capability_id, arguments)
            invocation_id = UUID(result["invocation_id"])
            from cygnusx.application.schemas.agent_tools import CAPABILITY_MODELS
            from cygnusx.application.services.agent_tool_gateway import digest
            from cygnusx.infrastructure.database.models.agent_tool_invocation import (
                AgentToolInvocationModel,
            )

            observed = await self.db.get(AgentToolInvocationModel, invocation_id)
            expected = (
                CAPABILITY_MODELS[step.capability_id]
                .model_validate(arguments)
                .model_dump(mode="json")
            )
            if (
                observed is None
                or observed.owner_id != str(owner)
                or observed.project_id != str(project)
                or observed.capability_id != step.capability_id
                or observed.request_id != context.request_id
                or observed.parameters_hash != digest(expected)
            ):
                raise ConflictError("Tool invocation does not match the reserved step")
        except Exception:
            # Do not expose provider/filesystem messages or pretend dispatch did not happen.
            await self.db.rollback()
            row = await self.owned(owner, project, plan_id, lock=True)
            steps = [StepView.model_validate(s) for s in row.steps]
            steps[index].status = StepStatus.RECONCILIATION_REQUIRED
            steps[index].error_code = "TOOL_OUTCOME_UNCERTAIN"
            row.steps = [s.model_dump(mode="json") for s in steps]
            if row.status not in {PlanStatus.CANCELLED, PlanStatus.PAUSED, PlanStatus.FAILED}:
                row.status = PlanStatus.RECONCILIATION_REQUIRED
            self.event(row, "TOOL_OUTCOME_UNCERTAIN", step_id=step.step_id)
            await self.db.flush()
            return await self.view(owner, project, plan_id)
        row = await self.owned(owner, project, plan_id, lock=True)
        if row.superseded_by or row.status != PlanStatus.RUNNING:
            raise ConflictError("计划调度期间状态已变化，需人工对账")
        step.invocation_id = invocation_id
        payload = result.get("result", {})
        valid = not isinstance(payload, dict) or payload.get("valid") is not False
        if step.effect == Effect.PREPARE:
            valid = (
                valid
                and isinstance(payload, dict)
                and bool(payload.get("proposal_id") or payload.get("analysis_proposal_id"))
            )
        if step.kind.value == "DELIVERY_PREPARE":
            valid = (
                valid
                and isinstance(payload, dict)
                and payload.get("result_integrity") == "VERIFIED"
                and payload.get("delivery_state") == "READY"
            )
        step.status = StepStatus.COMPLETE if valid else StepStatus.PARTIAL
        if step.kind.value == "DELIVERY_PREPARE" and isinstance(payload, dict):
            if (
                payload.get("task_id") != arguments.get("task_id")
                or payload.get("project_id") != str(project)
                or payload.get("owner_id") != str(owner)
            ):
                raise ConflictError("Task provenance scope mismatch")
            self.observe_delivery(step, ResearchProvenance.model_validate(payload))
        if not valid and step.kind.value != "DELIVERY_PREPARE":
            step.error_code = "PREPARE_OR_QUERY_POSTCONDITION_NOT_MET"
        row.steps = [s.model_dump(mode="json") for s in steps]
        # Read/prepare completion never means a research computation has completed.
        row.status = (
            PlanStatus.READY_FOR_REVIEW
            if all(s.status == StepStatus.COMPLETE for s in steps)
            else PlanStatus.RUNNING
        )
        self.event(
            row,
            "TOOL_OBSERVED",
            step_id=step.step_id,
            invocation_id=str(invocation_id),
            elapsed_seconds=time.monotonic() - started,
        )
        await self.db.flush()
        return await self.view(owner, project, plan_id)

    async def control(
        self,
        owner: UUID,
        project: UUID,
        plan_id: UUID,
        action: str,
    ) -> ResearchPlanView:
        from cygnusx.domain.research.plan_state import transition

        row = await self.owned(owner, project, plan_id, lock=True)
        target = {
            "pause": PlanStatus.PAUSED,
            "resume": PlanStatus.RUNNING,
            "cancel": PlanStatus.CANCELLED,
        }.get(action)
        if target is None or row.superseded_by:
            raise ConflictError("不可用的计划控制操作")
        try:
            row.status = transition(PlanStatus(row.status), target)
        except ValueError as exc:
            raise ConflictError("当前状态不允许该操作") from exc
        self.event(row, "HUMAN_PLAN_CONTROL", action=action)
        await self.db.flush()
        # No Task cancel, file deletion or approval consumption.
        return await self.view(owner, project, plan_id)

    @staticmethod
    def observe_delivery(step: StepView, graph: ResearchProvenance) -> None:
        step.task_id = graph.task_id
        step.result_manifest_sha256 = graph.manifest_sha256
        step.reports = graph.reports[:20]
        step.error_code = None
        if graph.compute_state in {"pending", "queued"}:
            step.status = StepStatus.QUEUED
        elif graph.compute_state in {"running", "started"}:
            step.status = StepStatus.RUNNING
        elif graph.compute_state in {"failed", "failure", "cancelled", "canceled"}:
            step.status = StepStatus.PARTIAL if graph.artifacts else StepStatus.FAILED
            step.error_code = "COMPUTE_NOT_SUCCESSFUL"
        elif graph.compute_state not in {"success", "completed"}:
            step.status = StepStatus.RECONCILIATION_REQUIRED
            step.error_code = "COMPUTE_STATE_UNKNOWN"
        elif graph.result_integrity != "VERIFIED":
            step.status = StepStatus.PARTIAL
            step.error_code = "RESULT_MANIFEST_OR_ARTIFACT_NOT_VERIFIED"
        elif graph.delivery_state != "READY":
            step.status = StepStatus.PARTIAL
            step.error_code = "REPORT_DELIVERY_INCOMPLETE"
        else:
            step.status = StepStatus.COMPLETE

    async def reconcile(
        self,
        owner: UUID,
        project: UUID,
        plan_id: UUID,
    ) -> ResearchPlanView:
        """Inspect existing records only. Missing response evidence never becomes success."""
        from cygnusx.infrastructure.database.models.agent_tool_invocation import (
            AgentToolInvocationModel,
        )

        row = await self.owned(owner, project, plan_id, lock=True)
        steps = [StepView.model_validate(s) for s in row.steps]
        changed = False
        for step in steps:
            if step.task_id and step.kind.value == "DELIVERY_PREPARE":
                from cygnusx.application.services.research_provenance_service import (
                    ResearchProvenanceService,
                )

                graph = await ResearchProvenanceService(self.db).task(owner, step.task_id)
                if graph.project_id != project:
                    raise NotFoundError("Task 不属于当前项目")
                before = step.model_dump(mode="json")
                self.observe_delivery(step, graph)
                changed = changed or before != step.model_dump(mode="json")
                continue
            if step.status not in {StepStatus.SUBMITTING, StepStatus.RECONCILIATION_REQUIRED}:
                continue
            request_id = str(uuid5(row.id, step.step_id + row.digest))
            if step.status == StepStatus.SUBMITTING:
                reservation = next(
                    (
                        event
                        for event in reversed(row.events)
                        if event.get("kind") == "STEP_RESERVED"
                        and event.get("step_id") == step.step_id
                        and event.get("request_id") == request_id
                    ),
                    None,
                )
                if reservation is not None:
                    try:
                        reserved_at = datetime.fromisoformat(reservation["at"])
                        age = (datetime.now(UTC) - reserved_at).total_seconds()
                    except (KeyError, TypeError, ValueError):
                        age = float("inf")
                    if 0 <= age < get_settings().research_plan_tool_timeout_seconds:
                        # An explicit reconcile must not invalidate an active invocation.
                        # Expired or missing reservations remain uncertain, never replayed.
                        continue
            found = (
                (
                    await self.db.execute(
                        select(AgentToolInvocationModel)
                        .where(
                            AgentToolInvocationModel.owner_id == str(owner),
                            AgentToolInvocationModel.project_id == str(project),
                            AgentToolInvocationModel.capability_id == step.capability_id,
                            AgentToolInvocationModel.request_id == request_id,
                        )
                        .limit(2)
                    )
                )
                .scalars()
                .all()
            )
            if len(found) == 1:
                step.invocation_id = found[0].id
            step.status = StepStatus.RECONCILIATION_REQUIRED
            step.error_code = "TOOL_POSTCONDITION_REQUIRES_HUMAN_REVIEW"
            changed = True
        if changed:
            row.steps = [s.model_dump(mode="json") for s in steps]
            row.status = (
                row.status
                if row.status in {PlanStatus.CANCELLED, PlanStatus.PAUSED, PlanStatus.FAILED}
                else PlanStatus.RECONCILIATION_REQUIRED
                if any(s.status == StepStatus.RECONCILIATION_REQUIRED for s in steps)
                else PlanStatus.READY_FOR_REVIEW
                if all(s.status == StepStatus.COMPLETE for s in steps)
                else PlanStatus.PARTIAL
            )
            # Deduplicate repeated reconcile observations; do not create an unbounded journal.
            if not row.events or row.events[-1]["kind"] != "PLAN_RECONCILED_WITH_GAPS":
                self.event(row, "PLAN_RECONCILED_WITH_GAPS")
            await self.db.flush()
        return await self.view(owner, project, plan_id)
