"""用户域 ORM 模型"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from omichub.infrastructure.database.base import Base, TimestampMixin


class UserModel(Base, TimestampMixin):
    """用户表"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="user")  # admin / user
    status: Mapped[str] = mapped_column(String(20), default="active")
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ===== 存储配额（按用户隔离）=====
    # 默认 500 GiB；管理员可经 PUT /admin/users/{id}/quota 动态调配
    storage_quota: Mapped[int] = mapped_column(BigInteger, default=500 * 1024 * 1024 * 1024)
    used_storage: Mapped[int] = mapped_column(BigInteger, default=0)
    # ===== 管理员备注 =====
    # 供管理员记录辅助信息（如"客户要求延期""测试账号"），不对外暴露给用户
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # ===== 所属课题组 =====
    # 用户归属的研究组/实验室，用于资产看板分组与检索；可空
    lab_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)


class WorkspaceModel(Base, TimestampMixin):
    """工作空间表"""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(200))
    storage_quota: Mapped[int] = mapped_column(default=10 * 1024 * 1024 * 1024)
    used_storage: Mapped[int] = mapped_column(default=0)
