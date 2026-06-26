"""MCP 域 ORM 模型 — MCP Server 注册表"""

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from omichub.infrastructure.database.base import Base, TimestampMixin


class MCPServerModel(Base, TimestampMixin):
    """MCP Server 注册表"""

    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    transport: Mapped[str] = mapped_column(String(20), default="builtin")
    command: Mapped[str] = mapped_column(String(500), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    env: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="offline", index=True)
    tools: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    timeout: Mapped[int] = mapped_column(Integer, default=30)
    auto_restart: Mapped[bool] = mapped_column(Boolean, default=True)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)
