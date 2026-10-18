import csv
import sys

import pytest
from scripts.summarize_acceptance_matrix import main, summarize_matrix

pytestmark = pytest.mark.unit


def _write_matrix(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["Test ID", "状态", "证据路径"])
        writer.writeheader()
        writer.writerows(rows)


def test_matrix_summary_checks_each_pass_evidence_path(tmp_path):
    evidence = tmp_path / "runtime.log"
    evidence.write_text("evidence\n", encoding="utf-8")
    matrix = tmp_path / "matrix.csv"
    _write_matrix(
        matrix,
        [
            {"Test ID": "CASE-01", "状态": "PASS_RUNTIME", "证据路径": str(evidence)},
            {"Test ID": "CASE-02", "状态": "BLOCKED", "证据路径": "missing.log"},
        ],
    )

    summary = summarize_matrix(matrix, repo_root=tmp_path)

    assert summary["pass_evidence_check"] == {
        "rows_checked": 1,
        "missing_count": 0,
        "missing": [],
    }


def test_matrix_summary_reports_missing_or_empty_pass_evidence(tmp_path):
    matrix = tmp_path / "matrix.csv"
    _write_matrix(
        matrix,
        [
            {"Test ID": "CASE-01", "状态": "PASS_ISOLATED", "证据路径": "missing.log"},
            {"Test ID": "CASE-02", "状态": "PASS_RUNTIME", "证据路径": ""},
        ],
    )

    summary = summarize_matrix(matrix, repo_root=tmp_path)

    assert summary["pass_evidence_check"]["missing_count"] == 2
    assert summary["pass_evidence_check"]["missing"] == [
        {"test_id": "CASE-01", "path": "missing.log", "reason": "not_found"},
        {"test_id": "CASE-02", "path": "", "reason": "empty"},
    ]


def test_strict_cli_fails_when_a_passing_row_has_missing_evidence(tmp_path, monkeypatch):
    matrix = tmp_path / "matrix.csv"
    _write_matrix(
        matrix,
        [{"Test ID": "CASE-01", "状态": "PASS_RUNTIME", "证据路径": "missing.log"}],
    )
    monkeypatch.setattr(
        sys, "argv", ["summarize_acceptance_matrix.py", str(matrix), "--strict-evidence"]
    )

    with pytest.raises(SystemExit, match="PASS matrix rows have missing evidence"):
        main()
