from datetime import UTC, datetime
from types import SimpleNamespace

from cygnusx.application.services.model_health_monitor import (
    HealthEventKind,
    ModelHealthMonitor,
)
from cygnusx.application.services.model_selector import ModelSelector, SelectionInput
from cygnusx.application.services.unified_intent_router import normalize_decision


def _provider(
    name: str,
    tier: str,
    out: float,
    weight: int = 100,
    is_default: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        tier=tier,
        cost_per_1m_in=out / 2,
        cost_per_1m_out=out,
        weight=weight,
        is_default=is_default,
        is_active=True,
    )


def test_health_monitor_opens_after_three_failures() -> None:
    monitor = ModelHealthMonitor()
    for _ in range(3):
        monitor.record("p", HealthEventKind.TIMEOUT)
    snapshot = monitor.snapshot("p")
    assert snapshot is not None
    assert snapshot.consecutive_failures == 3
    assert snapshot.healthy is False


def test_unknown_provider_is_admitted() -> None:
    assert ModelHealthMonitor().is_healthy("new") is True


def test_health_snapshot_keeps_event_time() -> None:
    monitor = ModelHealthMonitor()
    monitor.record("p", HealthEventKind.TIMEOUT)
    snapshot = monitor.snapshot("p")
    assert snapshot is not None
    assert snapshot.last_event_at is not None
    assert snapshot.last_event_at <= datetime.now(UTC)


def test_active_probe_timestamp_survives_passive_event() -> None:
    monitor = ModelHealthMonitor()
    monitor.record_probe("p", HealthEventKind.SUCCESS, 10)
    active = monitor.snapshot("p")
    assert active is not None and active.last_probe_at is not None
    monitor.record("p", HealthEventKind.SUCCESS, 12)
    passive = monitor.snapshot("p")
    assert passive is not None
    assert passive.last_probe_at == active.last_probe_at


def test_probe_backoff_after_three_all_failed_rounds() -> None:
    import asyncio
    from types import SimpleNamespace

    monitor = ModelHealthMonitor()
    provider = SimpleNamespace(name="p")

    async def fail(_: object) -> float:
        raise RuntimeError("offline")

    async def run() -> None:
        for _ in range(3):
            await monitor.probe_once([provider], fail)

    asyncio.run(run())
    assert monitor.providers_due_for_probe(["p"]) == []
    assert monitor.probe_failure_rounds == 3
    assert monitor.probe_backoff_active is True


def test_complexity_normalization_defaults_to_medium() -> None:
    for payload in ({}, {"complexity": "extreme"}, {"complexity": None}):
        decision = normalize_decision(
            payload,
            fallback_agent_id="agent-general",
            valid_agent_ids={"agent-general"},
        )
        assert decision.complexity == "medium"


def test_complexity_normalization_accepts_valid_levels() -> None:
    decision = normalize_decision(
        {"complexity": "HIGH"},
        fallback_agent_id="agent-general",
        valid_agent_ids={"agent-general"},
    )
    assert decision.complexity == "high"


def test_selector_uses_complexity_and_cost() -> None:
    selector = ModelSelector([_provider("light-a", "light", 2), _provider("light-b", "light", 1), _provider("heavy", "heavy", 10)])
    decision = selector.select(SelectionInput("r", 0, "agent", complexity="low", model_tier="auto"))
    assert decision.primary == "light-b"
    assert decision.cascade == ["light-a"]


def test_selector_explicit_choice_wins() -> None:
    selector = ModelSelector([_provider("light", "light", 1), _provider("heavy", "heavy", 10)])
    decision = selector.select(SelectionInput("r", 0, "agent", explicit_model_id="heavy"))
    assert decision.primary == "heavy"
    assert decision.decision_reason == "explicit_choice"


def test_selector_returns_each_cascade_candidate_once() -> None:
    selector = ModelSelector(
        [_provider("a", "light", 1), _provider("b", "light", 2), _provider("c", "light", 3)]
    )
    decision = selector.select(SelectionInput("r", 1, "agent", model_tier="light"))
    assert decision.primary == "a"
    assert selector.on_step_result("r", 1, failed=True, reason="timeout") == "b"
    assert selector.on_step_result("r", 1, failed=True, reason="timeout") == "c"
    assert selector.on_step_result("r", 1, failed=True, reason="timeout") is None
    assert selector.on_step_result("r", 1, failed=False) is None


def test_selector_upgrades_truncated_medium_step_once() -> None:
    selector = ModelSelector(
        [_provider("light", "light", 1), _provider("heavy-a", "heavy", 8), _provider("heavy-b", "heavy", 9)],
        max_cascades=0,
        max_upgrades=1,
    )
    selector.select(SelectionInput("r", 2, "agent", complexity="medium", model_tier="light"))
    assert selector.on_step_result("r", 2, failed=True, finish_reason="length", provider="light") == "heavy-a"
    assert selector.on_step_result("r", 2, failed=True, finish_reason="length", provider="heavy-a") is None


def test_selector_can_degrade_heavy_timeout() -> None:
    selector = ModelSelector(
        [_provider("light", "light", 1), _provider("heavy", "heavy", 8)],
        max_cascades=0,
    )
    selector.select(SelectionInput("r", 3, "agent", complexity="heavy", model_tier="heavy"))
    assert selector.on_step_result("r", 3, failed=True, reason="timeout", provider="heavy") == "light"


def test_selector_falls_back_to_default_when_all_candidates_unhealthy() -> None:
    providers = [
        _provider("light", "light", 1),
        _provider("default", "light", 3, is_default=True),
    ]
    monitor = ModelHealthMonitor()
    for _ in range(3):
        monitor.record("light", HealthEventKind.TIMEOUT)
        monitor.record("default", HealthEventKind.TIMEOUT)
    decision = ModelSelector(providers, health=monitor).select(
        SelectionInput("r", 4, "agent", model_tier="light")
    )
    assert decision.primary == "default"
    assert decision.decision_reason == "no_healthy_candidate"
    assert decision.candidates_considered[0].cost_est is not None
