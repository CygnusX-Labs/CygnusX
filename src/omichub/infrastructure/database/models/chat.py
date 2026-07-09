"""Cherry Studio 架构聊天系统 ORM 模型

对应 Cherry Studio 的 Topic(Session) + Message + Assistant 三层结构。
会话绑定 ai_provider_configs（复用现有 Provider 配置表，PK 为 UUID）。
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omichub.infrastructure.database.base import Base, TimestampMixin


class ChatSessionModel(Base, TimestampMixin):
    """聊天会话表（对应 Cherry Studio 的 Topic）"""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    assistant_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("chat_assistants.assistant_id"), nullable=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(50), ForeignKey("agent_templates.agent_id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), default="新对话", nullable=False)
    model_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_provider_configs.id"), nullable=False
    )

    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["ChatMessageModel"]] = relationship(
        "ChatMessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessageModel.created_at",
    )

    __table_args__ = (Index("idx_chat_sessions_user_updated", "user_id", "updated_at"),)


class ChatMessageModel(Base):
    """聊天消息表"""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="complete", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ChatSessionModel | None] = relationship(
        "ChatSessionModel", back_populates="messages"
    )

    __table_args__ = (Index("idx_chat_messages_session_created", "session_id", "created_at"),)


class ChatAssistantModel(Base, TimestampMixin):
    """AI 助手表（对应 Cherry Studio 的 Assistant）"""

    __tablename__ = "chat_assistants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assistant_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    default_model_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_provider_configs.id"), nullable=True
    )
    default_temperature: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    default_max_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)

    icon: Mapped[str] = mapped_column(String(10), default="\U0001f916", nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#4f8ef7", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)

    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (Index("idx_chat_assistants_category", "category", "is_active"),)
