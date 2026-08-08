#!/usr/bin/env python3
"""Conservative Bridge-only Quality Worker for completed AgentTeams tasks."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from claim_next import claim_next, heartbeat_work_item, request_json, submit_quality_gate


@dataclass(frozen=True)
class QualityWorkerConfig:
    bridge_url: str
    token: str
    poll_seconds: float


def load_config(environ: dict[str, str] | None = None) -> QualityWorkerConfig:
    values = os.environ if environ is None else environ
    bridge_url = values.get("AGENTTEAMS_BRIDGE_BASE_URL", "").strip()
    token = values.get("AGENTTEAMS_BRIDGE_TOKEN", "").strip()
    if values.get("AGENTTEAMS_WORKER_IDENTITY", "quality-auditor") != "quality-auditor":
        raise ValueError("Quality runtime requires the quality-auditor identity")
    if not bridge_url or not token:
        raise ValueError("Bridge URL and quality-auditor token are required")
    return QualityWorkerConfig(bridge_url, token, max(float(values.get("AGENTTEAMS_WORKER_POLL_SECONDS", "5")), 1.0))


def _task_id(assignment: dict[str, Any]) -> str:
    work_item = assignment.get("work_item")
    if not isinstance(work_item, dict):
        raise RuntimeError("Bridge returned malformed quality Work Item")
    for reference in work_item.get("context_refs") or []:
        if isinstance(reference, dict) and reference.get("kind") == "task" and isinstance(reference.get("id"), str):
            return reference["id"]
    raise RuntimeError("Quality Work Item does not contain a task reference")


def run_once(config: QualityWorkerConfig) -> dict[str, Any]:
    identity = "quality-auditor"
    preview = claim_next(config.bridge_url, identity, config.token, dry_run=True)
    if preview.get("assignment") is None:
        return {"action": "idle", "identity": identity}
    claimed = claim_next(config.bridge_url, identity, config.token)
    assignment = claimed.get("assignment")
    if assignment is None:
        return {"action": "claim_raced", "identity": identity}
    task_id = _task_id(assignment)
    heartbeat_work_item(config.bridge_url, identity, config.token, assignment, summary="Quality evidence inspection started.")
    artifacts = request_json(
        f"{config.bridge_url.rstrip('/')}/tasks/{task_id}/artifacts",
        {"X-Bridge-Identity": identity, "X-Bridge-Token": config.token},
        method="GET",
        opener=urlopen,
    )
    count = len(artifacts.get("items", [])) if isinstance(artifacts.get("items"), list) else 0
    result = submit_quality_gate(
        config.bridge_url,
        identity,
        config.token,
        assignment,
        task_id=task_id,
        decision="manual_review",
        summary=f"已检查 {count} 条逻辑产物证据；自动 Worker 不放行，需人工质量复核。",
    )
    return {
        "action": "manual_review",
        "identity": identity,
        "case_id": assignment["case_id"],
        "task_id": task_id,
        "status": result.get("decision"),
    }


def main() -> int:
    try:
        config = load_config()
    except ValueError as exc:
        print(f"quality worker configuration failed: {exc}", flush=True)
        return 2
    while True:
        try:
            print(json.dumps(run_once(config), ensure_ascii=False, separators=(",", ":")), flush=True)
        except (HTTPError, URLError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"quality worker failed: {exc}", flush=True)
        time.sleep(config.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
