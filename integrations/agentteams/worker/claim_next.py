#!/usr/bin/env python3
"""Claim one Bridge-assigned Work Item for an external AgentTeams Worker.

The command is intentionally controller-agnostic. A Worker runtime invokes it before asking an
LLM to execute a skill; stdout is a small JSON envelope and never contains Bridge credentials or
Bridge-private Case fields.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UrlOpen = Callable[[Request], Any]


def request_json(
    url: str,
    headers: dict[str, str],
    *,
    method: str,
    opener: UrlOpen,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_headers = dict(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    with opener(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Bridge returned a non-object response")
    return payload


def assignment_envelope(pending: dict[str, Any], work_item: dict[str, Any]) -> dict[str, Any]:
    """Keep stdout limited to the documented Worker assignment contract."""
    return {
        "case_id": pending.get("case_id"),
        "project_ref": pending.get("project_ref"),
        "intent": pending.get("intent"),
        "status": pending.get("status"),
        "omic_task_ids": pending.get("omic_task_ids", []),
        "quality_decision": pending.get("quality_decision"),
        "work_item": work_item,
    }


def claim_next(
    bridge_url: str,
    identity: str,
    token: str,
    *,
    dry_run: bool = False,
    opener: UrlOpen = urlopen,
) -> dict[str, Any]:
    base_url = bridge_url.rstrip("/")
    headers = {"X-Bridge-Identity": identity, "X-Bridge-Token": token}
    inbox = request_json(f"{base_url}/work-items/assigned", headers, method="GET", opener=opener)
    items = inbox.get("items", [])
    if not isinstance(items, list):
        raise RuntimeError("Bridge returned malformed Worker inbox")
    pending = next(
        (
            item
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get("work_item"), dict)
            and item["work_item"].get("status") == "pending"
        ),
        None,
    )
    if pending is None:
        return {"assignment": None}

    case_id = pending.get("case_id")
    work_item = pending["work_item"]
    work_item_id = work_item.get("work_item_id")
    if not isinstance(case_id, str) or not isinstance(work_item_id, str):
        raise RuntimeError("Bridge returned malformed Work Item identity")
    if dry_run:
        return {"assignment": assignment_envelope(pending, work_item), "claimed": False}

    claimed = request_json(
        f"{base_url}/cases/{case_id}/work-items/{work_item_id}/claim",
        headers,
        method="POST",
        opener=opener,
    )
    return {
        "assignment": {
            **assignment_envelope(pending, claimed),
        },
        "claimed": True,
    }


def complete_work_item(
    bridge_url: str,
    identity: str,
    token: str,
    assignment: dict[str, Any],
    summary: str,
    *,
    opener: UrlOpen = urlopen,
) -> dict[str, Any]:
    """Mark an already claimed, read-only assignment completed."""
    case_id = assignment.get("case_id")
    work_item = assignment.get("work_item")
    if not isinstance(case_id, str) or not isinstance(work_item, dict):
        raise RuntimeError("Bridge returned malformed claimed assignment")
    work_item_id = work_item.get("work_item_id")
    if not isinstance(work_item_id, str):
        raise RuntimeError("Bridge returned malformed Work Item identity")
    return request_json(
        f"{bridge_url.rstrip('/')}/cases/{case_id}/work-items/{work_item_id}",
        {"X-Bridge-Identity": identity, "X-Bridge-Token": token},
        method="POST",
        opener=opener,
        payload={"status": "completed", "summary": summary},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim one assigned OmicHub AgentTeams Work Item")
    parser.add_argument("--bridge-url", default=os.environ.get("AGENTTEAMS_BRIDGE_BASE_URL", ""))
    parser.add_argument("--identity", default=os.environ.get("AGENTTEAMS_WORKER_IDENTITY", ""))
    parser.add_argument("--token", default=os.environ.get("AGENTTEAMS_BRIDGE_TOKEN", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.bridge_url or not args.identity or not args.token:
        parser.error("Bridge URL, Worker identity, and Bridge token are required")
    try:
        result = claim_next(
            args.bridge_url,
            args.identity,
            args.token,
            dry_run=args.dry_run,
        )
    except HTTPError as exc:
        print(f"Bridge request failed with HTTP {exc.code}", file=sys.stderr)
        return 2
    except (URLError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Bridge worker claim failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
