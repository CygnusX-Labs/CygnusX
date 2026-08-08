from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location(
    "agentteams_production_runner", MODULE_DIR / "production_runner.py"
)
assert SPEC and SPEC.loader
production_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = production_runner
SPEC.loader.exec_module(production_runner)


def test_production_worker_requires_supported_identity() -> None:
    try:
        production_runner.load_config(
            {
                "AGENTTEAMS_BRIDGE_BASE_URL": "http://bridge:8080/v1",
                "AGENTTEAMS_WORKER_IDENTITY": "quality-auditor",
                "AGENTTEAMS_BRIDGE_TOKEN": "token",
            }
        )
    except ValueError as exc:
        assert "does not support identity" in str(exc)
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
    monkeypatch.setattr(production_runner, "heartbeat_work_item", fake_heartbeat)
    monkeypatch.setattr(production_runner, "execute_readonly_work_item", fake_execute)
    config = production_runner.ProductionWorkerConfig(
        bridge_url="http://bridge:8080/v1", identity="agent-code", token="code", poll_seconds=1
    )

    result = production_runner.run_once(config)

    assert calls == ["preview", "claim", "heartbeat", "execute"]
    assert result["action"] == "completed"
    assert result["work_item_id"] == "code-01"
