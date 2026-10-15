import pytest
from scripts.evaluate_model_routing_ab import evaluate


def _row(group: str, quality: float, cost: float, latency: float) -> dict:
    return {
        "group": group,
        "quality": quality,
        "input_tokens": 0,
        "output_tokens": 1_000_000,
        "input_price": 0,
        "output_price": cost,
        "latency_ms": latency,
        "success": True,
        "decision_logged": group == "B",
    }


def test_evaluation_reports_all_gates() -> None:
    report = evaluate([_row("A", 100, 10, 1000), _row("B", 99, 7, 900)])
    assert report["passed"] is True
    assert report["gates"]["cost"] is True
    assert report["comparison"]["cost_reduction"] == pytest.approx(0.3)


def test_evaluation_requires_both_groups() -> None:
    with pytest.raises(ValueError, match="both A and B"):
        evaluate([_row("A", 100, 10, 1000)])
