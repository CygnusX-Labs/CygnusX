"""Bounded lexical residual hints and owner-authorized user action telemetry."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.agent_memory import MemoryResidualHintDTO
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import BusinessError, NotFoundError
from cygnusx.core.telemetry import get_meter
from cygnusx.infrastructure.database.models.agent_memory import MemoryBlockModel, MemoryFactModel

_meter = get_meter("cygnusx.memory")
_hits = _meter.create_counter("memory.forget_residual_hits", description="返回用户的词面残留提示数")
_actions = _meter.create_counter(
    "memory.forget_residual_actions", description="用户报告的残留清理点击数"
)


def _excerpt(content: str, terms: list[str]) -> str:
    # Return a small context around the earliest hit, never an entire arbitrary block.
    from cygnusx.application.services.agent_memory_service import _SENSITIVE_PATTERN

    if _SENSITIVE_PATTERN.search(content):
        return "[可能包含敏感凭据，摘录已隐藏]"
    normalized = " ".join(content.split())
    positions = [normalized.lower().find(term) for term in terms if term in normalized.lower()]
    start = max(0, min(positions, default=0) - 15)
    return normalized[start : start + 60]


class MemoryResidualService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def scan(
        self,
        source: MemoryFactModel,
        *,
        agent_id: str,
        project_id: str | None,
    ) -> tuple[list[MemoryResidualHintDTO], bool]:
        from cygnusx.application.services.agent_memory_service import AgentMemoryService

        terms = list(
            dict.fromkeys(
                [
                    source.content.strip().lower(),
                    *(value.strip().lower() for value in (source.keywords or [])),
                    *AgentMemoryService._query_terms(source.content),
                ]
            )
        )
        terms = [term for term in terms if len(term) >= 2][:8]
        if not terms:
            return [], False
        limit = get_settings().memory_forget_residual_limit
        # Personal blocks are shared; focus uses exactly the currently visible partition.
        focus_project = AgentMemoryService.focus_project_id(project_id)
        blocks = list(
            (
                await self.db.scalars(
                    select(MemoryBlockModel)
                    .where(
                        MemoryBlockModel.user_id == source.user_id,
                        MemoryBlockModel.status == "active",
                        or_(
                            (MemoryBlockModel.agent_id == "")
                            & MemoryBlockModel.block_name.in_(["profile", "preferences"])
                            & MemoryBlockModel.project_id.is_(None),
                            (MemoryBlockModel.agent_id == agent_id)
                            & (MemoryBlockModel.agent_id != "")
                            & (MemoryBlockModel.block_name == "current_focus")
                            & (MemoryBlockModel.project_id == focus_project),
                        ),
                        or_(
                            *(
                                MemoryBlockModel.content.icontains(term, autoescape=True)
                                for term in terms
                            )
                        ),
                    )
                    .order_by(MemoryBlockModel.id)
                    .limit(limit + 1)
                )
            ).all()
        )
        facts = list(
            (
                await self.db.scalars(
                    select(MemoryFactModel)
                    .where(
                        MemoryFactModel.user_id == source.user_id,
                        MemoryFactModel.status == "active",
                        MemoryFactModel.id != source.id,
                        or_(
                            (MemoryFactModel.agent_id == "")
                            & MemoryFactModel.scope.in_(["profile", "preference"])
                            & MemoryFactModel.project_id.is_(None),
                            (MemoryFactModel.agent_id == agent_id)
                            & (MemoryFactModel.agent_id != "")
                            & MemoryFactModel.scope.in_(["project", "summary"])
                            & or_(
                                MemoryFactModel.project_id.is_(None),
                                MemoryFactModel.project_id == project_id,
                            ),
                            (MemoryFactModel.agent_id == agent_id)
                            & (MemoryFactModel.agent_id != "")
                            & (MemoryFactModel.scope == "episode")
                            & (MemoryFactModel.project_id == project_id),
                        ),
                        or_(
                            *(
                                or_(
                                    MemoryFactModel.content.icontains(term, autoescape=True),
                                    cast(MemoryFactModel.keywords, String).icontains(
                                        term, autoescape=True
                                    ),
                                )
                                for term in terms
                            )
                        ),
                    )
                    .order_by(MemoryFactModel.id)
                    .limit(limit + 1)
                )
            ).all()
        )
        hints = [
            MemoryResidualHintDTO(
                kind="block",
                id=block.id,
                excerpt=_excerpt(block.content, terms),
                agent_id=block.agent_id,
                project_id=block.project_id,
                block_name=block.block_name,
            )
            for block in blocks
        ]
        hints.extend(
            MemoryResidualHintDTO(
                kind="episode" if fact.scope == "episode" else "fact",
                id=fact.id,
                excerpt=_excerpt(fact.content, terms),
                agent_id=fact.agent_id,
                project_id=fact.project_id,
            )
            for fact in facts
        )
        truncated = len(hints) > limit
        hints = hints[:limit]
        for hint in hints:
            _hits.add(1, {"kind": hint.kind})
        return hints, truncated

    async def record_action(
        self,
        user_id: str,
        *,
        source_id: int,
        target_id: int,
        kind: Literal["block", "fact", "episode"],
        action: Literal["open_editor", "archive"],
    ) -> None:
        """Click telemetry is client-reported; it never authorizes a data mutation."""
        if not get_settings().memory_forget_residual_scan_enabled:
            raise BusinessError("残留检查未开启")
        if (kind == "block") != (action == "open_editor"):
            raise BusinessError("无效的残留处理动作")
        source = await self.db.scalar(
            select(MemoryFactModel.id).where(
                MemoryFactModel.id == source_id,
                MemoryFactModel.user_id == user_id,
                MemoryFactModel.status == "archived",
            )
        )
        if source is None:
            raise NotFoundError("原记忆不存在或未归档")
        if kind == "block":
            target = await self.db.scalar(
                select(MemoryBlockModel.id).where(
                    MemoryBlockModel.id == target_id,
                    MemoryBlockModel.user_id == user_id,
                    MemoryBlockModel.status == "active",
                )
            )
        else:
            target = await self.db.scalar(
                select(MemoryFactModel.id).where(
                    MemoryFactModel.id == target_id,
                    MemoryFactModel.user_id == user_id,
                    MemoryFactModel.status == "active",
                    MemoryFactModel.id != source_id,
                    (MemoryFactModel.scope == "episode")
                    if kind == "episode"
                    else (MemoryFactModel.scope != "episode"),
                )
            )
        if target is None:
            raise NotFoundError("残留候选已不可用")
        _actions.add(1, {"kind": kind, "action": action})
