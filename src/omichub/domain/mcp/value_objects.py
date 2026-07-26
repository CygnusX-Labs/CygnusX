"""MCP 域值对象"""

from enum import Enum


class Transport(str, Enum):
    """MCP 传输模式"""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"
    BUILTIN = "builtin"  # 内置预设（进程内执行，无需外部进程）


class ServerStatus(str, Enum):
    """MCP Server 状态"""

    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    STARTING = "starting"
