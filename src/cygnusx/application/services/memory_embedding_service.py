"""Operator-only bounded embedding maintenance with model-paired conditional writes."""

from __future__ import annotations

import time
from typing import Any, Literal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.core.config import get_settings
from cygnusx.core.telemetry import get_meter
from cygnusx.infrastructure.database.models.agent_memory import AgentMemoryModel, MemoryFactModel

Storage = Literal["facts", "legacy"]
BackfillMode = Literal["missing", "mismatch"]
_meter = get_meter("cygnusx.memory")
_mismatch = _meter.create_gauge(
    "memory.embedding_model_mismatch_rows", description="最近采样 active 行中模型标识不匹配数量"
)
_coverage = _meter.create_gauge(
    "memory.embedding_model_coverage", description="最近采样 active 行中兼容模型且有向量的占比"
)
_sample_time = _meter.create_gauge(
    "memory.embedding_coverage_sample_timestamp_seconds", description="覆盖率采样的 Unix 时间"
)
_outcomes = _meter.create_counter(
    "memory.embedding_backfill_rows", description="有界向量回填行结果"
)


class MemoryEmbeddingService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        storage: Storage = "facts",
        embedding_client: Any = None,
    ) -> None:
        if storage not in {"facts", "legacy"}:
            raise ValueError("Invalid memory storage")
        self.db = db
        self.storage = storage
        self.table = MemoryFactModel if storage == "facts" else AgentMemoryModel
        self.model_name = get_settings().agent_memory_embedding_model.strip()
        self.embedding_service = AgentMemoryService(db, embedding_client)

    async def coverage(self, *, publish: bool = True) -> dict[str, Any]:
        if not self.model_name:
            return {"status": "disabled", "reason": "embedding_model_not_configured"}
        model = self.table
        active = model.status == "active"
        compatible = (model.embedding.is_not(None)) & (model.embedding_model == self.model_name)
        missing = model.embedding.is_(None)
        mismatch = model.embedding_model.is_distinct_from(self.model_name)
        # One statement/snapshot for all counts, including NULL model identifiers.
        counts = (
            (
                await self.db.execute(
                    select(
                        func.count().label("active"),
                        func.count().filter(compatible).label("compatible"),
                        func.count().filter(missing).label("missing"),
                        func.count().filter(mismatch).label("mismatched"),
                        func.count().filter(or_(missing, mismatch)).label("pending"),
                    )
                    .select_from(model)
                    .where(active)
                )
            )
            .mappings()
            .one()
        )
        result = dict(counts)
        ratio = result["compatible"] / result["active"] if result["active"] else 0.0
        report = {
            "status": "collected",
            "storage": self.storage,
            "target_model": self.model_name,
            **result,
            "coverage": ratio,
        }
        if publish:
            self.publish_report(report)
        return report

    def publish_report(self, report: dict[str, Any]) -> None:
        """Publish backfill outcomes only after the owner successfully commits."""
        sample = report.get("after", report.get("before", report))
        if sample.get("status") != "collected":
            return
        _mismatch.set(sample["mismatched"], {"storage": self.storage})
        _coverage.set(sample["coverage"], {"storage": self.storage})
        _sample_time.set(time.time(), {"storage": self.storage})
        if report.get("status") == "completed":
            for outcome in ("updated", "failed", "skipped"):
                if report.get(outcome):
                    _outcomes.add(report[outcome], {"storage": self.storage, "result": outcome})

    async def backfill(
        self,
        limit: int = 100,
        *,
        mode: BackfillMode = "missing",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        if mode not in {"missing", "mismatch"}:
            raise ValueError("Invalid backfill mode")
        if not self.model_name:
            return {"status": "disabled", "updated": 0, "reason": "embedding_model_not_configured"}
        before = await self.coverage(publish=False)
        base: dict[str, Any] = {
            "mode": mode,
            "storage": self.storage,
            "target_model": self.model_name,
            "before": before,
        }
        pending = before["missing"] if mode == "missing" else before["pending"]
        if dry_run:
            return {**base, "status": "dry_run", "pending": pending, "updated": 0}
        table = self.table
        condition: ColumnElement[bool] = table.embedding.is_(None)
        if mode == "mismatch":
            condition = or_(condition, table.embedding_model.is_distinct_from(self.model_name))
        # Capture scalars before external calls, so ORM synchronization cannot erase
        # the optimistic conditions used to detect concurrent edits/archives/backfills.
        rows = (
            (
                await self.db.execute(
                    select(
                        table.id,
                        table.user_id,
                        table.agent_id,
                        table.project_id,
                        table.content,
                        table.embedding,
                        table.embedding_model,
                    )
                    .where(table.status == "active", condition)
                    .order_by(table.id)
                    .limit(max(1, min(limit, 500)))
                )
            )
            .mappings()
            .all()
        )
        updated = failed = skipped = 0
        prepared: list[tuple[Any, list[float]]] = []
        for row in rows:
            vector = await self.embedding_service._embed(row["content"], model=self.model_name)
            if not vector:
                failed += 1
                continue
            prepared.append((row, vector))
        # Do not hold updated-row locks across subsequent external Provider calls.
        for row, vector in prepared:
            changed = await self.db.scalar(
                update(table)
                .where(
                    table.id == row["id"],
                    table.user_id == row["user_id"],
                    table.agent_id.is_not_distinct_from(row["agent_id"]),
                    table.project_id.is_not_distinct_from(row["project_id"]),
                    table.status == "active",
                    table.content == row["content"],
                    table.embedding_model.is_not_distinct_from(row["embedding_model"]),
                    table.embedding.is_(None)
                    if row["embedding"] is None
                    else table.embedding == row["embedding"],
                )
                .values(embedding=vector, embedding_model=self.model_name)
                .returning(table.id)
                .execution_options(synchronize_session=False)
            )
            if changed is None:
                skipped += 1
            else:
                updated += 1
        after = await self.coverage(publish=False)
        # Transaction ownership stays with the task/CLI caller.
        return {
            **base,
            "status": "completed",
            "updated": updated,
            "failed": failed,
            "skipped": skipped,
            "scanned": len(rows),
            "after": after,
        }
