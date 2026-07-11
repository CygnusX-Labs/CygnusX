"""知识库文档主表"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omichub.infrastructure.database.base import Base, TimestampMixin
from omichub.infrastructure.database.models.knowledge_revision import DocRevisionModel


class KbDocumentModel(Base, TimestampMixin):
    """知识库文档主表"""

    __tablename__ = "kb_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # 1=已发布 2=待审核 3=已拒绝
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    current_rev: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doc_revisions.id"), nullable=True
    )
    pending_rev: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doc_revisions.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # 关联关系（仅用于编程便利，不依赖级联删除，避免误删历史）
    current_revision: Mapped[DocRevisionModel | None] = relationship(
        "DocRevisionModel",
        foreign_keys=[current_rev],
        lazy="selectin",
    )
    pending_revision: Mapped[DocRevisionModel | None] = relationship(
        "DocRevisionModel",
        foreign_keys=[pending_rev],
        lazy="selectin",
    )
