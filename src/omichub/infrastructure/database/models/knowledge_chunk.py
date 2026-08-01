"""知识库文档语义块表（chunk）

将文档正文按 Markdown 标题层级切分为语义块，
每块携带 embedding 向量，用于混合检索（向量 + 关键词）。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from omichub.infrastructure.database.base import Base, TimestampMixin

# pgvector 维度在迁移中硬编码（默认 1024，bge-m3）；
# ORM 层用 Text 占位避免 import 时依赖 pgvector 包（运行时由迁移建列）。
# 实际向量读写走 knowledge_indexer / studio_tools 中的原生 SQL。


class KbChunkModel(Base, TimestampMixin):
    """知识库文档语义块"""

    __tablename__ = "kb_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_kb_chunks_doc_index"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        # FK 在迁移中声明（ON DELETE CASCADE）
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default=""
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    # embedding 列由迁移以 vector(1024) 类型创建；
    # ORM 层不映射该列，通过原生 SQL 读写，避免对 pgvector 包的硬依赖。
    # 若需在 ORM 层使用，可安装 pgvector 后取消注释：
    # from pgvector.sqlalchemy import Vector
    # embedding = mapped_column(Vector(1024), nullable=True)
