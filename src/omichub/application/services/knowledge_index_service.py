"""Chunk and embed published knowledge-base documents for pgvector retrieval."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.core.config import get_settings
from omichub.infrastructure.database.models.knowledge_chunk import (
    EMBEDDING_DIMENSIONS,
    KbChunkModel,
)
from omichub.infrastructure.database.models.knowledge_document import KbDocumentModel

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_MAX_CHUNK_CHARS = 1800


class KnowledgeIndexService:
    """Keeps ``kb_chunks`` aligned with each published document revision."""

    def __init__(self, db: AsyncSession, embedding_client: Any | None = None) -> None:
        self._db = db
        self._embedding_client = embedding_client

    async def index_document(self, document: KbDocumentModel, content: str) -> int:
        """Replace a document's chunks atomically in the caller transaction."""
        await self._db.execute(
            delete(KbChunkModel).where(KbChunkModel.document_id == document.doc_id)
        )
        model = get_settings().agent_memory_embedding_model.strip()
        chunks = self._split(content)
        for chunk_index, (section_path, chunk_content) in enumerate(chunks):
            embedding = await self._embed(chunk_content, model) if model else None
            self._db.add(
                KbChunkModel(
                    document_id=document.doc_id,
                    chunk_index=chunk_index,
                    section_path=section_path,
                    content=chunk_content,
                    content_hash=hashlib.md5(chunk_content.encode("utf-8")).hexdigest(),
                    embedding=embedding,
                    embedding_model=model or None,
                )
            )
        await self._db.flush()
        return len(chunks)

    @staticmethod
    def _split(content: str) -> list[tuple[str, str]]:
        sections: list[tuple[str, str]] = []
        headings = list(_HEADING.finditer(content))
        if not headings:
            headings = []
        for index, heading in enumerate(headings):
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
            body = content[start:end].strip()
            if body:
                sections.append((heading.group(2).strip(), body))
        if not sections and content.strip():
            sections.append(("", content.strip()))

        chunks: list[tuple[str, str]] = []
        for section_path, body in sections:
            for offset in range(0, len(body), _MAX_CHUNK_CHARS):
                chunk = body[offset : offset + _MAX_CHUNK_CHARS].strip()
                if chunk:
                    chunks.append((section_path, chunk))
        return chunks

    async def _embed(self, content: str, model: str) -> list[float] | None:
        try:
            if self._embedding_client is None:
                from omichub.infrastructure.ai_provider.litellm_provider import LiteLLMProvider

                self._embedding_client = LiteLLMProvider()
            values = await self._embedding_client.embeddings(content, model=model)
            embedding = [float(value) for value in values] if values else None
            if embedding is not None and len(embedding) != EMBEDDING_DIMENSIONS:
                logger.warning(
                    "知识库向量维度不匹配，期望 {}、实际 {}，回退关键词检索",
                    EMBEDDING_DIMENSIONS,
                    len(embedding),
                )
                return None
            return embedding
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识库分块向量生成失败，保留关键词检索: {}", exc)
            return None
