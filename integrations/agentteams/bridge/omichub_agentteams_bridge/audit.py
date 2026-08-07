"""Bridge-owned append-only JSONL audit index, intentionally separate from OmicHub data."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from .shared_state import RedisStateBackend


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class AuditStore:
    def __init__(
        self,
        path: str,
        state_store_url: str = "",
        state_store_key_prefix: str = "omichub:agentteams:audit",
    ) -> None:
        self._path = Path(path)
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._shared_state = (
            RedisStateBackend(state_store_url, state_store_key_prefix) if state_store_url else None
        )
        if self._shared_state is None:
            self._load()
        from asyncio import Lock

        self._lock = Lock()

    @property
    def _event_stream_key(self) -> str:
        if self._shared_state is None:
            raise RuntimeError("Redis audit stream is not configured")
        return f"{self._shared_state.data_key}:events"

    @property
    def _receipt_key_prefix(self) -> str:
        if self._shared_state is None:
            raise RuntimeError("Redis audit receipts are not configured")
        return f"{self._shared_state.data_key}:receipt:"

    async def aclose(self) -> None:
        if self._shared_state is not None:
            await self._shared_state.aclose()

    async def _shared_events(self, case_id: str | None = None) -> list[dict[str, Any]]:
        if self._shared_state is None:
            raise RuntimeError("Redis audit stream is not configured")
        records = await self._shared_state.client.xrange(self._event_stream_key, min="-", max="+")
        events: list[dict[str, Any]] = []
        for _, fields in records:
            encoded = fields.get("event")
            if not isinstance(encoded, str):
                continue
            try:
                event = json.loads(encoded)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or (case_id is not None and event.get("case_id") != case_id):
                continue
            events.append(event)
        return events

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
        if self._shared_state is not None:
            encoded = await self._shared_state.client.get(f"{self._receipt_key_prefix}{idempotency_key}")
            if not isinstance(encoded, str):
                return None
            try:
                receipt = json.loads(encoded)
            except json.JSONDecodeError:
                return None
            return receipt if isinstance(receipt, dict) else None
        async with self._lock:
            return self._idempotency.get(idempotency_key)

    async def save_receipt(self, idempotency_key: str, receipt: dict[str, Any]) -> None:
        if self._shared_state is not None:
            await self._shared_state.client.set(
                f"{self._receipt_key_prefix}{idempotency_key}",
                json.dumps(receipt, ensure_ascii=False, separators=(",", ":"), default=_json_default),
            )
            return
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
        encoded = json.dumps(
            event,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        ) + "\n"
        if self._shared_state is not None:
            await self._shared_state.client.xadd(self._event_stream_key, {"event": encoded.rstrip("\n")})
            return event_id, recorded_at
        async with self._lock:
            self._events.setdefault(case_id, []).append(event)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            _append(self._path, encoded)
        return event_id, recorded_at

    async def list_events(self, case_id: str) -> list[dict[str, Any]]:
        if self._shared_state is not None:
            return await self._shared_events(case_id)
        async with self._lock:
            return [*self._events.get(case_id, [])]

    async def metrics(self) -> dict[str, int]:
        if self._shared_state is not None:
            all_events = [
                event for event in await self._shared_events() if event.get("case_id") != "__bridge_health__"
            ]
            case_ids = {str(event["case_id"]) for event in all_events if isinstance(event.get("case_id"), str)}
            return {
                "case_count": len(case_ids),
                "event_count": len(all_events),
                "submitted_task_count": sum(event.get("event_type") == "omic_task.submitted" for event in all_events),
                "quality_decision_count": sum(event.get("event_type") == "quality.decision" for event in all_events),
                "closed_case_count": sum(event.get("event_type") == "case.closed" for event in all_events),
            }
        async with self._lock:
            all_events = [
                event
                for case_id, events in self._events.items()
                if case_id != "__bridge_health__"
                for event in events
            ]
            return {
                "case_count": sum(case_id != "__bridge_health__" for case_id in self._events),
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

    async def worker_heartbeats(self, workers: set[str]) -> dict[str, datetime | None]:
        """Return the latest inbox-poll event for each Worker identity."""
        if self._shared_state is not None:
            return _worker_heartbeats(await self._shared_events("__bridge_health__"), workers)
        async with self._lock:
            return _worker_heartbeats(self._events.get("__bridge_health__", []), workers)


def _append(path: Path, value: str) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(value)


def _worker_heartbeats(
    events: list[dict[str, Any]], workers: set[str]
) -> dict[str, datetime | None]:
    latest = {worker: None for worker in workers}
    for event in events:
        actor = event.get("actor")
        if actor not in latest or event.get("event_type") != "worker.inbox_polled":
            continue
        try:
            recorded_at = datetime.fromisoformat(str(event["recorded_at"]))
        except (KeyError, TypeError, ValueError):
            continue
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=UTC)
        if latest[actor] is None or recorded_at > latest[actor]:
            latest[actor] = recorded_at
    return latest
