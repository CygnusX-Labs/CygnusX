"""Bridge-owned append-only JSONL audit index, intentionally separate from OmicHub data."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class AuditStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._load()
        self._lock = asyncio.Lock()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or not isinstance(event.get("case_id"), str):
                continue
            self._events.setdefault(event["case_id"], []).append(event)
            payload = event.get("payload")
            if event.get("event_type") != "omic_task.submitted" or not isinstance(payload, dict):
                continue
            idempotency_key = payload.get("idempotency_key")
            receipt = payload.get("receipt")
            if isinstance(idempotency_key, str) and isinstance(receipt, dict):
                self._idempotency[idempotency_key] = receipt

    async def get_receipt(self, idempotency_key: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._idempotency.get(idempotency_key)

    async def save_receipt(self, idempotency_key: str, receipt: dict[str, Any]) -> None:
        async with self._lock:
            self._idempotency[idempotency_key] = receipt

    async def record(
        self, *, case_id: str, actor: str, event_type: str, payload: dict[str, Any]
    ) -> tuple[str, datetime]:
        event_id = str(uuid4())
        recorded_at = datetime.now(UTC)
        event = {
            "event_id": event_id,
            "recorded_at": recorded_at.isoformat(),
            "case_id": case_id,
            "actor": actor,
            "event_type": event_type,
            "payload": payload,
        }
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        async with self._lock:
            self._events.setdefault(case_id, []).append(event)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(_append, self._path, encoded)
        return event_id, recorded_at

    async def list_events(self, case_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return [*self._events.get(case_id, [])]

    async def metrics(self) -> dict[str, int]:
        async with self._lock:
            all_events = [event for events in self._events.values() for event in events]
            return {
                "case_count": len(self._events),
                "event_count": len(all_events),
                "submitted_task_count": sum(
                    event["event_type"] == "omic_task.submitted" for event in all_events
                ),
                "quality_decision_count": sum(
                    event["event_type"] == "quality.decision" for event in all_events
                ),
                "closed_case_count": sum(
                    event["event_type"] == "case.closed" for event in all_events
                ),
            }


def _append(path: Path, value: str) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(value)
