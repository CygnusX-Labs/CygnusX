"""MCP 域实体 - 聚合根"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from omichub.domain.mcp.value_objects import ServerStatus, Transport


class MCPToolRegistry(BaseModel):
    """MCP 工具注册"""

    tool_name: str
    description: str = ""
    input_schema: dict[str, Any] = {}
    server_id: UUID


class MCPServer(BaseModel):
    """MCP Server 聚合根"""

    id: UUID
    name: str
    description: str = ""
    transport: Transport = Transport.STDIO
    command: str = ""  # stdio 模式的启动命令
    url: str = ""  # SSE 模式的 URL
    env: dict[str, str] = {}
    status: ServerStatus = ServerStatus.OFFLINE
    tools: list[MCPToolRegistry] = []
    timeout: int = 30  # 超时秒数
    auto_restart: bool = True
    is_preset: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def is_available(self) -> bool:
        return self.status == ServerStatus.ONLINE
