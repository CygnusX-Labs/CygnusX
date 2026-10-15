"""Provider 动态选型与级联状态机。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cygnusx.application.services.model_health_monitor import ModelHealthMonitor


@dataclass(frozen=True)
class SelectionInput:
    request_id: str
    step_index: int
    agent_id: str
    complexity: str = "medium"
    model_tier: str = "auto"
    explicit_model_id: str | None = None
    estimated_output_tokens: int = 1024


@dataclass(frozen=True)
class CandidateEval:
    provider: str
    healthy: bool
    cost_est: float | None
    rank_score: float


@dataclass(frozen=True)
class SelectionDecision:
    primary: str
    cascade: list[str] = field(default_factory=list)
    decision_reason: str = "tier_match"
    candidates_considered: list[CandidateEval] = field(default_factory=list)
    degraded: bool = False
    degrade_reason: str | None = None


@dataclass(frozen=True)
class StepResult:
    failed: bool = False
    reason: str = ""
    finish_reason: str | None = None
    provider: str | None = None


def rank_candidates(candidates: list[Any], estimated_output_tokens: int) -> list[Any]:
    def key(item: Any) -> tuple[float, int, str]:
        in_cost = getattr(item, "cost_per_1m_in", None)
        out_cost = getattr(item, "cost_per_1m_out", None)
        # Input length is not available at this boundary. Keep the known output
        # estimate in per-million-token units and use input price as a stable
        # tie-breaker when output prices are absent.
        cost = (
            float(out_cost) * estimated_output_tokens / 1_000_000
            if out_cost is not None
            else (float(in_cost) if in_cost is not None else float("inf"))
        )
        return cost, -int(getattr(item, "weight", 100) or 100), str(getattr(item, "name", ""))
    return sorted(candidates, key=key)


def _cost_estimate(provider: Any, estimated_output_tokens: int) -> float | None:
    out_cost = getattr(provider, "cost_per_1m_out", None)
    in_cost = getattr(provider, "cost_per_1m_in", None)
    if out_cost is not None:
        return float(out_cost) * estimated_output_tokens / 1_000_000
    if in_cost is not None:
        return float(in_cost)
    return None


class ModelSelector:
    def __init__(
        self,
        providers: list[Any],
        health: ModelHealthMonitor | None = None,
        *,
        max_cascades: int = 2,
        max_upgrades: int = 1,
        quality_degrade_enabled: bool = True,
    ) -> None:
        self.providers = providers
        self.health = health or ModelHealthMonitor()
        self._cascade_counts: dict[tuple[str, int], int] = {}
        self._decisions: dict[tuple[str, int], SelectionDecision] = {}
        self._inputs: dict[tuple[str, int], SelectionInput] = {}
        self._upgrade_counts: dict[str, int] = {}
        self.max_cascades = max(0, max_cascades)
        self.max_upgrades = max(0, max_upgrades)
        self.quality_degrade_enabled = quality_degrade_enabled

    def select(self, inp: SelectionInput) -> SelectionDecision:
        active = [p for p in self.providers if getattr(p, "is_active", True)]
        by_name = {str(getattr(p, "name", "")): p for p in active}
        if inp.explicit_model_id and inp.explicit_model_id in by_name:
            chosen = by_name[inp.explicit_model_id]
            if self.health.is_healthy(chosen.name):
                alternatives = [
                    p for p in active
                    if p.name != chosen.name
                    and getattr(p, "tier", "light") == getattr(chosen, "tier", "light")
                    and self.health.is_healthy(p.name)
                ]
                ranked = rank_candidates(alternatives, inp.estimated_output_tokens)
                decision = SelectionDecision(
                    chosen.name,
                    [p.name for p in ranked[:2]],
                    "explicit_choice",
                    [
                        CandidateEval(
                            p.name,
                            True,
                            _cost_estimate(p, inp.estimated_output_tokens),
                            float(i),
                        )
                        for i, p in enumerate([chosen, *ranked])
                    ],
                )
                self._decisions[(inp.request_id, inp.step_index)] = decision
                self._inputs[(inp.request_id, inp.step_index)] = inp
                return decision
        tier = inp.model_tier
        if tier == "auto":
            tier = "heavy" if inp.complexity in {"high", "heavy"} else "light"
        pool = [p for p in active if getattr(p, "tier", "light") == tier and self.health.is_healthy(p.name)]
        reason = "tier_match"
        if not pool:
            pool = [p for p in active if self.health.is_healthy(p.name)]
            reason = "no_healthy_candidate"
        if not pool:
            default = next((p for p in active if getattr(p, "is_default", False)), None)
            pool = [default] if default is not None else active
            reason = "no_healthy_candidate"
        ranked = rank_candidates(pool, inp.estimated_output_tokens)
        if not ranked:
            raise ValueError("没有可用 AI Provider")
        decision = SelectionDecision(
            ranked[0].name,
            [p.name for p in ranked[1:3]],
            reason,
            [
                CandidateEval(
                    p.name,
                    self.health.is_healthy(p.name),
                    _cost_estimate(p, inp.estimated_output_tokens),
                    float(i),
                )
                for i, p in enumerate(ranked)
            ],
            degraded=reason != "tier_match",
            degrade_reason=reason if reason != "tier_match" else None,
        )
        self._decisions[(inp.request_id, inp.step_index)] = decision
        self._inputs[(inp.request_id, inp.step_index)] = inp
        return decision

    def on_step_result(
        self,
        request_id: str,
        step_index: int,
        *,
        failed: bool,
        reason: str = "",
        finish_reason: str | None = None,
        provider: str | None = None,
    ) -> str | None:
        """Return the next provider for a retry, respecting cascade and upgrade limits."""
        key = (request_id, step_index)
        if not failed:
            self._cascade_counts.pop(key, None)
            self._decisions.pop(key, None)
            self._inputs.pop(key, None)
            return None
        count = self._cascade_counts.get(key, 0)
        decision = self._decisions.get(key)
        inp = self._inputs.get(key)
        if decision is None or inp is None:
            return None
        if count < self.max_cascades and count < len(decision.cascade):
            self._cascade_counts[key] = count + 1
            return decision.cascade[count]

        # A length finish indicates an undersized model response. Upgrade once
        # to the cheapest healthy heavy provider for medium/high complexity.
        if (
            finish_reason in {"length", "max_tokens"}
            and inp.complexity in {"medium", "heavy"}
            and self._upgrade_counts.get(request_id, 0) < self.max_upgrades
        ):
            heavy = [
                item
                for item in self.providers
                if getattr(item, "is_active", True)
                and getattr(item, "tier", "light") == "heavy"
                and item.name != provider
                and self.health.is_healthy(item.name)
            ]
            if heavy:
                self._upgrade_counts[request_id] = self._upgrade_counts.get(request_id, 0) + 1
                return rank_candidates(heavy, inp.estimated_output_tokens)[0].name

        # A heavy timeout can be recovered by a light provider when enabled;
        # callers surface the quality degradation through the decision metadata.
        if (
            self.quality_degrade_enabled
            and (
                inp.model_tier == "heavy"
                or (inp.model_tier == "auto" and inp.complexity in {"high", "heavy"})
            )
            and "timeout" in reason.lower()
        ):
            light = [
                item
                for item in self.providers
                if getattr(item, "is_active", True)
                and getattr(item, "tier", "light") == "light"
                and self.health.is_healthy(item.name)
            ]
            if light:
                return rank_candidates(light, inp.estimated_output_tokens)[0].name
        return None
