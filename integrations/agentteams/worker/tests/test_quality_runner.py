from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location("agentteams_quality_runner", MODULE_DIR / "quality_runner.py")
assert SPEC and SPEC.loader
quality_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = quality_runner
SPEC.loader.exec_module(quality_runner)


def test_quality_runner_requires_quality_identity() -> None:
    try:
        quality_runner.load_config(
            {"AGENTTEAMS_BRIDGE_BASE_URL": "http://bridge/v1", "AGENTTEAMS_BRIDGE_TOKEN": "token", "AGENTTEAMS_WORKER_IDENTITY": "agent-code"}
        )
    except ValueError as exc:
        assert "quality-auditor" in str(exc)
    else:
        raise AssertionError("quality runtime accepted another identity")


def test_quality_runner_submits_manual_review(monkeypatch) -> None:
    assignment = {"case_id": "case-1", "work_item": {"work_item_id": "quality-01", "context_refs": [{"kind": "task", "id": "task-1"}]}}
    calls: list[str] = []
    monkeypatch.setattr(quality_runner, "claim_next", lambda *_args, dry_run=False, **_kwargs: calls.append("preview" if dry_run else "claim") or {"assignment": assignment})
    monkeypatch.setattr(quality_runner, "heartbeat_work_item", lambda *_args, **_kwargs: calls.append("heartbeat") or {})
    monkeypatch.setattr(quality_runner, "request_json", lambda *_args, **_kwargs: calls.append("artifacts") or {"items": [{"uri": "omic://artifact/1"}]})
    monkeypatch.setattr(quality_runner, "submit_quality_gate", lambda *_args, **kwargs: calls.append("quality") or {"decision": kwargs["decision"]})

    result = quality_runner.run_once(quality_runner.QualityWorkerConfig("http://bridge/v1", "token", 1))

    assert calls == ["preview", "claim", "heartbeat", "artifacts", "quality"]
    assert result["action"] == "manual_review"
