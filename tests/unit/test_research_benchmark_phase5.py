"""Metric denominators, unknowns, case-review honesty and repeatable raw exports."""

import importlib.util
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cygnusx.domain.research.benchmark import BenchmarkCase, BenchmarkRun, proportion, summarize

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def measurement(**updates):
    fields = dict(
        run_id="isolated-01",
        case_id="synthetic_case",
        case_version="1.0",
        system="contract_candidate",
        layer="SYNTHETIC_CONTRACT",
        repetition=1,
        goal_kind="CONTRACT_VALIDATION",
        elapsed_seconds=1,
    )
    fields.update(updates)
    return BenchmarkRun(**fields)


def test_unknown_denominators_and_partial_success():
    rows = [
        measurement(
            task_success=True,
            evidence_valid=1,
            evidence_required=3,
            provenance_verified=0,
            provenance_required=2,
        ),
        measurement(run_id="isolated-02", task_success=False),
        measurement(run_id="isolated-03"),
    ]
    result = next(iter(summarize(rows)["groups"].values()))
    assert result["task_success_rate"]["numerator"] == 1
    assert result["task_success_rate"]["denominator"] == 2
    assert result["task_success_rate"]["not_evaluated"] == 1
    assert result["evidence_coverage"]["rate"] == 1 / 3
    assert result["provenance_completeness"]["rate"] == 0
    assert result["discovery_accuracy"]["rate"] is None
    assert result["cost_missing"] == 3 and result["cost"] == {}
    assert result["human_interventions"]["missing"] == 3
    assert proportion(0, 0)["ci95"] is None
    assert 0 <= proportion(0, 12)["ci95"][0] <= proportion(0, 12)["ci95"][1] < 1


@pytest.mark.parametrize(
    "updates",
    [
        {"evidence_valid": 2, "evidence_required": 1},
        {"reproduction_matched": True},
        {"reproduction_attempted": True},
        {"goal_kind": "RESEARCH_DELIVERY"},
        {"cost_amount": 1},
        {"cost_amount": 1, "currency": "USD"},
    ],
)
def test_invalid_measurements_rejected(updates):
    with pytest.raises(ValidationError):
        measurement(**updates)


def test_duplicate_measurement_rejected_and_prespecified_reproduction_rule():
    with pytest.raises(ValueError):
        summarize([measurement(), measurement()])
    run = measurement(
        reproduction_attempted=True,
        reproduction_matched=False,
        reproduction_rule="predeclared: SHA256 equality of exact byte artifact",
    )
    result = next(iter(summarize([run])["groups"].values()))
    assert result["reproduction_success"]["denominator"] == 1
    assert result["reproduction_success"]["numerator"] == 0


def test_cases_versioned_balanced_and_pending_review_honest():
    paths = sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))
    cases = [BenchmarkCase.model_validate_json(p.read_text()) for p in paths]
    assert len(cases) == len({c.case_id for c in cases}) == 12
    assert all(
        sum(c.category == category for c in cases) == 4
        for category in ["discovery", "planning", "safety_recovery"]
    )
    assert not any(c.network_allowed or c.live_execution_allowed for c in cases)
    assert all(c.review_status == "PENDING_HUMAN_REVIEW" for c in cases)
    bad = cases[0].model_dump()
    bad["review_status"] = "HUMAN_REVIEWED"
    with pytest.raises(ValidationError):
        BenchmarkCase.model_validate(bad)


def test_actual_synthetic_runner_repeatable_outcomes_never_overwrites(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "phase5_benchmark_runner", ROOT / "scripts/evaluate_research_benchmark.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = [
        BenchmarkCase.model_validate_json(p.read_text())
        for p in sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))
    ]
    first, second = module.evaluate_cases(cases, "first"), module.evaluate_cases(cases, "second")
    assert [r.task_success for r in first] == [r.task_success for r in second]
    # Keep frozen 1.0 candidates: missing sample identities now expose a stale gold.
    # Do not rewrite gold merely to restore a green benchmark result.
    stale = next(r for r in first if r.case_id == "planning_01")
    assert stale.task_success is False
    assert stale.failure_codes == ["EXPECTED_CONTRACT_OUTCOME_MISMATCH"]
    assert "SAMPLE_IDENTITY_REQUIRED" in stale.trace[0]["output"]["gaps"]
    assert all(r.discovery_correct is None and r.workflow_correct is None for r in first)
    module.export_measurements(tmp_path / "run", first, cases)
    raw = (tmp_path / "run/benchmark_results.jsonl").read_bytes()
    with pytest.raises(FileExistsError):
        module.export_measurements(tmp_path / "run", second, cases)
    assert (tmp_path / "run/benchmark_results.jsonl").read_bytes() == raw
    summary = json.loads((tmp_path / "run/benchmark_summary.json").read_text())
    assert summary["human_reviewed_cases"] == 0 and summary["pending_review_cases"] == 12


