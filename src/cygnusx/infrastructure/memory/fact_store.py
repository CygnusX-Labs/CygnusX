"""FactStore abstraction for the v2 memory facts.

The application depends on ``FactStore`` so the persistence backend can be
replaced without changing memory assembly or extraction code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Protocol

from sqlalchemy import Float, String, case, cast, literal, or_, true, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import select
from sqlalchemy.sql.elements import ColumnElement

from cygnusx.infrastructure.database.models.agent_memory import MemoryFactModel


@dataclass(slots=True)
class MemoryFactCreate:
    user_id: str
    agent_id: str
    scope: str
    content: str
    keywords: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    embedding_model: str | None = None
    source_session_id: str | None = None
    source_message_ids: list[str] = field(default_factory=list)
    confidence: float = 0.8
    content_hash: str | None = None
    project_id: str | None = None
    importance: int = 5


@dataclass(slots=True)
class MemoryFact:
    id: int
    user_id: str
    agent_id: str
    scope: str
    content: str
    keywords: list[str] | None
    embedding: list[float] | None
    embedding_model: str | None
    source_session_id: str | None
    source_message_ids: list[str] | None
    confidence: float
    status: str
    created_at: datetime
    last_recalled_at: datetime | None
    similarity: float | None = None
    project_id: str | None = None
    importance: int = 5
    recall_count: int = 0


class FactStore(Protocol):
    async def insert(
        self, fact: MemoryFactCreate, *, allow_recreate: bool = False
    ) -> MemoryFact: ...

    async def search(
        self,
        user_id: str,
        agent_id: str,
        query_vector: list[float],
        limit: int = 10,
        *,
        project_id: str | None = None,
        embedding_model: str | None = None,
    ) -> list[MemoryFact]: ...

    async def search_keywords(
        self,
        user_id: str,
        agent_id: str,
        terms: list[str],
        limit: int = 10,
        *,
        project_id: str | None = None,
        incompatible_model: str | None = None,
    ) -> list[MemoryFact]: ...

    async def hybrid_candidates(
        self,
        user_id: str,
        agent_id: str,
        query_vector: list[float],
        terms: list[str],
        *,
        embedding_model: str,
        min_similarity: float,
        vector_limit: int = 20,
        keyword_limit: int = 20,
        project_id: str | None = None,
    ) -> tuple[list[MemoryFact], list[MemoryFact]]: ...

    async def supersede(self, old_id: int, new_fact: MemoryFactCreate) -> MemoryFact: ...

    async def recent_episodes(
        self, user_id: str, agent_id: str, *, project_id: str | None = None
    ) -> list[MemoryFact]: ...

    async def settlement_candidates(
        self,
        user_id: str,
        agent_id: str,
        *,
        project_id: str | None = None,
        limit: int = 30,
        scope: str | None = None,
    ) -> list[MemoryFact]: ...

    async def archive(self, fact_id: int) -> None: ...

    async def touch_recalled(self, fact_ids: list[int], *, user_id: str) -> None: ...


class PostgresFactStore:
    """Postgres/pgvector implementation of ``FactStore``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, fact: MemoryFactCreate, *, allow_recreate: bool = False) -> MemoryFact:
        if fact.scope in {"project", "summary"} and not fact.agent_id:
            from cygnusx.core.exceptions import BusinessError

            raise BusinessError("项目或摘要记忆需要当前 Agent 上下文")
        project_id = None if fact.scope in {"profile", "preference"} else fact.project_id
        agent_id = "" if fact.scope in {"profile", "preference"} else fact.agent_id
        hash_content = f"{project_id}\0{fact.content}" if project_id else fact.content
        if fact.scope == "episode":
            hash_content = f"episode:{fact.source_session_id}\0{hash_content}"
        content_hash = _content_hash(hash_content)
        existing = await self._session.scalar(
            select(MemoryFactModel).where(
                MemoryFactModel.user_id == fact.user_id,
                MemoryFactModel.agent_id == agent_id,
                MemoryFactModel.content_hash == content_hash,
            )
        )
        if existing is not None:
            if existing.status == "active" or not allow_recreate:
                return _to_fact(existing)
            # Keep the inactive row and its superseded links immutable. Retire
            # only its deduplication slot, then create a fresh active version.
            retired = await self._session.scalar(
                update(MemoryFactModel)
                .where(
                    MemoryFactModel.id == existing.id,
                    MemoryFactModel.user_id == fact.user_id,
                    MemoryFactModel.agent_id == agent_id,
                    MemoryFactModel.project_id == project_id,
                    MemoryFactModel.content_hash == content_hash,
                    MemoryFactModel.status == existing.status,
                )
                .values(content_hash=_content_hash(f"historical:{existing.id}\0{content_hash}"))
                .returning(MemoryFactModel.id)
            )
            if retired is None:
                from cygnusx.core.exceptions import BusinessError

                raise BusinessError("记忆状态已变化，请重试保存")
        # Unknown-model vectors are not reusable; retain the fact as lexical memory.
        embedding_model = (fact.embedding_model or "").strip() or None
        embedding = fact.embedding if embedding_model and fact.embedding else None
        model = MemoryFactModel(
            user_id=fact.user_id,
            agent_id=agent_id,
            project_id=project_id,
            scope=fact.scope,
            content=fact.content,
            content_hash=content_hash,
            keywords=fact.keywords,
            embedding=embedding,
            embedding_model=embedding_model if embedding else None,
            source_session_id=fact.source_session_id,
            source_message_ids=fact.source_message_ids,
            confidence=fact.confidence,
            importance=fact.importance,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_fact(model)

    async def search(
        self,
        user_id: str,
        agent_id: str,
        query_vector: list[float],
        limit: int = 10,
        *,
        project_id: str | None = None,
        embedding_model: str | None = None,
    ) -> list[MemoryFact]:
        if embedding_model is not None and not embedding_model.strip():
            return []
        model_filter = (
            MemoryFactModel.embedding_model == embedding_model.strip()
            if embedding_model is not None
            else true()
        )
        distance = MemoryFactModel.embedding.cosine_distance(query_vector)
        rows = await self._session.execute(
            select(MemoryFactModel, distance.label("distance"))
            .where(
                MemoryFactModel.user_id == user_id,
                MemoryFactModel.agent_id == agent_id,
                MemoryFactModel.scope.in_(["profile", "preference"]) if not agent_id else true(),
                MemoryFactModel.status == "active",
                or_(MemoryFactModel.project_id.is_(None), MemoryFactModel.project_id == project_id),
                MemoryFactModel.embedding.is_not(None),
                model_filter,
            )
            .order_by(distance)
            .limit(max(1, min(limit, 100)))
        )
        return [
            _to_fact(model, similarity=1 - float(distance_value)) for model, distance_value in rows
        ]

    async def search_keywords(
        self,
        user_id: str,
        agent_id: str,
        terms: list[str],
        limit: int = 10,
        *,
        project_id: str | None = None,
        incompatible_model: str | None = None,
    ) -> list[MemoryFact]:
        """Recall active facts even when no embedding is available."""
        terms = list(dict.fromkeys(term.lower() for term in terms if term.strip()))[:8]
        if not terms:
            return []
        predicates = [
            or_(
                MemoryFactModel.content.icontains(term, autoescape=True),
                cast(MemoryFactModel.keywords, String).icontains(term, autoescape=True),
            )
            for term in terms
        ]
        rows = list(
            (
                await self._session.scalars(
                    select(MemoryFactModel)
                    .where(
                        MemoryFactModel.user_id == user_id,
                        MemoryFactModel.agent_id == agent_id,
                        MemoryFactModel.scope.in_(["profile", "preference"])
                        if not agent_id
                        else true(),
                        MemoryFactModel.status == "active",
                        or_(
                            MemoryFactModel.project_id.is_(None),
                            MemoryFactModel.project_id == project_id,
                        ),
                        or_(*predicates),
                        or_(
                            MemoryFactModel.embedding.is_(None),
                            MemoryFactModel.embedding_model.is_distinct_from(incompatible_model),
                        )
                        if incompatible_model is not None
                        else true(),
                    )
                    .order_by(MemoryFactModel.created_at.desc(), MemoryFactModel.id.desc())
                    .limit(max(1, min(limit, 100)))
                )
            ).all()
        )
        facts = [
            _to_fact(
                model,
                similarity=sum(
                    term in model.content.lower()
                    or any(term in keyword.lower() for keyword in (model.keywords or []))
                    for term in terms
                )
                / len(terms),
            )
            for model in rows
        ]
        return sorted(facts, key=lambda fact: fact.similarity or 0.0, reverse=True)

    async def hybrid_candidates(
        self,
        user_id: str,
        agent_id: str,
        query_vector: list[float],
        terms: list[str],
        *,
        embedding_model: str,
        min_similarity: float,
        vector_limit: int = 20,
        keyword_limit: int = 20,
        project_id: str | None = None,
    ) -> tuple[list[MemoryFact], list[MemoryFact]]:
        """Fetch independently bounded lanes in one SQL statement/transaction snapshot.

        AsyncSession must not execute concurrent commands on its connection. A UNION
        keeps both lanes independent without creating a separate, stale transaction.
        """
        if not query_vector or not embedding_model.strip():
            return [], await self.search_keywords(
                user_id, agent_id, terms, limit=keyword_limit, project_id=project_id
            )
        if not isfinite(min_similarity) or not -1 <= min_similarity <= 1:
            raise ValueError("Invalid vector similarity floor")
        terms = list(dict.fromkeys(term.lower() for term in terms if term.strip()))[:8]
        boundary = (
            MemoryFactModel.user_id == user_id,
            MemoryFactModel.agent_id == agent_id,
            MemoryFactModel.status == "active",
            MemoryFactModel.scope.in_(["profile", "preference"]) if not agent_id else true(),
            or_(MemoryFactModel.project_id.is_(None), MemoryFactModel.project_id == project_id),
        )
        distance = MemoryFactModel.embedding.cosine_distance(query_vector)
        vectors = (
            select(MemoryFactModel.id, distance.label("distance"))
            .where(
                *boundary,
                MemoryFactModel.embedding.is_not(None),
                MemoryFactModel.embedding_model == embedding_model.strip(),
                distance <= 1 - min_similarity,
            )
            .order_by(distance, MemoryFactModel.id)
            .limit(max(1, min(vector_limit, 100)))
            .subquery()
        )
        vector_lane = select(
            MemoryFactModel,
            literal("vector").label("lane"),
            (1 - vectors.c.distance).label("relevance"),
        ).join(vectors, vectors.c.id == MemoryFactModel.id)
        if terms:
            predicates = [
                or_(
                    MemoryFactModel.content.icontains(term, autoescape=True),
                    cast(MemoryFactModel.keywords, String).icontains(term, autoescape=True),
                )
                for term in terms
            ]
            score: ColumnElement[int] = literal(0)
            for predicate in predicates:
                score = score + case((predicate, 1), else_=0)
            keywords = (
                select(MemoryFactModel.id, score.label("matches"))
                .where(
                    *boundary,
                    or_(*predicates),
                )
                .order_by(
                    score.desc(), MemoryFactModel.created_at.desc(), MemoryFactModel.id.desc()
                )
                .limit(max(1, min(keyword_limit, 100)))
                .subquery()
            )
            keyword_lane = select(
                MemoryFactModel,
                literal("keyword").label("lane"),
                (cast(keywords.c.matches, Float) / len(terms)).label("relevance"),
            ).join(keywords, keywords.c.id == MemoryFactModel.id)
            combined = union_all(vector_lane, keyword_lane).subquery()
        else:
            combined = vector_lane.subquery()
        entity = aliased(MemoryFactModel, combined)
        rows = (
            await self._session.execute(select(entity, combined.c.lane, combined.c.relevance))
        ).all()
        vector_facts: list[MemoryFact] = []
        keyword_facts: list[MemoryFact] = []
        for model, lane, relevance in rows:
            fact = _to_fact(model, similarity=float(relevance))
            (vector_facts if lane == "vector" else keyword_facts).append(fact)
        vector_facts.sort(key=lambda fact: (-(fact.similarity or 0), fact.id))

        def keyword_order(fact: MemoryFact) -> tuple[float, float, int]:
            created = fact.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            return fact.similarity or 0, created.timestamp(), fact.id

        keyword_facts.sort(key=keyword_order, reverse=True)
        return vector_facts, keyword_facts

    async def settlement_candidates(
        self,
        user_id: str,
        agent_id: str,
        *,
        project_id: str | None = None,
        limit: int = 30,
        scope: str | None = None,
    ) -> list[MemoryFact]:
        statement = select(MemoryFactModel).where(
            MemoryFactModel.user_id == user_id,
            MemoryFactModel.status == "active",
            or_(
                (MemoryFactModel.agent_id == "")
                & MemoryFactModel.scope.in_(["profile", "preference"])
                & MemoryFactModel.project_id.is_(None),
                (MemoryFactModel.agent_id == agent_id)
                & MemoryFactModel.scope.in_(["project", "summary"])
                & (MemoryFactModel.project_id == project_id),
            ),
        )
        if scope is not None:
            statement = statement.where(MemoryFactModel.scope == scope)
        rows = (
            await self._session.scalars(
                statement.order_by(
                    MemoryFactModel.created_at.desc(), MemoryFactModel.id.desc()
                ).limit(max(1, min(limit, 100)))
            )
        ).all()
        return [_to_fact(row) for row in rows]

    async def recent_episodes(
        self, user_id: str, agent_id: str, *, project_id: str | None = None
    ) -> list[MemoryFact]:
        rows = (
            await self._session.scalars(
                select(MemoryFactModel)
                .where(
                    MemoryFactModel.user_id == user_id,
                    MemoryFactModel.agent_id == agent_id,
                    MemoryFactModel.status == "active",
                    MemoryFactModel.scope == "episode",
                    MemoryFactModel.project_id == project_id,
                )
                .order_by(MemoryFactModel.created_at.desc(), MemoryFactModel.id.desc())
                .limit(1)
            )
        ).all()
        return [_to_fact(row) for row in rows]

    async def supersede(self, old_id: int, new_fact: MemoryFactCreate) -> MemoryFact:
        replacement = await self.insert(new_fact)
        if replacement.status != "active":
            raise ValueError("Replacement fact is not active")
        if replacement.id == old_id:
            return replacement
        changed = await self._session.scalar(
            update(MemoryFactModel)
            .where(
                MemoryFactModel.id == old_id,
                MemoryFactModel.user_id == new_fact.user_id,
                MemoryFactModel.agent_id == replacement.agent_id,
                MemoryFactModel.project_id == replacement.project_id,
                MemoryFactModel.scope == new_fact.scope,
                MemoryFactModel.status == "active",
            )
            .values(status="superseded", superseded_by=replacement.id)
            .returning(MemoryFactModel.id)
        )
        if changed is None:
            raise ValueError("Replacement target changed or is outside the memory partition")
        return replacement

    async def archive(self, fact_id: int) -> None:
        await self._session.execute(
            update(MemoryFactModel).where(MemoryFactModel.id == fact_id).values(status="archived")
        )

    async def touch_recalled(self, fact_ids: list[int], *, user_id: str) -> None:
        if fact_ids:
            await self._session.execute(
                update(MemoryFactModel)
                .where(
                    MemoryFactModel.id.in_(set(fact_ids)),
                    MemoryFactModel.user_id == user_id,
                    MemoryFactModel.status == "active",
                )
                .values(
                    last_recalled_at=datetime.now(UTC),
                    recall_count=MemoryFactModel.recall_count + 1,
                )
            )


def _content_hash(content: str) -> str:
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _to_fact(model: MemoryFactModel, *, similarity: float | None = None) -> MemoryFact:
    return MemoryFact(
        id=model.id,
        user_id=model.user_id,
        agent_id=model.agent_id,
        scope=model.scope,
        content=model.content,
        keywords=model.keywords,
        embedding=model.embedding,
        embedding_model=model.embedding_model,
        source_session_id=model.source_session_id,
        source_message_ids=model.source_message_ids,
        confidence=model.confidence,
        status=model.status,
        created_at=model.created_at,
        last_recalled_at=model.last_recalled_at,
        project_id=model.project_id,
        importance=model.importance,
        recall_count=model.recall_count,
        similarity=similarity,
    )
