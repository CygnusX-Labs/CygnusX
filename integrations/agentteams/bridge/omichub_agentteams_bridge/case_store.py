"""Small Bridge-owned Case state store; it contains references, never raw omics data."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .models import CaseRecord, CaseStatus, PreflightInputSnapshot, WorkItemRecord

_ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    "received": {"preflight_running", "cancelled"},
    "preflight_running": {"preflight_blocked", "approval_pending", "cancelled"},
    "preflight_blocked": {"waiting_for_correction", "cancelled"},
    "waiting_for_correction": {"preflight_running", "cancelled"},
    "approval_pending": {"approved", "cancelled"},
    "approved": {"executing", "cancelled"},
    "executing": {"quality_running", "execution_failed", "cancelled"},
    "execution_failed": {"remediation_pending", "cancelled"},
    "quality_running": {"delivery_ready", "quality_blocked", "remediation_pending", "cancelled"},
    "quality_blocked": {"remediation_pending", "cancelled"},
    "remediation_pending": {"preflight_running", "executing", "quality_running", "cancelled"},
    "delivery_ready": {"closed", "remediation_pending", "cancelled"},
    "closed": set(),
    "cancelled": set(),
}


class CaseStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._cases = self._load()
        self._lock = asyncio.Lock()

    def _load(self) -> dict[str, CaseRecord]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        cases: dict[str, CaseRecord] = {}
        for case_id, payload in raw.items():
            if not isinstance(payload, dict):
                continue
            try:
                cases[str(case_id)] = CaseRecord.model_validate(payload)
            except ValueError:
                continue
        return cases

    async def create(self, case: CaseRecord) -> CaseRecord:
        async with self._lock:
            if case.case_id in self._cases:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Case already exists"
                )
            self._cases[case.case_id] = case
            await self._persist()
            return case

    async def get(self, case_id: str) -> CaseRecord:
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            return case

    async def list(self, requester_ref: str | None = None) -> list[CaseRecord]:
        async with self._lock:
            cases = list(self._cases.values())
            if requester_ref is not None:
                cases = [case for case in cases if case.requester_ref == requester_ref]
            return sorted(cases, key=lambda case: case.updated_at, reverse=True)

    async def list_assigned_work_items(
        self, target: str, statuses: set[str]
    ) -> list[tuple[CaseRecord, WorkItemRecord]]:
        async with self._lock:
            assigned = [
                (case, work_item)
                for case in self._cases.values()
                for work_item in case.work_items
                if work_item.target == target and work_item.status in statuses
            ]
            return sorted(assigned, key=lambda item: item[1].updated_at, reverse=True)

    async def transition(self, case_id: str, target: CaseStatus) -> CaseRecord:
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            if target not in _ALLOWED_TRANSITIONS[case.status]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Invalid Case transition: {case.status} -> {target}",
                )
            updated = case.model_copy(update={"status": target, "updated_at": datetime.now(UTC)})
            self._cases[case_id] = updated
            await self._persist()
            return updated

    async def attach_task(
        self, case_id: str, task_id: str, task_spec: dict[str, Any] | None = None
    ) -> CaseRecord:
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            if task_id not in case.omic_task_ids:
                case = case.model_copy(
                    update={
                        "omic_task_ids": [*case.omic_task_ids, task_id],
                        "task_specs": [*case.task_specs, task_spec]
                        if task_spec
                        else case.task_specs,
                        "updated_at": datetime.now(UTC),
                    }
                )
                self._cases[case_id] = case
                await self._persist()
            return case

    async def save_preflight_input(
        self, case_id: str, snapshot: PreflightInputSnapshot | None
    ) -> CaseRecord:
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            updated = case.model_copy(
                update={"preflight_input": snapshot, "updated_at": datetime.now(UTC)}
            )
            self._cases[case_id] = updated
            await self._persist()
            return updated

    async def add_work_item(self, case_id: str, work_item: WorkItemRecord) -> CaseRecord:
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            if any(item.work_item_id == work_item.work_item_id for item in case.work_items):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Work item already exists"
                )
            if work_item.parent_work_item_id and not any(
                item.work_item_id == work_item.parent_work_item_id for item in case.work_items
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Parent work item not found",
                )
            updated = case.model_copy(
                update={
                    "work_items": [*case.work_items, work_item],
                    "updated_at": datetime.now(UTC),
                }
            )
            self._cases[case_id] = updated
            await self._persist()
            return updated

    async def ensure_work_item(
        self, case_id: str, work_item: WorkItemRecord
    ) -> tuple[WorkItemRecord, bool]:
        """Return an existing work item or add it atomically for reconciliation."""
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            for existing in case.work_items:
                if existing.work_item_id == work_item.work_item_id:
                    return existing, False
            if work_item.parent_work_item_id and not any(
                item.work_item_id == work_item.parent_work_item_id for item in case.work_items
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Parent work item not found",
                )
            updated = case.model_copy(
                update={
                    "work_items": [*case.work_items, work_item],
                    "updated_at": datetime.now(UTC),
                }
            )
            self._cases[case_id] = updated
            await self._persist()
            return work_item, True

    async def update_work_item(
        self, case_id: str, work_item_id: str, work_item: WorkItemRecord
    ) -> CaseRecord:
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            if not any(item.work_item_id == work_item_id for item in case.work_items):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found"
                )
            updated = case.model_copy(
                update={
                    "work_items": [
                        work_item if item.work_item_id == work_item_id else item
                        for item in case.work_items
                    ],
                    "updated_at": datetime.now(UTC),
                }
            )
            self._cases[case_id] = updated
            await self._persist()
            return updated

    async def claim_work_item(self, case_id: str, work_item_id: str, target: str) -> WorkItemRecord:
        """Atomically claim a pending assignment, reclaiming only an expired lease."""
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            work_item = next(
                (item for item in case.work_items if item.work_item_id == work_item_id), None
            )
            if work_item is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found"
                )
            if work_item.target != target:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Work item target mismatch"
                )
            now = datetime.now(UTC)
            lease_expired = (
                work_item.status == "in_progress"
                and (now - work_item.updated_at).total_seconds() >= work_item.deadline_seconds
            )
            if work_item.status != "pending" and not lease_expired:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Work item is already claimed or completed",
                )
            claimed = work_item.model_copy(update={"status": "in_progress", "updated_at": now})
            updated_case = case.model_copy(
                update={
                    "work_items": [
                        claimed if item.work_item_id == work_item_id else item
                        for item in case.work_items
                    ],
                    "updated_at": now,
                }
            )
            self._cases[case_id] = updated_case
            await self._persist()
            return claimed

    async def get_work_item(self, case_id: str, work_item_id: str) -> WorkItemRecord:
        case = await self.get(case_id)
        for item in case.work_items:
            if item.work_item_id == work_item_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found")

    async def get_by_task(self, task_id: str) -> CaseRecord:
        async with self._lock:
            for case in self._cases.values():
                if task_id in case.omic_task_ids:
                    return case
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Task is not linked to a Case"
            )

    async def set_quality(self, case_id: str, decision: str) -> CaseRecord:
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            case = case.model_copy(
                update={"quality_decision": decision, "updated_at": datetime.now(UTC)}
            )
            self._cases[case_id] = case
            await self._persist()
            return case

    async def close(self, case_id: str, manifest_uri: str) -> CaseRecord:
        async with self._lock:
            case = self._cases.get(case_id)
            if case is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
            if case.status != "delivery_ready":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Case is not ready to close"
                )
            updated = case.model_copy(
                update={
                    "status": "closed",
                    "manifest_uri": manifest_uri,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._cases[case_id] = updated
            await self._persist()
            return updated

    async def _persist(self) -> None:
        encoded = json.dumps(
            {case_id: case.model_dump(mode="json") for case_id, case in self._cases.items()},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._path.write_text, encoded, encoding="utf-8")