def test_actual_reproduction_comparison_uses_frozen_tolerances():
    from cygnusx.domain.research.benchmark import ReproductionRule, compare_reproduction

    rule = ReproductionRule(kind="numeric", rtol=1e-8, atol=1e-10)
    assert compare_reproduction([1.0, 2.0], [1.0 + 1e-10, 2.0], rule)
    assert not compare_reproduction([1.0], [1.01], rule)
    assert not compare_reproduction([float("nan")], [float("nan")], rule)
    assert not compare_reproduction([], [], rule)
    assert not compare_reproduction([1.0], [1.0, 2.0], rule)
    sha = ReproductionRule(kind="sha256")
    assert compare_reproduction("a" * 64, "a" * 64, sha)
    assert not compare_reproduction("a" * 64, "b" * 64, sha)


@pytest.mark.parametrize(
    "field,value",
    [("token", "private"), ("authorization", "Bearer private"), ("api_key", "sk-private")],
)
def test_benchmark_rejects_plaintext_credentials_in_trace(field, value):
    with pytest.raises(ValidationError):
        measurement(trace=[{field: value}])


def test_live_measurement_cannot_relabel_synthetic_case(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "phase5_runner_scope", ROOT / "scripts/evaluate_research_benchmark.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))[0]
    case = BenchmarkCase.model_validate_json(path.read_text())
    run = measurement(case_id=case.case_id, layer="CONTROLLED_LIVE")
    destination = tmp_path / "forbidden-live"
    with pytest.raises(ValueError, match="not authorized"):
        module.export_measurements(destination, [run], [case])
    assert not destination.exists()


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archived_contract(tmp_path):
    runner = load_script("evaluate_research_benchmark")
    cases = [
        BenchmarkCase.model_validate_json(p.read_text())
        for p in sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))
    ]
    runs = runner.evaluate_cases(cases, "archive-integrity-test")
    destination = tmp_path / "archive"
    runner.export_measurements(destination, runs, cases, source="HOST_CONTRACT_RUN")
    return runner, destination, runs, cases


def test_archive_recomputes_all_metrics_and_records_actual_dependency_versions(tmp_path):
    from importlib.metadata import version

    _, archive, runs, _ = archived_contract(tmp_path)
    analyzer = load_script("analyze_research_benchmark")
    result = analyzer.verify_archive(archive)
    assert result["measurement_count"] == 12
    assert result["recomputed"] == summarize(runs)
    assert result["scientific_reproduction"] == "NOT_EVALUATED_BY_THIS_COMMAND"
    assert runs[0].environment["installed_packages"]["pydantic"] == version("pydantic")
    assert (archive / "source_snapshot/uv.lock").exists()
    assert (archive / "source_snapshot/pyproject.toml").exists()
    raw = archive / "benchmark_results.jsonl"
    raw.write_text(raw.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        analyzer.verify_archive(archive)


@pytest.mark.parametrize(
    "artifact", ["benchmark_summary.json", "benchmark_results.csv", "failure_catalog.json"]
)
def test_archive_rejects_rehashed_but_inconsistent_derived_results(tmp_path, artifact):
    import hashlib

    _, archive, _, _ = archived_contract(tmp_path)
    path = archive / artifact
    if artifact == "benchmark_summary.json":
        data = json.loads(path.read_text())
        next(iter(data["groups"].values()))["task_success_rate"]["numerator"] += 1
        path.write_text(json.dumps(data))
    elif artifact.endswith("csv"):
        path.write_text(path.read_text().replace("CONTRACT_VALIDATION", "FORGED_TARGET", 1))
    else:
        path.write_text("[]")
    manifest_path = archive / "experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifact_sha256"][artifact] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="disagrees"):
        load_script("analyze_research_benchmark").verify_archive(archive)


