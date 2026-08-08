from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_DIR = Path(__file__).parents[1]
sys.path.insert(0, str(MODULE_DIR))
SPEC = importlib.util.spec_from_file_location("agentteams_delivery_runner", MODULE_DIR / "delivery_runner.py")
assert SPEC and SPEC.loader
delivery_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = delivery_runner
SPEC.loader.exec_module(delivery_runner)


def test_delivery_runner_requires_delivery_identity() -> None:
    try:
        delivery_runner.load_config(
            {"AGENTTEAMS_BRIDGE_BASE_URL": "http://bridge/v1", "AGENTTEAMS_BRIDGE_TOKEN": "token", "AGENTTEAMS_WORKER_IDENTITY": "quality-auditor"}
        )
    except ValueError as exc:
        assert "delivery-reporter" in str(exc)
    else:
        raise AssertionError("delivery runtime accepted another identity")


def test_delivery_runner_records_closeout_recommendation_without_closing(monkeypatch) -> None:
    assignment = {"case_id": "case-1", "work_item": {"work_item_id": "delivery-01", "context_refs": [{"kind": "task", "id": "task-1"}]}}
    calls: list[str] = []
    monkeypatch.setattr(delivery_runner, "claim_next", lambda *_args, dry_run=False, **_kwargs: calls.append("preview" if dry_run else "claim") or {"assignment": assignment})
    monkeypatch.setattr(delivery_runner, "heartbeat_work_item", lambda *_args, **_kwargs: calls.append("heartbeat") or {})
    monkeypatch.setattr(delivery_runner, "request_json", lambda url, *_args, **_kwargs: calls.append("events" if url.endswith("/events") else "artifacts") or ({"events": [{}]} if url.endswith("/events") else {"items": [{}]}))
    monkeypatch.setattr(delivery_runner, "record_evidence", lambda *_args, **kwargs: calls.append("evidence") or kwargs)
    monkeypatch.setattr(delivery_runner, "complete_work_item", lambda *_args, **_kwargs: calls.append("complete") or {"status": "completed"})

    result = delivery_runner.run_once(delivery_runner.DeliveryWorkerConfig("http://bridge/v1", "token", 1))

    assert calls == ["preview", "claim", "heartbeat", "events", "artifacts", "evidence", "complete"]
    assert result["action"] == "closeout_recommended"
