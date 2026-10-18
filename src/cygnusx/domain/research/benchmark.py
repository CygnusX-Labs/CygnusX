"""Versioned offline benchmark records and explicit-denominator metrics.

An evaluation record cannot grant platform permissions or certify its own evidence.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Literal

from pydantic import Field, model_validator

from cygnusx.application.schemas.research_plan import PlanInput


class BenchmarkRecord(PlanInput):
    @model_validator(mode="before")
    @classmethod
    def reject_credentials(cls, value: Any) -> Any:
        def inspect(node: Any, depth: int = 0) -> None:
            if depth > 20:
                raise ValueError("benchmark record nesting exceeds limit")
            if isinstance(node, dict):
                if any(
                    str(key).lower()
                    in {"token", "jwt", "authorization", "api_key", "password", "secret"}
                    for key in node
                ):
                    raise ValueError("benchmark records must not contain credentials")
                for child in node.values():
                    inspect(child, depth + 1)
            elif isinstance(node, list):
                for child in node:
                    inspect(child, depth + 1)
            elif isinstance(node, str) and (
                node.lower().startswith("bearer ") or node.startswith("sk-")
            ):
                raise ValueError("benchmark records must not contain credentials")

        inspect(value)
        return value


class BenchmarkCase(BenchmarkRecord):
    benchmark_version: Literal["research-agent-v1"] = "research-agent-v1"
    case_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    case_version: Literal["1.0"] = "1.0"
    category: Literal["discovery", "planning", "safety_recovery"]
    difficulty: Literal["small_synthetic", "controlled_live"]
    question: str = Field(min_length=1, max_length=4000)
    public_input: dict[str, Any]
    gold: dict[str, Any] = Field(min_length=1, max_length=100)
    source: str
    access: Literal["SYNTHETIC_NO_NETWORK", "PUBLIC_REQUIRES_VERIFICATION"]
    license: str
    review_status: Literal["PENDING_HUMAN_REVIEW", "HUMAN_REVIEWED"]
    reviewer: str | None = None
    review_record: str | None = None
    network_allowed: Literal[False] = False
    live_execution_allowed: Literal[False] = False
    max_seconds: int = Field(default=30, ge=1, le=600)
    arbitration: str = "Unresolved disagreement excludes ground-truth accuracy reporting"

    @model_validator(mode="after")
    def reviewed_requires_record(self) -> BenchmarkCase:
        if self.review_status == "HUMAN_REVIEWED" and not (self.reviewer and self.review_record):
            raise ValueError("human review requires a real reviewer and review record")
        return self


class BenchmarkRun(BenchmarkRecord):
    run_id: str
    case_id: str
    case_version: str
    benchmark_version: Literal["research-agent-v1"] = "research-agent-v1"
    system: Literal["manual", "existing_assistant", "contract_candidate"]
    layer: Literal["SYNTHETIC_CONTRACT", "CONTROLLED_LIVE"]
    repetition: int = Field(ge=1)
    goal_kind: Literal["CONTRACT_VALIDATION", "RESEARCH_DELIVERY"]
    task_success: bool | None = None
    valid_plan: bool | None = None
    discovery_correct: bool | None = None
    workflow_correct: bool | None = None
    recovery_safe: bool | None = None
    safety_violation: bool | None = None
    evidence_valid: int = Field(default=0, ge=0)
    evidence_required: int = Field(default=0, ge=0)
    unsupported_claims: int = Field(default=0, ge=0)
    factual_claims_evaluated: int = Field(default=0, ge=0)
    provenance_verified: int = Field(default=0, ge=0)
    provenance_required: int = Field(default=0, ge=0)
    reproduction_attempted: bool = False
    reproduction_matched: bool = False
    reproduction_rule: str | None = None
    human_interventions: int | None = Field(default=None, ge=0)
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    cost_amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = None
    cost_evidence: str | None = Field(default=None, min_length=1, max_length=2000)
    environment: dict[str, Any] = Field(default_factory=dict)
    model_id: str | None = None
    model_tokens: int | None = Field(default=None, ge=0)
    trace: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    failure_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_denominators(self) -> BenchmarkRun:
        for numerator, denominator in [
            (self.evidence_valid, self.evidence_required),
            (self.unsupported_claims, self.factual_claims_evaluated),
            (self.provenance_verified, self.provenance_required),
        ]:
            if numerator > denominator:
                raise ValueError("numerator exceeds denominator")
        if self.reproduction_matched and not self.reproduction_attempted:
            raise ValueError("reproduction match requires actual attempt")
        if self.reproduction_attempted and not self.reproduction_rule:
            raise ValueError("reproduction requires a predefined comparison rule")
        if self.cost_amount is not None and not (self.currency and self.cost_evidence):
            raise ValueError("cost requires currency and an actual billing or price record")
        if self.layer == "SYNTHETIC_CONTRACT" and self.goal_kind == "RESEARCH_DELIVERY":
            raise ValueError("synthetic validation cannot claim actual research delivery")
        return self


def proportion(numerator: int, denominator: int) -> dict[str, Any]:
    """Wilson 95% interval. Null when no observations, never synthetic 100%."""
    if not denominator:
        return {"numerator": numerator, "denominator": denominator, "rate": None, "ci95": None}
    rate = numerator / denominator
    z = 1.959963984540054
    scale = 1 + z * z / denominator
    centre = (rate + z * z / (2 * denominator)) / scale
    radius = z * math.sqrt(rate * (1 - rate) / denominator + z * z / (4 * denominator**2)) / scale
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": rate,
        "ci95": [max(0, centre - radius), min(1, centre + radius)],
    }


def summarize(runs: list[BenchmarkRun]) -> dict[str, Any]:
    if len({(r.run_id, r.case_id, r.repetition, r.system) for r in runs}) != len(runs):
        raise ValueError("duplicate measurement would overweight results")
    groups: dict[str, list[BenchmarkRun]] = {}
    for row in runs:
        groups.setdefault(f"{row.layer}:{row.goal_kind}:{row.system}", []).append(row)
    output: dict[str, Any] = {}
    for name, rows in groups.items():
        metrics: dict[str, Any] = {}
        for metric, field in {
            "task_success_rate": "task_success",
            "valid_plan_rate": "valid_plan",
            "discovery_accuracy": "discovery_correct",
            "workflow_accuracy": "workflow_correct",
            "recovery_success_rate": "recovery_safe",
            "safety_violation_rate": "safety_violation",
        }.items():
            observed = [getattr(r, field) for r in rows if getattr(r, field) is not None]
            metrics[metric] = proportion(sum(v is True for v in observed), len(observed))
            metrics[metric]["not_evaluated"] = len(rows) - len(observed)
        for metric, num, den in [
            ("evidence_coverage", "evidence_valid", "evidence_required"),
            ("unsupported_claim_rate", "unsupported_claims", "factual_claims_evaluated"),
            ("provenance_completeness", "provenance_verified", "provenance_required"),
        ]:
            metrics[metric] = proportion(
                sum(getattr(r, num) for r in rows), sum(getattr(r, den) for r in rows)
            )
        attempted = [r for r in rows if r.reproduction_attempted]
        metrics["reproduction_success"] = proportion(
            sum(r.reproduction_matched for r in attempted), len(attempted)
        )
        times = sorted(r.elapsed_seconds for r in rows)
        metrics["end_to_end_seconds"] = {
            "median": median(times),
            "values": times,
            "scope": "contract validation only"
            if rows[0].layer == "SYNTHETIC_CONTRACT"
            else "research delivery",
        }
        humans = [r.human_interventions for r in rows if r.human_interventions is not None]
        metrics["human_interventions"] = {
            "values": humans,
            "median": median(humans) if humans else None,
            "missing": len(rows) - len(humans),
        }
        costs: dict[str, list[float]] = {}
        for row in rows:
            if row.cost_amount is not None:
                costs.setdefault(str(row.currency), []).append(row.cost_amount)
        metrics["cost"] = {
            currency: {"values": values, "median": median(values)}
            for currency, values in costs.items()
        }
        metrics["cost_missing"] = sum(r.cost_amount is None for r in rows)
        metrics["failures"] = [
            {"case_id": r.case_id, "run_id": r.run_id, "codes": r.failure_codes}
            for r in rows
            if r.failure_codes or r.task_success is False
        ]
        metrics["measurement_count"] = len(rows)
        output[name] = metrics
    return {
        "benchmark_version": "research-agent-v1",
        "groups": output,
        "comparison": "NO_FAIR_BASELINE_MEASUREMENTS_NO_SUPERIORITY_CLAIM",
        "ci_note": "Wilson intervals describe observations; repeated cases are not independent samples",
    }


class ReproductionRule(PlanInput):
    kind: Literal["sha256", "numeric"]
    rtol: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    atol: float = Field(default=0, ge=0, allow_inf_nan=False)


def compare_reproduction(
    reference: list[float] | str,
    observed: list[float] | str,
    rule: ReproductionRule,
) -> bool:
    """Caller loads a predeclared rule; never adapt tolerances to observed output."""
    if rule.kind == "sha256":
        import re

        return (
            isinstance(reference, str)
            and isinstance(observed, str)
            and re.fullmatch(r"[0-9a-f]{64}", reference) is not None
            and reference == observed
        )
    if not isinstance(reference, list) or not isinstance(observed, list):
        return False
    if not reference or len(reference) != len(observed):
        return False
    return all(
        math.isfinite(a) and math.isfinite(b) and abs(a - b) <= rule.atol + rule.rtol * abs(a)
        for a, b in zip(reference, observed, strict=True)
    )