def test_imported_measurements_are_not_export_host_attestations(tmp_path):
    runner = load_script("evaluate_research_benchmark")
    case = BenchmarkCase.model_validate_json(
        sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))[0].read_text()
    )
    row = measurement(case_id=case.case_id, system="manual", model_id="synthetic-model-label")
    archive = tmp_path / "imported"
    runner.export_measurements(
        archive, [row], [case], source="IMPORTED_RECORDS", input_sha256="a" * 64
    )
    manifest = json.loads((archive / "experiment_manifest.json").read_text())
    summary = json.loads((archive / "benchmark_summary.json").read_text())
    assert manifest["measurement_source"] == "IMPORTED_RECORDS"
    assert manifest["baseline_status"]["manual"] == "IMPORTED_RECORDS_NOT_INDEPENDENTLY_VERIFIED"
    assert manifest["record_counts_by_system"]["manual"] == 1
    assert manifest["model_ids_in_records"] == ["synthetic-model-label"]
    assert manifest["cache"] == "UNKNOWN" and manifest["max_retries"] is None
    assert summary["environment"]["missing_measurement_environment"] == 1
    assert summary["environment"]["network"] == "UNKNOWN"
    load_script("analyze_research_benchmark").verify_archive(archive)


def test_duplicate_measurements_do_not_leave_partial_archive(tmp_path):
    runner = load_script("evaluate_research_benchmark")
    case = BenchmarkCase.model_validate_json(
        sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))[0].read_text()
    )
    row = measurement(case_id=case.case_id)
    destination = tmp_path / "duplicate"
    with pytest.raises(ValueError, match="duplicate measurement"):
        runner.export_measurements(destination, [row, row], [case])
    assert not destination.exists()


def test_archive_path_cannot_escape_or_read_an_absolute_path(tmp_path):
    analyzer = load_script("analyze_research_benchmark")
    for path in ("../outside", str(tmp_path / "absolute")):
        with pytest.raises(ValueError, match="invalid archive path"):
            analyzer.verified_bytes(tmp_path.resolve(), path, "a" * 64)


def test_empty_gold_does_not_become_an_automatic_success():
    case = json.loads(
        sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))[0].read_text()
    )
    case["gold"] = {}
    with pytest.raises(ValidationError):
        BenchmarkCase.model_validate(case)


def test_candidate_failure_is_retained_without_hiding_other_cases_or_leaking_errors(monkeypatch):
    runner = load_script("evaluate_research_benchmark")
    case = BenchmarkCase.model_validate_json(
        sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))[0].read_text()
    )
    broken = case.model_copy(
        update={"case_id": "exception_fixture", "public_input": {"operation": "break"}}
    )
    original = runner.evaluate_public_input

    def evaluate(value):
        if value["operation"] == "break":
            raise ValueError("/private/secret must not enter trace")
        return original(value)

    monkeypatch.setattr(runner, "evaluate_public_input", evaluate)
    runs = runner.evaluate_cases([broken, case], "synthetic-fault")
    assert len(runs) == 2 and runs[0].task_success is False and runs[1].task_success is True
    assert "CONTRACT_CANDIDATE_ERROR" in runs[0].failure_codes
    assert "/private/secret" not in runs[0].model_dump_json()
    metrics = next(iter(summarize(runs)["groups"].values()))
    assert metrics["task_success_rate"]["denominator"] == 2
    assert metrics["task_success_rate"]["numerator"] == 1


def test_completed_but_over_budget_contract_is_not_reported_successful(monkeypatch):
    from types import SimpleNamespace

    runner = load_script("evaluate_research_benchmark")
    case = BenchmarkCase.model_validate_json(
        sorted((ROOT / "benchmarks/research_agent/v1/cases").glob("*.json"))[0].read_text()
    )
    ticks = iter([0.0, float(case.max_seconds + 1)])
    monkeypatch.setattr(runner, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
    run = runner.evaluate_cases([case], "synthetic-clock-fixture")[0]
    assert run.task_success is False
    assert "CASE_TIME_BUDGET_EXCEEDED" in run.failure_codes
