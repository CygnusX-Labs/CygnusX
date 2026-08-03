"""Agent 跨会话长期记忆服务。"""

from __future__ import annotations

import inspect
import json
import math
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.core.config import get_settings
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.infrastructure.database.models.agent_memory import (
    EMBEDDING_DIMENSIONS,
    AgentMemoryModel,
)

MEMORY_SCOPES = {"profile", "project", "preference", "summary"}
_MAX_MEMORIES_PER_USER = 500
_MAX_CONTENT_LENGTH = 200
_MAX_KEYWORDS = 8
_SENSITIVE_PATTERN = re.compile(
    r"(?i)(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|passwd|secret|"
    r"bearer\s+[\w.-]+|sk-[\w-]{12,}|AKIA[0-9A-Z]{16})"
)


class AgentMemoryService:
    """管理用户隔离的跨会话记忆与提示词召回。"""

    def __init__(self, db: AsyncSession, embedding_client: Any | None = None) -> None:
        self._db = db
        self._embedding_client = embedding_client

    async def save_memory(
        self,
        *,
        user_id: str,
        content: str,
        scope: str,
        keywords: list[str] | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        source_session: str | None = None,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        normalized_content = self._validate_content(content)
        normalized_scope = self._validate_scope(scope)
        normalized_keywords = self._normalize_keywords(keywords, normalized_content)
        normalized_confidence = self._validate_confidence(confidence)

        existing = await self._find_duplicate(
            user_id=user_id,
            agent_id=agent_id,
            project_id=project_id,
            scope=normalized_scope,
            keywords=normalized_keywords,
        )
        if existing is not None:
            conflict_action = await self._adjudicate_conflict(existing, normalized_content)
            if conflict_action == "discard":
                return {"memory": self._serialize(existing), "action": "discarded"}
            if conflict_action == "coexist":
                existing = None

        if existing is not None:
            existing.content = normalized_content
            existing.keywords = normalized_keywords
            existing.source_session = source_session or existing.source_session
            existing.status = "active"
            existing.confidence = normalized_confidence
            await self._populate_embedding(existing)
            await self._db.flush()
            return {"memory": self._serialize(existing), "action": "updated"}

        await self._archive_excess(user_id)
        memory = AgentMemoryModel(
            user_id=user_id,
            project_id=project_id,
            agent_id=agent_id,
            scope=normalized_scope,
            content=normalized_content,
            keywords=normalized_keywords,
            source_session=source_session,
            confidence=normalized_confidence,
            status="active",
        )
        self._db.add(memory)
        await self._populate_embedding(memory)
        await self._db.flush()
        return {"memory": self._serialize(memory), "action": "created"}

    async def update_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        content: str,
        keywords: list[str] | None = None,
        source_session: str | None = None,
    ) -> dict[str, Any]:
        memory = await self._get_owned_memory(user_id, memory_id)
        memory.content = self._validate_content(content)
        memory.keywords = self._normalize_keywords(keywords, memory.content)
        if source_session:
            memory.source_session = source_session
        memory.status = "active"
        await self._populate_embedding(memory)
        await self._db.flush()
        return {"memory": self._serialize(memory), "action": "updated"}

    async def forget_memory(self, *, user_id: str, memory_id: str, **_kwargs: Any) -> dict[str, Any]:
        memory = await self._get_owned_memory(user_id, memory_id)
        memory.status = "archived"
        await self._db.flush()
        return {"memory_id": str(memory.id), "forgotten": True}

    async def search_memory(
        self,
        *,
        user_id: str,
        query: str,
        scope: str | None = None,
        limit: int = 5,
        agent_id: str | None = None,
        project_id: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        query_terms = self._query_terms(query)
        statement = select(AgentMemoryModel).where(
            AgentMemoryModel.user_id == user_id,
            AgentMemoryModel.status == "active",
            or_(AgentMemoryModel.agent_id.is_(None), AgentMemoryModel.agent_id == agent_id),
            (
                AgentMemoryModel.project_id == project_id
                if project_id
                else AgentMemoryModel.project_id.is_(None)
            ),
        )
        if scope:
            statement = statement.where(AgentMemoryModel.scope == self._validate_scope(scope))
        semantic_enabled = self._semantic_enabled()
        if query_terms and not semantic_enabled:
            statement = statement.where(
                or_(*(AgentMemoryModel.content.ilike(f"%{term}%") for term in query_terms))
            )
        candidate_limit = (
            max(1, min(get_settings().agent_memory_semantic_candidate_limit, 500))
            if semantic_enabled
            else max(1, min(limit, 10))
        )
        statement = statement.order_by(
            AgentMemoryModel.use_count.desc(), AgentMemoryModel.updated_at.desc()
        ).limit(candidate_limit)
        rows = list((await self._db.scalars(statement)).all())
        if semantic_enabled:
            rows = await self._semantic_rank(rows, query, query_terms, limit)
        await self._mark_used(rows)
        return {"memories": [self._serialize(row) for row in rows], "count": len(rows)}

    async def list_memories(
        self,
        user_id: str,
        *,
        agent_id: str | None = None,
        scope: str | None = None,
        project_id: str | None = None,
        status: str = "active",
        include_archived: bool = False,
        limit: int = 100,
    ) -> list[AgentMemoryModel]:
        statement = select(AgentMemoryModel).where(AgentMemoryModel.user_id == user_id)
        if agent_id:
            statement = statement.where(AgentMemoryModel.agent_id == agent_id)
        if scope:
            statement = statement.where(AgentMemoryModel.scope == self._validate_scope(scope))
        if project_id:
            statement = statement.where(AgentMemoryModel.project_id == project_id)
        if status and not include_archived:
            statement = statement.where(AgentMemoryModel.status == status)
        statement = statement.order_by(AgentMemoryModel.updated_at.desc()).limit(max(1, min(limit, 500)))
        return list((await self._db.scalars(statement)).all())

    async def delete_memory(self, user_id: str, memory_id: str) -> None:
        memory = await self._get_owned_memory(user_id, memory_id)
        await self._db.delete(memory)
        await self._db.flush()

    async def clear_memories(self, user_id: str, *, agent_id: str | None = None) -> int:
        memories = await self.list_memories(user_id, agent_id=agent_id, limit=500)
        for memory in memories:
            memory.status = "archived"
        await self._db.flush()
        return len(memories)

    async def build_prompt_context(
        self, user_id: str, agent_id: str, query: str, *, project_id: str | None = None
    ) -> str:
        """构建固定 L1 + 当前 query 触发的 L2 记忆块，最大约 800 tokens。"""
        common = await self._query_active(
            user_id,
            agent_id,
            project_id=project_id,
            scopes={"profile", "preference"},
            limit=10,
        )
        recalled = await self._search_for_prompt(
            user_id, agent_id, query, project_id=project_id, limit=5
        )
        seen = {memory.id for memory in common}
        selected = [*common, *(memory for memory in recalled if memory.id not in seen)]
        if not selected:
            return ""
        await self._mark_used(selected)

        lines: list[str] = []
        budget = 3200
        used = 0
        for memory in selected:
            line = f"- {memory.content.strip()}"
            size = len(line.encode("utf-8"))
            if used + size > budget:
                logger.info("长期记忆注入达到 800 token 预算，已截断 user_id={}", user_id)
                break
            lines.append(line)
            used += size
        if not lines:
            return ""
        return (
            "## 用户记忆（跨会话，可能过时；与当前对话冲突时以当前对话为准）\n"
            + "\n".join(lines)
        )

    async def _query_active(
        self,
        user_id: str,
        agent_id: str,
        *,
        project_id: str | None,
        scopes: set[str],
        limit: int,
    ) -> list[AgentMemoryModel]:
        statement = (
            select(AgentMemoryModel)
            .where(
                AgentMemoryModel.user_id == user_id,
                AgentMemoryModel.status == "active",
                AgentMemoryModel.scope.in_(scopes),
                or_(AgentMemoryModel.agent_id.is_(None), AgentMemoryModel.agent_id == agent_id),
                (
                    AgentMemoryModel.project_id == project_id
                    if project_id
                    else AgentMemoryModel.project_id.is_(None)
                ),
            )
            .order_by(AgentMemoryModel.use_count.desc(), AgentMemoryModel.updated_at.desc())
            .limit(limit)
        )
        return list((await self._db.scalars(statement)).all())

    async def _search_for_prompt(
        self, user_id: str, agent_id: str, query: str, *, project_id: str | None, limit: int
    ) -> list[AgentMemoryModel]:
        terms = self._query_terms(query)
        if not terms:
            return []
        semantic_enabled = self._semantic_enabled()
        statement = select(AgentMemoryModel).where(
            AgentMemoryModel.user_id == user_id,
            AgentMemoryModel.status == "active",
            AgentMemoryModel.scope.in_({"project", "summary"}),
            or_(AgentMemoryModel.agent_id.is_(None), AgentMemoryModel.agent_id == agent_id),
            (
                AgentMemoryModel.project_id == project_id
                if project_id
                else AgentMemoryModel.project_id.is_(None)
            ),
        )
        if not semantic_enabled:
            statement = statement.where(
                or_(*(AgentMemoryModel.content.ilike(f"%{term}%") for term in terms))
            )
        candidate_limit = (
            max(1, min(get_settings().agent_memory_semantic_candidate_limit, 500))
            if semantic_enabled
            else limit
        )
        rows = list(
            (await self._db.scalars(
                statement.order_by(
                    AgentMemoryModel.use_count.desc(), AgentMemoryModel.updated_at.desc()
                ).limit(candidate_limit)
            )).all()
        )
        return await self._semantic_rank(rows, query, terms, limit) if semantic_enabled else rows

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
            sum(value * value for value in right)
        )
        if denominator <= 0:
            return 0.0
        return sum(a * b for a, b in zip(left, right, strict=True)) / denominator

    def _semantic_enabled(self) -> bool:
        settings = get_settings()
        return bool(
            settings.agent_memory_semantic_retrieval_enabled
            and settings.agent_memory_embedding_model.strip()
        )

    async def _populate_embedding(self, memory: AgentMemoryModel) -> None:
        if not self._semantic_enabled():
            return
        embedding = await self._embed(memory.content)
        if embedding:
            memory.embedding = embedding
            memory.embedding_model = get_settings().agent_memory_embedding_model.strip()
        else:
            memory.embedding = None
            memory.embedding_model = None

    async def _semantic_rank(
        self,
        memories: list[AgentMemoryModel],
        query: str,
        query_terms: list[str],
        limit: int,
    ) -> list[AgentMemoryModel]:
        query_embedding = await self._embed(query)
        if not query_embedding:
            return memories[:limit]

        try:
            from sqlalchemy import select

            distance = AgentMemoryModel.embedding.cosine_distance(query_embedding)
            statement = (
                select(AgentMemoryModel)
                .where(AgentMemoryModel.id.in_([memory.id for memory in memories]))
                .where(AgentMemoryModel.embedding.is_not(None))
                .order_by(distance)
                .limit(limit)
            )
            result = await self._db.scalars(statement)
            ranked_values = result.all()
            if inspect.isawaitable(ranked_values):
                ranked_values = await ranked_values
            ranked = list(ranked_values)
            if ranked:
                return ranked
        except Exception as exc:  # noqa: BLE001
            logger.warning("记忆 pgvector 召回失败，回退内存排序: {}", exc)

        def score(memory: AgentMemoryModel) -> tuple[float, int, datetime]:
            embedding = [float(value) for value in (memory.embedding or [])]
            semantic = self._cosine_similarity(query_embedding, embedding)
            lexical = sum(term in memory.content.lower() for term in query_terms) * 0.05
            return semantic + lexical, memory.use_count, memory.updated_at

        return sorted(memories, key=score, reverse=True)[:limit]

    async def _embed(self, text: str) -> list[float]:
        try:
            if self._embedding_client is None:
                from omichub.infrastructure.ai_provider.litellm_provider import LiteLLMProvider

                self._embedding_client = LiteLLMProvider()
            values = await self._embedding_client.embeddings(
                text, model=get_settings().agent_memory_embedding_model.strip()
            )
            embedding = [float(value) for value in values] if values else []
            if embedding and len(embedding) != EMBEDDING_DIMENSIONS:
                logger.warning(
                    "记忆向量维度不匹配，期望 {}、实际 {}，回退关键词召回",
                    EMBEDDING_DIMENSIONS,
                    len(embedding),
                )
                return []
            return embedding
        except Exception as exc:  # noqa: BLE001
            logger.warning("记忆语义向量生成失败，回退关键词召回: {}", exc)
            return []

    async def _adjudicate_conflict(self, existing: AgentMemoryModel, content: str) -> str:
        """在可选模型裁决失败时保持 P1 的“最新值覆盖”规则。"""
        settings = get_settings()
        if not settings.agent_memory_conflict_adjudication_enabled:
            return "update"
        try:
            if self._embedding_client is None:
                from omichub.infrastructure.ai_provider.litellm_provider import LiteLLMProvider

                self._embedding_client = LiteLLMProvider()
            response = await self._embedding_client.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "判断两条用户长期记忆的关系。仅输出 JSON："
                            '{"action":"update|coexist|discard"}。'
                            "新事实修正旧事实用 update；独立事实用 coexist；新内容无价值或重复用 discard。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"旧记忆：{existing.content}\n新记忆：{content}",
                    },
                ],
                model=settings.agent_memory_conflict_adjudication_model.strip(),
                temperature=0,
            )
            return self._parse_conflict_action(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("记忆冲突裁决失败，按最新值覆盖: {}", exc)
            return "update"

    @staticmethod
    def _parse_conflict_action(response: Any) -> str:
        try:
            choices = response.get("choices", []) if isinstance(response, dict) else []
            message = choices[0].get("message", {}) if choices else {}
            content = str(message.get("content", ""))
            match = re.search(r"\{[^{}]*\}", content)
            payload = json.loads(match.group(0) if match else content)
            action = str(payload.get("action", "")).lower()
            return action if action in {"update", "coexist", "discard"} else "update"
        except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            return "update"

    async def _find_duplicate(
        self,
        *,
        user_id: str,
        agent_id: str | None,
        project_id: str | None,
        scope: str,
        keywords: list[str],
    ) -> AgentMemoryModel | None:
        statement = select(AgentMemoryModel).where(
            AgentMemoryModel.user_id == user_id,
            AgentMemoryModel.agent_id.is_(None) if agent_id is None else AgentMemoryModel.agent_id == agent_id,
            (
                AgentMemoryModel.project_id == project_id
                if project_id
                else AgentMemoryModel.project_id.is_(None)
            ),
            AgentMemoryModel.scope == scope,
            AgentMemoryModel.status == "active",
        ).order_by(AgentMemoryModel.updated_at.desc()).limit(30)
        for memory in (await self._db.scalars(statement)).all():
            if set(memory.keywords or []) & set(keywords):
                return memory
        return None

    async def _archive_excess(self, user_id: str) -> None:
        statement = select(AgentMemoryModel).where(
            AgentMemoryModel.user_id == user_id, AgentMemoryModel.status == "active"
        ).order_by(AgentMemoryModel.use_count.asc(), AgentMemoryModel.updated_at.asc())
        memories = list((await self._db.scalars(statement)).all())
        overflow = len(memories) - _MAX_MEMORIES_PER_USER + 1
        for memory in memories[: max(0, overflow)]:
            memory.status = "archived"

    async def _mark_used(self, memories: list[AgentMemoryModel]) -> None:
        if not memories:
            return
        now = datetime.now(UTC)
        for memory in memories:
            memory.use_count += 1
            memory.last_used_at = now
        await self._db.flush()

    async def _get_owned_memory(self, user_id: str, memory_id: str) -> AgentMemoryModel:
        try:
            parsed_id = uuid.UUID(memory_id)
        except ValueError as exc:
            raise NotFoundError("记忆不存在") from exc
        memory = await self._db.scalar(
            select(AgentMemoryModel).where(
                AgentMemoryModel.id == parsed_id, AgentMemoryModel.user_id == user_id
            )
        )
        if memory is None:
            raise NotFoundError("记忆不存在")
        return memory

    @staticmethod
    def _validate_scope(scope: str) -> str:
        normalized = str(scope).strip().lower()
        if normalized not in MEMORY_SCOPES:
            raise BusinessError(f"不支持的记忆范围: {scope}")
        return normalized

    @staticmethod
    def _validate_content(content: str) -> str:
        normalized = str(content).strip()
        if not normalized:
            raise BusinessError("记忆内容不能为空")
        if len(normalized) > _MAX_CONTENT_LENGTH:
            raise BusinessError(f"单条记忆不能超过 {_MAX_CONTENT_LENGTH} 个字符")
        if _SENSITIVE_PATTERN.search(normalized):
            raise BusinessError("禁止将密钥、密码、Token 或其他敏感凭据写入长期记忆")
        return normalized

    @staticmethod
    def _validate_confidence(value: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError) as exc:
            raise BusinessError("记忆置信度必须是 0 到 1 之间的数字") from exc
        if not 0 <= confidence <= 1:
            raise BusinessError("记忆置信度必须在 0 到 1 之间")
        return confidence

    @staticmethod
    def _normalize_keywords(keywords: list[str] | None, content: str) -> list[str]:
        source = keywords or AgentMemoryService._query_terms(content)
        normalized: list[str] = []
        for value in source:
            term = str(value).strip().lower()
            if term and term not in normalized:
                normalized.append(term[:48])
            if len(normalized) >= _MAX_KEYWORDS:
                break
        return normalized

    @staticmethod
    def _query_terms(text: str) -> list[str]:
        terms = re.findall(r"[A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff]{2,}", str(text).lower())
        return list(dict.fromkeys(terms))[:8]

    @staticmethod
    def _serialize(memory: AgentMemoryModel) -> dict[str, Any]:
        return {
            "id": str(memory.id),
            "agent_id": memory.agent_id,
            "project_id": memory.project_id,
            "scope": memory.scope,
            "content": memory.content,
            "keywords": list(memory.keywords or []),
            "source_session": memory.source_session,
            "confidence": memory.confidence,
            "use_count": memory.use_count,
            "last_used_at": memory.last_used_at.isoformat() if memory.last_used_at else None,
            "status": memory.status,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
        }
