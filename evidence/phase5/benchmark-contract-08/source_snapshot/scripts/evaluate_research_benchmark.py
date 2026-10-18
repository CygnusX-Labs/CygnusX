"""Offline contract benchmark or import measured baseline records; never runs business Tasks.

Run: .venv/bin/python scripts/evaluate_research_benchmark.py --output evidence/phase5/benchmark-run-01
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from cygnusx.application.schemas.dataset import DataHandoff
from cygnusx.application.schemas.research_claims import ClaimDraft
from cygnusx.application.schemas.research_plan import ResearchPlanDraft
from cygnusx.domain.research.benchmark import BenchmarkCase, BenchmarkRun, summarize
from cygnusx.domain.research.plan_state import ready_steps
from cygnusx.domain.research.scientific_validation import assess_claim, check_scientific_inputs
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]


def runtime_environment() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in ("pydantic", "SQLAlchemy", "numpy", "pytest"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "installed_packages": packages,
        "scope": "host_not_worker",
    }


def evaluate_public_input(value: dict[str, Any]) -> dict[str, Any]:
    """No case IDs, gold labels or expected answers enter the candidate boundary."""
    kind = value["operation"]
    if kind == "claim_grounding":
        claim = ClaimDraft.model_validate(value["claim"])
        available = {tuple(x) for x in value["available_evidence"]}
        return {
            "status": assess_claim(
                claim, available, contradictory=value.get("conflicting", False)
            ).provenance_status
        }
    if kind == "scientific_eligibility":
        result = check_scientific_inputs(
            DataHandoff.model_validate(value["handoff"]), value["flow_id"]
        )
        return {"status": result.status, "gaps": list(result.gaps)}
    if kind == "validate_plan":
        try:
            ResearchPlanDraft.model_validate(value["draft"])
            return {"valid": True}
        except ValidationError:
            return {"valid": False}
    if kind == "ready_steps":
        from cygnusx.application.schemas.research_plan import StepStatus

        draft = ResearchPlanDraft.model_validate(value["draft"])
        states = {key: StepStatus(state) for key, state in value["states"].items()}
        return {"ready": ready_steps(draft, states)}
    raise ValueError("unsupported benchmark operation")


def evaluate_cases(cases: list[BenchmarkCase], run_id: str) -> list[BenchmarkRun]:
    runs = []
    environment = runtime_environment()
    for case in cases:
        if (
            case.difficulty != "small_synthetic"
            or case.network_allowed
            or case.live_execution_allowed
        ):
            raise ValueError("this runner only supports synthetic offline contract cases")
        started = time.perf_counter()
        output = evaluate_public_input(case.public_input)
        elapsed = time.perf_counter() - started
        # Gold is accessed only by the scorer, never by evaluate_public_input.
        matches = all(output.get(key) == val for key, val in case.gold.items())
        runs.append(
            BenchmarkRun(
                run_id=run_id,
                case_id=case.case_id,
                case_version=case.case_version,
                system="contract_candidate",
                layer="SYNTHETIC_CONTRACT",
                repetition=1,
                goal_kind="CONTRACT_VALIDATION",
                task_success=matches,
                valid_plan=output.get("valid"),
                recovery_safe=matches if case.category == "safety_recovery" else None,
                elapsed_seconds=elapsed,
                environment=environment,
                trace=[
                    {
                        "origin": "server_contract_validator",
                        "output": output,
                        "gold_review_status": case.review_status,
                    }
                ],
                failure_codes=[] if matches else ["EXPECTED_CONTRACT_OUTCOME_MISMATCH"],
            )
        )
    return runs


def export_measurements(
    output: Path,
    runs: list[BenchmarkRun],
    cases: list[BenchmarkCase],
    *,
    source: Literal["HOST_CONTRACT_RUN", "IMPORTED_RECORDS", "UNSPECIFIED"] = "UNSPECIFIED",
    input_sha256: str | None = None,
) -> None:
    known: dict[tuple[str, str], BenchmarkCase] = {
        (case.case_id, case.case_version): case for case in cases
    }
    if len(known) != len(cases):
        raise ValueError("duplicate case/version in registry")
    for run in runs:
        case = known.get((run.case_id, run.case_version))
        if case is None:
            raise ValueError("unknown case/version in measurement")
        if run.layer == "CONTROLLED_LIVE" and (
            case.difficulty != "controlled_live" or not case.live_execution_allowed
        ):
            raise ValueError("case is not authorized for a controlled live measurement")
    # Validate aggregation before creating any output, including duplicate records.
    summary = summarize(runs)
    # Fail rather than replace a previous experiment or its raw measurements.
    output.mkdir(parents=True, exist_ok=False)
    with (output / "benchmark_results.jsonl").open("x") as stream:
        for row in runs:
            stream.write(row.model_dump_json() + "\n")
    fields = list(BenchmarkRun.model_fields)
    with (output / "benchmark_results.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in runs:
            values = row.model_dump(mode="json")
            writer.writerow(
                {
                    key: json.dumps(values[key], ensure_ascii=False)
                    if isinstance(values[key], (dict, list))
                    else values[key]
                    for key in fields
                }
            )
    summary["environment"] = {
        "export_host": runtime_environment(),
        "measurement_source": source,
        "missing_measurement_environment": sum(not r.environment for r in runs),
        "network": "not_used_by_contract_runner" if source == "HOST_CONTRACT_RUN" else "UNKNOWN",
        "note": "Export host does not attest the origin/environment of imported measurements",
    }
    summary["human_reviewed_cases"] = sum(c.review_status == "HUMAN_REVIEWED" for c in cases)
    summary["pending_review_cases"] = sum(c.review_status != "HUMAN_REVIEWED" for c in cases)
    (output / "benchmark_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    paths = [
        Path(__file__),
        ROOT / "scripts/analyze_research_benchmark.py",
        ROOT / "src/cygnusx/domain/research/benchmark.py",
        ROOT / "src/cygnusx/domain/research/scientific_validation.py",
        ROOT / "src/cygnusx/application/schemas/research_plan.py",
    ]
    paths += sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))
    paths += sorted((ROOT / "src/cygnusx/domain/research").glob("*.py"))
    paths += [
        ROOT / "src/cygnusx/application/schemas" / name
        for name in ("dataset.py", "research_claims.py", "agent_tools.py")
    ]
    paths += [ROOT / "uv.lock", ROOT / "pyproject.toml"]
    paths = sorted(set(paths))
    # Preserve exact evaluated source alongside hashes while changes are uncommitted.
    for path in paths:
        if path.suffix in {".py", ".json", ".lock", ".toml"}:
            archived = output / "source_snapshot" / path.relative_to(ROOT)
            archived.parent.mkdir(parents=True, exist_ok=True)
            archived.write_bytes(path.read_bytes())
    failure_catalog = [
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
    (output / "failure_catalog.json").write_text(json.dumps(failure_catalog, indent=2) + "\n")
    artifacts = [
        "benchmark_results.jsonl",
        "benchmark_results.csv",
        "benchmark_summary.json",
        "failure_catalog.json",
    ]
    manifest = {
        "archive_schema_version": "research-benchmark-archive-v1",
        "measurement_source": source,
        "input_measurements_sha256": input_sha256,
        "artifact_sha256": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in artifacts
        },
        "run_ids": sorted({r.run_id for r in runs}),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "file_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
        "model_ids_in_records": sorted({r.model_id for r in runs if r.model_id}),
        "model_id": None,
        "prompt_hash": None,
        "temperature": None,
        "random_seed": None,
        "cache": "not_used" if source == "HOST_CONTRACT_RUN" else "UNKNOWN",
        "max_retries": 0 if source == "HOST_CONTRACT_RUN" else None,
        "live_execution": False,
        "baseline_status": {
            system: "IMPORTED_RECORDS_NOT_INDEPENDENTLY_VERIFIED"
            if any(r.system == system for r in runs)
            else "NOT_MEASURED"
            for system in ("manual", "existing_assistant")
        },
        "record_counts_by_system": {
            system: sum(r.system == system for r in runs)
            for system in ("manual", "existing_assistant", "contract_candidate")
        },
        "integrity_note": "Hashes detect changes relative to this manifest; not a signed attestation",
    }
    (output / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--measurements",
        type=Path,
        help="Import actual manual/assistant run JSONL; no simulated baseline",
    )
    args = parser.parse_args()
    paths = sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))
    cases = [BenchmarkCase.model_validate_json(path.read_text()) for path in paths]
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("duplicate case_id")
    raw_measurements = args.measurements.read_bytes() if args.measurements else None
    if raw_measurements is not None:
        runs = [
            BenchmarkRun.model_validate_json(line)
            for line in raw_measurements.decode().splitlines()
            if line.strip()
        ]
        known = {(case.case_id, case.case_version) for case in cases}
        if any((r.case_id, r.case_version) not in known for r in runs):
            raise ValueError("unknown case/version in measurement")
    else:
        runs = evaluate_cases(cases, str(uuid4()))
    export_measurements(
        args.output,
        runs,
        cases,
        source="IMPORTED_RECORDS" if args.measurements else "HOST_CONTRACT_RUN",
        input_sha256=hashlib.sha256(raw_measurements).hexdigest()
        if raw_measurements is not None
        else None,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "measurements": len(runs),
                "scope": "see manifest; no live runtime acceptance",
            }
        )
    )


if __name__ == "__main__":
    main()
