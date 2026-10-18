"""Research intent is untrusted input; identity and execution facts are server-owned."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepKind(StrEnum):
    DISCOVERY = "DISCOVERY"
    DATASET_INSPECT = "DATASET_INSPECT"
    WORKFLOW_MATCH = "WORKFLOW_MATCH"
    ANALYSIS_PREPARE = "ANALYSIS_PREPARE"
    DATASET_IMPORT_PREPARE = "DATASET_IMPORT_PREPARE"
    DATASET_IMPORT = "DATASET_IMPORT"
    ANALYSIS_EXECUTE = "ANALYSIS_EXECUTE"
    DELIVERY_PREPARE = "DELIVERY_PREPARE"
    REPORT_PUBLISH = "REPORT_PUBLISH"


class Effect(StrEnum):
    READ_ONLY = "READ_ONLY"
    PREPARE = "PREPARE"
    MUTATING = "MUTATING"
    REPORT_PUBLISH = "REPORT_PUBLISH"


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class StepStatus(StrEnum):
    WAITING_INPUT = "WAITING_INPUT"
    READY = "READY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUBMITTING = "SUBMITTING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


# StepKind -> exact existing capability, effect, output port type.
# Publishing has no Agent capability: explicitly blocked, never mapped to a write tool.
STEP_CONTRACTS: dict[StepKind, tuple[str, Effect, str]] = {
    StepKind.DISCOVERY: ("dataset.discover", Effect.READ_ONLY, "discovery_proposal"),
    StepKind.DATASET_INSPECT: ("dataset.inspect", Effect.READ_ONLY, "dataset_version"),
    StepKind.WORKFLOW_MATCH: (
        "analysis.list_compatible_workflows",
        Effect.READ_ONLY,
        "workflow_candidates",
    ),
    StepKind.ANALYSIS_PREPARE: (
        "analysis.prepare_from_dataset",
        Effect.PREPARE,
        "analysis_proposal",
    ),
    StepKind.DATASET_IMPORT_PREPARE: ("dataset.prepare_import", Effect.PREPARE, "import_proposal"),
    StepKind.DATASET_IMPORT: ("dataset.execute_import", Effect.MUTATING, "dataset_version"),
    StepKind.ANALYSIS_EXECUTE: ("analysis.submit", Effect.MUTATING, "task_id"),
    StepKind.DELIVERY_PREPARE: ("research.task_provenance", Effect.READ_ONLY, "delivery_proposal"),
    StepKind.REPORT_PUBLISH: ("", Effect.REPORT_PUBLISH, "published_report"),
}

StepId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")]


class InputBinding(PlanInput):
    """Bind an exact upstream output to a declared downstream argument."""

    argument: Literal["proposal_id", "task_id"]
    from_step: StepId
    output: Literal["analysis_proposal", "import_proposal", "task_id"]


class PlanBudget(PlanInput):
    max_tool_calls: int = Field(default=20, ge=1, le=100)
    max_elapsed_seconds: int = Field(default=300, ge=1, le=600)
    max_model_tokens: int = Field(default=10000, ge=1, le=100000)
    max_retries: Literal[0] = 0
    estimated_compute_seconds: int | None = Field(default=None, ge=0)
    estimated_storage_bytes: int | None = Field(default=None, ge=0)


class ResearchStepDraft(PlanInput):
    step_id: StepId
    kind: StepKind
    goal: str = Field(min_length=1, max_length=1000)
    depends_on: list[StepId] = Field(default_factory=list, max_length=20)
    arguments: dict[str, Any] = Field(default_factory=dict)
    bindings: list[InputBinding] = Field(default_factory=list, max_length=2)
    failure_policy: Literal["STOP_AND_RECONCILE"] = "STOP_AND_RECONCILE"

    @model_validator(mode="after")
    def validate_arguments(self) -> Self:
        from cygnusx.application.schemas.agent_tools import CAPABILITY_MODELS

        def check_public(value: Any, depth: int = 0) -> None:
            if depth > 8:
                raise ValueError("arguments exceed nesting limit")
            if isinstance(value, dict):
                if len(value) > 100:
                    raise ValueError("too many argument fields")
                forbidden = {
                    "owner_id",
                    "user_id",
                    "project_id",
                    "token",
                    "api_key",
                    "authorization",
                    "_confirmed",
                    "confirmed",
                    "user_confirmed",
                    "status",
                    "shell",
                    "command",
                    "raw_data_path",
                    "data_deliver",
                    "storage_path",
                    "workflow",
                }
                if any(str(key).lower() in forbidden for key in value):
                    raise ValueError(
                        "trusted identity, credentials or execution fields are forbidden"
                    )
                for child in value.values():
                    check_public(child, depth + 1)
            elif isinstance(value, list):
                if len(value) > 100:
                    raise ValueError("argument list exceeds limit")
                for child in value:
                    check_public(child, depth + 1)
            elif isinstance(value, str) and (
                value.startswith(("/", "~/", "\\")) or "://" in value or "../" in value
            ):
                raise ValueError("server paths and arbitrary URLs are forbidden")

        check_public(self.arguments)
        if len(json.dumps(self.arguments, allow_nan=False).encode()) > 16384:
            raise ValueError("argument payload exceeds contract limit")
        capability, _, _ = STEP_CONTRACTS[self.kind]
        if self.kind == StepKind.REPORT_PUBLISH:
            if self.arguments or self.bindings:
                raise ValueError("REPORT_PUBLISH is unavailable; no publication arguments allowed")
            return self
        bound = {b.argument for b in self.bindings}
        if len(bound) != len(self.bindings) or bound & self.arguments.keys():
            raise ValueError("duplicate or shadowed binding")
        # Validate names/types of literal arguments without inventing an actual resource.
        validation_args = dict(self.arguments)
        placeholder = "00000000-0000-0000-0000-000000000000"
        validation_args.update({name: placeholder for name in bound})
        CAPABILITY_MODELS[capability].model_validate(validation_args)
        expected_binding = {
            StepKind.ANALYSIS_EXECUTE: ("proposal_id", "analysis_proposal"),
            StepKind.DATASET_IMPORT: ("proposal_id", "import_proposal"),
        }.get(self.kind)
        if expected_binding and (
            len(self.bindings) != 1
            or (self.bindings[0].argument, self.bindings[0].output) != expected_binding
        ):
            raise ValueError("mutating step must use a proposal from its prepare dependency")
        if self.kind == StepKind.DELIVERY_PREPARE and any(
            b.argument != "task_id" or b.output != "task_id" for b in self.bindings
        ):
            raise ValueError("delivery binding must reference an actual upstream task")
        return self


class ResearchPlanDraft(PlanInput):
    schema_version: Literal["cygnusx.research_plan.v1"] = "cygnusx.research_plan.v1"
    research_question: str = Field(min_length=1, max_length=4000)
    assumptions: list[Annotated[str, Field(max_length=1000)]] = Field(
        default_factory=list, max_length=20
    )
    steps: list[ResearchStepDraft] = Field(min_length=1, max_length=20)
    budget: PlanBudget = Field(default_factory=PlanBudget)

    @model_validator(mode="after")
    def validate_dag(self) -> Self:
        nodes = {s.step_id: s for s in self.steps}
        if len(nodes) != len(self.steps):
            raise ValueError("duplicate step_id")
        complete: set[str] = set()
        visiting: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("cyclic dependency")
            if step_id in complete:
                return
            visiting.add(step_id)
            step = nodes[step_id]
            if len(set(step.depends_on)) != len(step.depends_on):
                raise ValueError("duplicate dependency")
            for dep in step.depends_on:
                if dep not in nodes:
                    raise ValueError("dangling dependency")
                visit(dep)
            for binding in step.bindings:
                if binding.from_step not in step.depends_on:
                    raise ValueError("binding must reference a direct dependency")
                if STEP_CONTRACTS[nodes[binding.from_step].kind][2] != binding.output:
                    raise ValueError("incompatible output port")
            visiting.remove(step_id)
            complete.add(step_id)

        for key in nodes:
            visit(key)
        if len(self.steps) > self.budget.max_tool_calls:
            raise ValueError("step count exceeds tool-call budget")
        return self


class PlanPrepare(PlanInput):
    request_key: UUID
    draft: ResearchPlanDraft


class PlanRevision(PlanPrepare):
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class StepView(PlanInput):
    step_id: str
    kind: StepKind
    capability_id: str
    effect: Effect
    approval_required: bool
    expected_output: str
    status: StepStatus
    invocation_id: UUID | None = None
    task_id: UUID | None = None
    error_code: str | None = None


class ResearchPlanView(PlanInput):
    schema_version: Literal["cygnusx.research_plan.v1"] = "cygnusx.research_plan.v1"
    plan_id: UUID
    version: int
    project_id: UUID
    digest: str
    status: PlanStatus
    mode: Literal["PLAN_ONLY"] = "PLAN_ONLY"
    draft: ResearchPlanDraft
    steps: list[StepView]
    gaps: list[str]
    created_at: datetime
    reviewed_at: datetime | None = None
    superseded_by: UUID | None = None
