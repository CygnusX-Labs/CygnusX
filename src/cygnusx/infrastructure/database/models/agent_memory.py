"""跨会话 Agent 长期记忆 ORM 模型。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from cygnusx.infrastructure.database.base import Base, TimestampMixin
from cygnusx.infrastructure.database.vector import Vector

EMBEDDING_DIMENSIONS = 1024


class AgentMemoryModel(Base, TimestampMixin):
    """用户隔离的、可管理的跨会话记忆（只读归档，v2 不再写入）。"""

    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_session: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)

    __table_args__ = (
        Index("idx_agent_memories_user_agent_status", "user_id", "agent_id", "status"),
        Index("idx_agent_memories_user_scope_status", "user_id", "scope", "status"),
        Index("idx_agent_memories_project_status", "project_id", "status"),
        Index(
            "ix_agent_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
    )


class MemoryBlockModel(Base, TimestampMixin):
    """Agent 策展的常驻记忆块。"""

    __tablename__ = "memory_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    block_name: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    superseded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("memory_blocks.id", name="fk_memory_blocks_superseded_by"), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_memory_blocks_general", "user_id", "agent_id", "block_name", unique=True,
            postgresql_where=text("project_id IS NULL"), sqlite_where=text("project_id IS NULL"),
        ),
        Index(
            "uq_memory_blocks_project", "user_id", "agent_id", "block_name", "project_id",
            unique=True, postgresql_where=text("project_id IS NOT NULL"),
            sqlite_where=text("project_id IS NOT NULL"),
        ),
        Index("idx_memory_blocks_user_agent", "user_id", "agent_id"),
    )


class MemoryFactModel(Base):
    """语义召回事实库；由 FactStore 统一读写。"""

    __tablename__ = "memory_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(String(1200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    keywords: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_session_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_message_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    recall_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    superseded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("memory_facts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    last_recalled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", "content_hash", name="uq_memory_facts_content"),
        Index("idx_memory_facts_user_agent_status", "user_id", "agent_id", "status"),
        Index(
            "idx_memory_facts_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
    )


class MemorySettlementModel(Base):
    """已处理的会话消息区间，保证 settle 重试无副作用。"""

    __tablename__ = "memory_settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    range_key: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    session_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    start_message_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    end_message_id: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class MemoryRecallBatchModel(Base):
    """Idempotency receipt for one asynchronously recorded recall batch."""

    __tablename__ = "memory_recall_batches"
    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )


class MemoryConsolidationBudgetModel(Base):
    """Durable global weekly model-call allowance, including failed calls."""

    __tablename__ = "memory_consolidation_budgets"
    week: Mapped[str] = mapped_column(String(10), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class MemoryConsolidationRunModel(Base):
    """Append-only successful consolidation decisions and source watermark."""

    __tablename__ = "memory_consolidation_runs"
    run_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    week: Mapped[str] = mapped_column(String(10), nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(50), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    watermark: Mapped[int] = mapped_column(Integer, nullable=False)
    decisions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    rolled_back_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
