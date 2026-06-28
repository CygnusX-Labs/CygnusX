"""MCP DTO"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from omichub.application.schemas.base import OmicsHubBaseSchema


class MCPToolDTO(OmicsHubBaseSchema):
    """MCP 工具描述"""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = {}


class MCPServerDTO(OmicsHubBaseSchema):
    """MCP Server"""

    id: UUID
    name: str
    description: str = ""
    transport: str = "builtin"
    command: str = ""
    url: str = ""
    status: str = "offline"
    timeout: int = 30
    auto_restart: bool = True
    is_preset: bool = False
    tool_count: int = 0
    created_at: datetime | None = None


class CreateMCPServerDTO(OmicsHubBaseSchema):
    """注册外部 MCP Server"""

    name: str
    description: str = ""
    transport: str = "stdio"  # stdio | sse
    command: str = ""
    url: str = ""
    env: dict[str, str] = {}
    timeout: int = 30
    auto_restart: bool = True


class UpdateMCPServerDTO(OmicsHubBaseSchema):
    """更新 MCP Server"""

    name: str | None = None
    description: str | None = None
    command: str | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    timeout: int | None = None
    auto_restart: bool | None = None


class InvokeToolDTO(OmicsHubBaseSchema):
    """工具调用请求"""

    tool_name: str
    arguments: dict[str, Any] = {}
