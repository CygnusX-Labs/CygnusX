"""Verify an archived benchmark and recompute metrics without executing archived code.

Hashes establish consistency with a manifest, not authorship or scientific correctness.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from cygnusx.domain.research.benchmark import BenchmarkCase, BenchmarkRun, summarize


def verified_bytes(root: Path, name: str, expected: str) -> bytes:
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError("invalid archive path or checksum")
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("invalid archive path or checksum")
    content = candidate.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f"archive checksum mismatch: {name}")
    return content


def verify_archive(archive: Path) -> dict[str, Any]:
    root = archive.resolve()
    manifest = json.loads((root / "experiment_manifest.json").read_text())
    if manifest.get("archive_schema_version") != "research-benchmark-archive-v1":
        raise ValueError("archive lacks the versioned output-integrity contract")
    required = {
        "benchmark_results.jsonl",
        "benchmark_results.csv",
        "benchmark_summary.json",
        "failure_catalog.json",
    }
    hashes = manifest.get("artifact_sha256", {})
    if not required <= hashes.keys():
        raise ValueError("archive lacks required artifact checksums")
    content = {name: verified_bytes(root, name, sha) for name, sha in hashes.items()}
    source_hashes = manifest.get("file_sha256", {})
    if not source_hashes:
        raise ValueError("archive lacks source snapshots")
    cases = []
    for name, sha in source_hashes.items():
        # No snapshot is imported or executed. Only bytes and fixed case records are read.
        data = verified_bytes(root, f"source_snapshot/{name}", sha)
        if name.startswith("benchmarks/research_agent/v1/cases/") and name.endswith(".json"):
            cases.append(BenchmarkCase.model_validate_json(data))
    known: dict[tuple[str, str], BenchmarkCase] = {
        (case.case_id, case.case_version): case for case in cases
    }
    if len(known) != len(cases) or not known:
        raise ValueError("missing or duplicate archived cases")
    runs = [
        BenchmarkRun.model_validate_json(line)
        for line in content["benchmark_results.jsonl"].decode().splitlines()
        if line.strip()
    ]
    for run in runs:
        case = known.get((run.case_id, run.case_version))
        if case is None:
            raise ValueError("measurement does not reference an archived case/version")
        if run.layer == "CONTROLLED_LIVE" and not case.live_execution_allowed:
            raise ValueError("measurement layer contradicts archived case authorization")
    if sorted({run.run_id for run in runs}) != manifest.get("run_ids"):
        raise ValueError("manifest run IDs disagree with raw records")
    recomputed = summarize(runs)
    recorded = json.loads(content["benchmark_summary.json"])
    if any(recorded.get(key) != value for key, value in recomputed.items()):
        raise ValueError("summary disagrees with raw-record recomputation")
    expected_failures = [
        {
            "case_id": r.case_id,
            "run_id": r.run_id,
            "system": r.system,
            "codes": r.failure_codes,
            "task_success": r.task_success,
        }
        for r in runs
        if r.failure_codes or r.task_success is False
    ]
    if json.loads(content["failure_catalog.json"]) != expected_failures:
        raise ValueError("failure catalog disagrees with raw records")
    csv_rows = list(csv.DictReader(io.StringIO(content["benchmark_results.csv"].decode())))
    expected_csv = []
    for run in runs:
        expected_csv.append(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else ""
                if value is None
                else str(value)
                for key, value in run.model_dump(mode="json").items()
            }
        )
    if csv_rows != expected_csv:
        raise ValueError("CSV disagrees with complete raw JSONL records")
    return {
        "verification": "ARCHIVE_CONSISTENT_NOT_SCIENTIFIC_ATTESTATION",
        "measurement_count": len(runs),
        "recomputed": recomputed,
        "scientific_reproduction": "NOT_EVALUATED_BY_THIS_COMMAND",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_archive(args.archive)
    if args.output:
        with args.output.open("x") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"verification": result["verification"], "output": str(args.output)}))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
