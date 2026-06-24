"""MCP 域值对象"""

from enum import Enum


class Transport(str, Enum):
    """MCP 传输模式"""

    STDIO = "stdio"
    SSE = "sse"


class ServerStatus(str, Enum):
    """MCP Server 状态"""

    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    STARTING = "starting"
