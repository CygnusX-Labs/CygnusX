#!/usr/bin/env python3
"""Bridge-only Delivery Worker that prepares a human-reviewable closeout recommendation."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from claim_next import claim_next, complete_work_item, heartbeat_work_item, record_evidence, request_json


@dataclass(frozen=True)
class DeliveryWorkerConfig:
    bridge_url: str
    token: str
    poll_seconds: float


def load_config(environ: dict[str, str] | None = None) -> DeliveryWorkerConfig:
    values = os.environ if environ is None else environ
    bridge_url = values.get("AGENTTEAMS_BRIDGE_BASE_URL", "").strip()
    token = values.get("AGENTTEAMS_BRIDGE_TOKEN", "").strip()
    if values.get("AGENTTEAMS_WORKER_IDENTITY", "delivery-reporter") != "delivery-reporter":
        raise ValueError("Delivery runtime requires the delivery-reporter identity")
    if not bridge_url or not token:
        raise ValueError("Bridge URL and delivery-reporter token are required")
    return DeliveryWorkerConfig(bridge_url, token, max(float(values.get("AGENTTEAMS_WORKER_POLL_SECONDS", "5")), 1.0))


def _task_id(assignment: dict[str, Any]) -> str | None:
    work_item = assignment.get("work_item")
    if not isinstance(work_item, dict):
        raise RuntimeError("Bridge returned malformed delivery Work Item")
    for reference in work_item.get("context_refs") or []:
        if isinstance(reference, dict) and reference.get("kind") == "task" and isinstance(reference.get("id"), str):
            return reference["id"]
    return None


def run_once(config: DeliveryWorkerConfig) -> dict[str, Any]:
    identity = "delivery-reporter"
    preview = claim_next(config.bridge_url, identity, config.token, dry_run=True)
    if preview.get("assignment") is None:
        return {"action": "idle", "identity": identity}
    claimed = claim_next(config.bridge_url, identity, config.token)
    assignment = claimed.get("assignment")
    if assignment is None:
        return {"action": "claim_raced", "identity": identity}
    task_id = _task_id(assignment)
    heartbeat_work_item(config.bridge_url, identity, config.token, assignment, summary="Delivery evidence package started.")
    case_id = str(assignment["case_id"])
    events = request_json(f"{config.bridge_url.rstrip('/')}/cases/{case_id}/events", {"X-Bridge-Identity": identity, "X-Bridge-Token": config.token}, method="GET", opener=urlopen)
    artifacts: dict[str, Any] = {}
    if task_id:
        artifacts = request_json(f"{config.bridge_url.rstrip('/')}/tasks/{task_id}/artifacts", {"X-Bridge-Identity": identity, "X-Bridge-Token": config.token}, method="GET", opener=urlopen)
    event_count = len(events.get("events", [])) if isinstance(events.get("events"), list) else 0
    artifact_count = len(artifacts.get("items", [])) if isinstance(artifacts.get("items"), list) else 0
    summary = f"已汇总 {event_count} 条审计事件和 {artifact_count} 条逻辑产物引用；建议人工复核后关闭 Case。"
    record_evidence(config.bridge_url, identity, config.token, assignment, event_type="delivery.closeout_recommended", summary=summary, context_refs=[{"kind": "task", "id": task_id}] if task_id else [], omic_task_id=task_id, skill_name="delivery-pack", payload={"event_count": event_count, "artifact_count": artifact_count, "auto_close": False})
    completed = complete_work_item(config.bridge_url, identity, config.token, assignment, summary)
    return {"action": "closeout_recommended", "identity": identity, "case_id": case_id, "task_id": task_id, "status": completed.get("status")}


def main() -> int:
    try:
        config = load_config()
    except ValueError as exc:
        print(f"delivery worker configuration failed: {exc}", flush=True)
        return 2
    while True:
        try:
            print(json.dumps(run_once(config), ensure_ascii=False, separators=(",", ":")), flush=True)
        except (HTTPError, URLError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"delivery worker failed: {exc}", flush=True)
        time.sleep(config.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
