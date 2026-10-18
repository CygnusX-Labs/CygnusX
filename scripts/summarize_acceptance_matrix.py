#!/usr/bin/env python3
"""Summarize an acceptance CSV without promoting child results to parent cases."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def summarize_matrix(path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if (
            not reader.fieldnames
            or "Test ID" not in reader.fieldnames
            or "状态" not in reader.fieldnames
        ):
            raise ValueError("matrix requires 'Test ID' and '状态' columns")
        rows = list(reader)

    ids = [str(row.get("Test ID", "")).strip() for row in rows]
    if any(not test_id for test_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("matrix contains an empty or duplicate Test ID")

    all_states = Counter(str(row.get("状态", "")).strip() for row in rows)
    parent_rows = [row for row in rows if "." not in str(row["Test ID"])]
    child_rows = [row for row in rows if "." in str(row["Test ID"])]
    evidence_root = repo_root or Path(__file__).resolve().parents[1]
    passing_rows = [row for row in rows if str(row.get("状态", "")).strip().startswith("PASS")]
    missing_evidence: list[dict[str, str]] = []
    for row in passing_rows:
        test_id = str(row["Test ID"]).strip()
        evidence = str(row.get("证据路径", "")).strip()
        paths = [part.strip().strip("`") for part in evidence.split(";") if part.strip()]
        if not paths:
            missing_evidence.append({"test_id": test_id, "path": "", "reason": "empty"})
            continue
        for evidence_path in paths:
            candidate = Path(evidence_path)
            if not candidate.is_absolute():
                candidate = evidence_root / candidate
            if not candidate.exists():
                missing_evidence.append(
                    {"test_id": test_id, "path": evidence_path, "reason": "not_found"}
                )
    children: dict[str, list[str]] = defaultdict(list)
    for row in child_rows:
        parent_id = str(row["Test ID"]).split(".", maxsplit=1)[0]
        children[parent_id].append(str(row["Test ID"]))

    return {
        "matrix": str(path),
        "row_count": len(rows),
        "parent_case_count": len(parent_rows),
        "child_assertion_count": len(child_rows),
        "status_counts_all_rows": dict(sorted(all_states.items())),
        "status_counts_parent_cases": dict(
            sorted(Counter(str(row["状态"]).strip() for row in parent_rows).items())
        ),
        "status_counts_child_assertions": dict(
            sorted(Counter(str(row["状态"]).strip() for row in child_rows).items())
        ),
        "pass_evidence_check": {
            "rows_checked": len(passing_rows),
            "missing_count": len(missing_evidence),
            "missing": missing_evidence,
        },
        "children_by_parent": {key: sorted(value) for key, value in sorted(children.items())},
        "aggregation_rule": "child assertions are reported separately and never change parent status",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--strict-evidence",
        action="store_true",
        help="fail instead of writing a summary if a PASS row has missing evidence",
    )
    args = parser.parse_args()
    summary = summarize_matrix(args.matrix)
    if args.strict_evidence and summary["pass_evidence_check"]["missing_count"]:
        raise SystemExit("PASS matrix rows have missing evidence; inspect pass_evidence_check")
    output = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
