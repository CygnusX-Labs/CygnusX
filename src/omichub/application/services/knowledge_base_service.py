"""知识库资源管理服务（AI 配置中心 - 知识库卡片）。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.knowledge_base import (
    KnowledgeBaseCreateDTO,
    KnowledgeBaseDocDTO,
    KnowledgeBaseDTO,
    KnowledgeBaseUpdateDTO,
)
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.infrastructure.database.models.knowledge_base import KnowledgeBaseModel
from omichub.infrastructure.database.models.knowledge_document import KbDocumentModel


class KnowledgeBaseService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _dto(model: KnowledgeBaseModel, doc_count: int) -> KnowledgeBaseDTO:
        return KnowledgeBaseDTO(
            id=model.id,
            name=model.name,
            description=model.description,
            show_in_lab=model.show_in_lab,
            ai_searchable=model.ai_searchable,
            is_enabled=model.is_enabled,
            doc_count=doc_count,
            updated_at=model.updated_at,
        )

    async def list_bases(self) -> list[KnowledgeBaseDTO]:
        counts = dict(
            (
                await self._db.execute(
                    select(KbDocumentModel.kb_id, func.count())
                    .group_by(KbDocumentModel.kb_id)
                )
            ).all()
        )
        result = await self._db.execute(
            select(KnowledgeBaseModel).order_by(KnowledgeBaseModel.created_at)
        )
        return [
            self._dto(model, int(counts.get(model.id) or 0))
            for model in result.scalars().all()
        ]

    async def create_base(self, dto: KnowledgeBaseCreateDTO) -> KnowledgeBaseDTO:
        existing = await self._db.get(KnowledgeBaseModel, dto.id)
        if existing is not None:
            raise BusinessError(f"知识库标识「{dto.id}」已存在")
        model = KnowledgeBaseModel(
            id=dto.id,
            name=dto.name.strip(),
            description=dto.description.strip(),
            show_in_lab=dto.show_in_lab,
            ai_searchable=dto.ai_searchable,
        )
        self._db.add(model)
        await self._db.flush()
        await self._db.refresh(model)
        return self._dto(model, 0)

    async def update_base(self, kb_id: str, dto: KnowledgeBaseUpdateDTO) -> KnowledgeBaseDTO:
        model = await self._db.get(KnowledgeBaseModel, kb_id)
        if model is None:
            raise NotFoundError("知识库不存在")
        model.name = dto.name.strip()
        model.description = dto.description.strip()
        model.show_in_lab = dto.show_in_lab
        model.ai_searchable = dto.ai_searchable
        model.is_enabled = dto.is_enabled
        await self._db.flush()
        await self._db.refresh(model)
        count = (
            await self._db.execute(
                select(func.count()).select_from(KbDocumentModel).where(
                    KbDocumentModel.kb_id == kb_id
                )
            )
        ).scalar_one()
        return self._dto(model, int(count))

    async def delete_base(self, kb_id: str) -> None:
        model = await self._db.get(KnowledgeBaseModel, kb_id)
        if model is None:
            raise NotFoundError("知识库不存在")
        count = (
            await self._db.execute(
                select(func.count()).select_from(KbDocumentModel).where(
                    KbDocumentModel.kb_id == kb_id
                )
            )
        ).scalar_one()
        if count:
            raise BusinessError(f"知识库内仍有 {count} 篇文档，请先迁移或删除文档")
        await self._db.delete(model)
        await self._db.flush()

    async def list_docs(self, kb_id: str) -> list[KnowledgeBaseDocDTO]:
        model = await self._db.get(KnowledgeBaseModel, kb_id)
        if model is None:
            raise NotFoundError("知识库不存在")
        result = await self._db.execute(
            select(KbDocumentModel)
            .where(KbDocumentModel.kb_id == kb_id)
            .order_by(KbDocumentModel.category, KbDocumentModel.title)
            .limit(500)
        )
        return [
            KnowledgeBaseDocDTO(
                doc_id=doc.doc_id,
                title=doc.title,
                category=doc.category,
                status=doc.status,
                updated_at=doc.updated_at,
            )
            for doc in result.scalars().all()
        ]
