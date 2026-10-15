"""Evaluate a static-vs-dynamic model-routing experiment from JSONL evidence.

Each input row must contain ``group`` (``A`` or ``B``), ``request_id``,
``quality``, ``input_tokens``, ``output_tokens``, ``input_price``,
``output_price``, ``latency_ms``, ``success`` and optional routing counters:
``cascade_count``, ``upgrade_count``, ``degrade_count``, ``classifier_cost``
and ``decision_logged``.  The script only aggregates supplied evidence; it
never invents provider calls or quality scores.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _rows(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: each line must be a JSON object")
        result.append(value)
    return result


def _number(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    return float(value) if value is not None else default


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    costs = [
        (_number(row, "input_tokens") / 1_000_000) * _number(row, "input_price")
        + (_number(row, "output_tokens") / 1_000_000) * _number(row, "output_price")
        for row in rows
    ]
    latencies = [_number(row, "latency_ms") for row in rows]
    qualities = [_number(row, "quality") for row in rows]
    return {
        "requests": len(rows),
        "success_rate": sum(bool(row.get("success")) for row in rows) / len(rows)
        if rows
        else 0.0,
        "quality_mean": statistics.mean(qualities) if qualities else 0.0,
        "cost": sum(costs),
        "latency_p50_ms": statistics.median(latencies) if latencies else 0.0,
        "cascade_rate": sum(_number(row, "cascade_count") > 0 for row in rows) / len(rows)
        if rows
        else 0.0,
        "upgrade_rate": sum(_number(row, "upgrade_count") > 0 for row in rows) / len(rows)
        if rows
        else 0.0,
        "degrade_rate": sum(_number(row, "degrade_count") > 0 for row in rows) / len(rows)
        if rows
        else 0.0,
        "classifier_cost_share": sum(_number(row, "classifier_cost") for row in rows)
        / sum(costs)
        if sum(costs) > 0
        else 0.0,
        "decision_log_coverage": sum(bool(row.get("decision_logged")) for row in rows) / len(rows)
        if rows
        else 0.0,
        "reasons": dict(Counter(str(row.get("decision_reason") or "unknown") for row in rows)),
    }


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group = str(row.get("group") or "")
        if group not in {"A", "B"}:
            raise ValueError("group must be A or B")
        groups[group].append(row)
    if not groups.get("A") or not groups.get("B"):
        raise ValueError("evidence must contain both A and B groups")
    a, b = _summary(groups["A"]), _summary(groups["B"])
    quality_relative_drop = (a["quality_mean"] - b["quality_mean"]) / a["quality_mean"] if a["quality_mean"] else 0.0
    cost_reduction = (a["cost"] - b["cost"]) / a["cost"] if a["cost"] else 0.0
    report = {
        "groups": {"A_static": a, "B_dynamic": b},
        "comparison": {
            "quality_relative_drop": quality_relative_drop,
            "cost_reduction": cost_reduction,
            "latency_p50_change_ms": b["latency_p50_ms"] - a["latency_p50_ms"],
        },
        "gates": {
            "quality": quality_relative_drop <= 0.03,
            "cost": cost_reduction >= 0.20 and b["classifier_cost_share"] <= 0.05,
            "latency": b["latency_p50_ms"] <= a["latency_p50_ms"]
            and b["latency_p50_ms"] - a["latency_p50_ms"] <= 300,
            "reliability": b["success_rate"] >= 0.99 and a["success_rate"] >= 0.99,
            "audit": b["decision_log_coverage"] >= 1.0,
        },
    }
    report["passed"] = all(report["gates"].values())
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="A/B experiment JSONL")
    parser.add_argument("--output", type=Path, help="write report JSON to this path")
    args = parser.parse_args()
    try:
        report = evaluate(_rows(args.evidence))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
