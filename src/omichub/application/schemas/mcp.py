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
    args: list[str] = []
    url: str = ""
    env: dict[str, str] = {}
    registry: str = "default"
    working_dir: str = ""
    version: str = ""
    status: str = "offline"
    is_enabled: bool = True
    timeout: int = 30
    auto_restart: bool = True
    is_preset: bool = False
    tool_count: int = 0
    tools: list[MCPToolDTO] = []
    created_at: datetime | None = None


class CreateMCPServerDTO(OmicsHubBaseSchema):
    """注册外部 MCP Server"""

    name: str
    description: str = ""
    transport: str = "stdio"  # stdio | sse
    command: str = ""
    args: list[str] = []
    url: str = ""
    env: dict[str, str] = {}
    registry: str = "default"
    working_dir: str = ""
    timeout: int = 30
    auto_restart: bool = True


class UpdateMCPServerDTO(OmicsHubBaseSchema):
    """更新 MCP Server"""

    name: str | None = None
    description: str | None = None
    transport: str | None = None
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None
    registry: str | None = None
    working_dir: str | None = None
    version: str | None = None
    timeout: int | None = None
    auto_restart: bool | None = None
    is_enabled: bool | None = None


class MCPLogEntryDTO(OmicsHubBaseSchema):
    """MCP 日志条目"""

    timestamp: datetime
    level: str
    message: str
    source: str = "internal"


class InvokeToolDTO(OmicsHubBaseSchema):
    """工具调用请求"""

    tool_name: str
    arguments: dict[str, Any] = {}
