"""Deterministic transitions shared by storage, coordinator and isolated benchmarks."""

from __future__ import annotations

import hashlib
import json

from cygnusx.application.schemas.research_plan import (
    PlanStatus,
    ResearchPlanDraft,
    StepStatus,
)


class InvalidTransitionError(ValueError):
    pass


TRANSITIONS: dict[PlanStatus, frozenset[PlanStatus]] = {
    PlanStatus.DRAFT: frozenset({PlanStatus.VALIDATED, PlanStatus.REVIEW_REQUIRED}),
    PlanStatus.VALIDATED: frozenset({PlanStatus.READY_FOR_REVIEW, PlanStatus.REVIEW_REQUIRED}),
    PlanStatus.READY_FOR_REVIEW: frozenset({PlanStatus.APPROVED, PlanStatus.CANCELLED}),
    PlanStatus.REVIEW_REQUIRED: frozenset({PlanStatus.CANCELLED}),
    PlanStatus.APPROVED: frozenset({PlanStatus.RUNNING, PlanStatus.PAUSED, PlanStatus.CANCELLED}),
    PlanStatus.RUNNING: frozenset(
        {
            PlanStatus.COMPLETED,
            PlanStatus.PARTIAL,
            PlanStatus.FAILED,
            PlanStatus.PAUSED,
            PlanStatus.CANCELLED,
            PlanStatus.RECONCILIATION_REQUIRED,
        }
    ),
    PlanStatus.PAUSED: frozenset({PlanStatus.RUNNING, PlanStatus.CANCELLED}),
    PlanStatus.RECONCILIATION_REQUIRED: frozenset(
        {
            PlanStatus.PARTIAL,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
        }
    ),
    PlanStatus.PARTIAL: frozenset({PlanStatus.CANCELLED}),
    PlanStatus.COMPLETED: frozenset(),
    PlanStatus.FAILED: frozenset(),
    PlanStatus.CANCELLED: frozenset(),
}


def transition(current: PlanStatus, target: PlanStatus) -> PlanStatus:
    if current == target:
        return current
    if target not in TRANSITIONS[current]:
        raise InvalidTransitionError(f"{current} -> {target} is not allowed")
    return target


def plan_digest(plan: ResearchPlanDraft) -> str:
    return hashlib.sha256(
        json.dumps(
            plan.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def ready_steps(plan: ResearchPlanDraft, states: dict[str, StepStatus]) -> list[str]:
    """Unknown/submitting/partial upstream states never release downstream work."""
    return [
        step.step_id
        for step in plan.steps
        if states.get(step.step_id, StepStatus.WAITING_INPUT)
        in {StepStatus.WAITING_INPUT, StepStatus.READY, StepStatus.WAITING_APPROVAL}
        and all(states.get(dep) == StepStatus.COMPLETE for dep in step.depends_on)
    ]
