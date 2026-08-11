from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
import threading
import time

MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "agentteams_production_runner", MODULE_DIR / "production_runner.py"
)
assert SPEC and SPEC.loader
production_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = production_runner
SPEC.loader.exec_module(production_runner)


def test_production_worker_requires_supported_identity(monkeypatch) -> None:
    config = production_runner.load_config(
        {
            "AGENTTEAMS_BRIDGE_BASE_URL": "http://bridge:8080/v1",
            "AGENTTEAMS_WORKER_IDENTITY": "unknown-worker",
            "AGENTTEAMS_BRIDGE_TOKEN": "token",
        }
    )
    monkeypatch.setattr(
        production_runner,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("unsupported")),
    )
    try:
        production_runner.load_worker_profile(config)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported production identity was accepted")


def test_production_worker_supports_rnaseq_research_identity() -> None:
    config = production_runner.load_config(
        {
            "AGENTTEAMS_BRIDGE_BASE_URL": "http://bridge:8080/v1",
            "AGENTTEAMS_WORKER_IDENTITY": "agent-rnaseq",
            "AGENTTEAMS_BRIDGE_TOKEN": "rnaseq-token",
        }
    )

    assert config.identity == "agent-rnaseq"


def test_production_worker_loads_profile_from_bridge(monkeypatch) -> None:
    config = production_runner.ProductionWorkerConfig(
        "http://bridge:8080/v1", "agent-atacseq", "token", 1
    )

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"worker_profiles":{"agent-atacseq":{"agent_id":"agent-atacseq","capability":"interpretation"}}}'

    monkeypatch.setattr(production_runner, "urlopen", lambda *_args, **_kwargs: Response())

    assert production_runner.load_worker_profile(config) == ("agent-atacseq", "interpretation")


def test_production_worker_claims_and_uses_bridge_execution(monkeypatch) -> None:
    calls: list[str] = []
    assignment = {
        "case_id": "case-1",
        "work_item": {
            "work_item_id": "code-01",
            "objective": "Review this analysis script.",
            "context_refs": [{"kind": "project", "id": "project-1"}],
        },
    }

    def fake_claim(*_args, dry_run: bool = False, **_kwargs):
        calls.append("preview" if dry_run else "claim")
        return {"assignment": assignment, "claimed": not dry_run}

    def fake_heartbeat(*_args, **_kwargs):
        calls.append("heartbeat")
        return {"status": "claimed"}

    def fake_execute(*_args, **kwargs):
        calls.append("execute")
        assert kwargs["agent_id"] == "agent-code"
        assert kwargs["capability"] == "planning_advice"
        assert "Review this analysis script" in kwargs["question"]
        return {"status": "completed", "work_item_id": "code-01"}

    monkeypatch.setattr(production_runner, "claim_next", fake_claim)
    monkeypatch.setattr(
        production_runner, "load_worker_profile", lambda _config: ("agent-code", "planning_advice")
    )
    monkeypatch.setattr(production_runner, "heartbeat_work_item", fake_heartbeat)
    monkeypatch.setattr(production_runner, "execute_readonly_work_item", fake_execute)
    config = production_runner.ProductionWorkerConfig(
        bridge_url="http://bridge:8080/v1", identity="agent-code", token="code", poll_seconds=1
    )

    result = production_runner.run_once(config)

    assert calls == ["preview", "claim", "heartbeat", "execute"]
    assert result["action"] == "completed"
    assert result["work_item_id"] == "code-01"


def test_production_worker_forwards_workspace_execution_mode(monkeypatch) -> None:
    assignment = {
        "case_id": "case-1",
        "work_item": {
            "work_item_id": "exec-01",
            "objective": "Build tree.",
            "execution_mode": "workspace_execution",
        },
    }
    monkeypatch.setattr(
        production_runner, "claim_next", lambda *_args, **_kwargs: {"assignment": assignment}
    )
    monkeypatch.setattr(
        production_runner, "load_worker_profile", lambda _config: ("agent-code", "planning_advice")
    )
    monkeypatch.setattr(production_runner, "heartbeat_work_item", lambda *_args, **_kwargs: {})
    observed = {}
    monkeypatch.setattr(
        production_runner,
        "execute_readonly_work_item",
        lambda *_args, **kwargs: observed.update(kwargs) or {"status": "completed"},
    )

    production_runner.run_once(
        production_runner.ProductionWorkerConfig("http://bridge", "agent-code", "token", 1)
    )

    assert observed["capability"] == "workspace_execution"
    assert observed["execution_mode"] == "workspace_execution"


def test_production_worker_runs_up_to_configured_concurrency(monkeypatch) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_run_once(_config):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return {"action": "completed"}

    monkeypatch.setattr(production_runner, "run_once", fake_run_once)
    config = production_runner.ProductionWorkerConfig(
        "http://bridge", "agent-code", "token", 1, max_concurrent=2
    )

    assert len(production_runner.run_batch_once(config)) == 2
    assert peak == 2


def test_production_worker_forwards_evidence_refs_and_readonly_tools(monkeypatch) -> None:
    assignment = {
        "case_id": "case-1",
        "work_item": {
            "work_item_id": "quality-01",
            "objective": "Review QC.",
            "context_refs": [
                {"kind": "task", "id": "task-1"},
                {"kind": "file", "id": "file-1", "location": "reports/qc.tsv"},
            ],
        },
    }
    monkeypatch.setattr(
        production_runner, "claim_next", lambda *_args, **_kwargs: {"assignment": assignment}
    )
    monkeypatch.setattr(
        production_runner, "load_worker_profile", lambda _config: ("agent-qc", "quality-gate")
    )
    monkeypatch.setattr(production_runner, "heartbeat_work_item", lambda *_args, **_kwargs: {})
    observed = {}
    monkeypatch.setattr(
        production_runner,
        "execute_readonly_work_item",
        lambda *_args, **kwargs: observed.update(kwargs) or {"status": "completed"},
    )

    production_runner.run_once(
        production_runner.ProductionWorkerConfig("http://bridge", "quality-auditor", "token", 1)
    )

    assert observed["evidence_refs"] == ["task:task-1", "file:reports/qc.tsv"]
    assert set(observed["requested_tools"]) == set(production_runner._EVIDENCE_TOOLS)
