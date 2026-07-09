"""MCP Client - MCP Server 生命周期管理、工具发现、调用路由与错误隔离"""

from __future__ import annotations

import asyncio
import ipaddress
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from omichub.domain.mcp.entities import MCPServer
from omichub.domain.mcp.value_objects import ServerStatus, Transport
from omichub.infrastructure.mcp.presets import get_preset_by_name

# stdio transport 禁止使用的 shell 解释器（大小写不敏感）
_DENIED_STDIO_COMMANDS = {
    "sh",
    "bash",
    "zsh",
    "dash",
    "csh",
    "tcsh",
    "fish",
    "cmd",
    "command",
    "powershell",
    "pwsh",
}


def _is_internal_host(host: str) -> bool:
    """判断主机名是否为内网、回环、链路本地、组播或 metadata 地址。"""
    if host == "169.254.169.254":
        return True
    try:
        addr = ipaddress.ip_address(host)
        return (
            addr.is_loopback
            or addr.is_private
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
        )
    except ValueError:
        return False


def validate_sse_url(url: str) -> None:
    """校验 SSE URL：仅允许 http/https，且禁止指向内网/本地/metadata 地址。"""
    if not url:
        raise ValueError("SSE URL 不能为空")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的 SSE URL scheme: {parsed.scheme}")
    host = parsed.hostname
    if not host:
        raise ValueError("SSE URL 缺少主机名")
    if _is_internal_host(host):
        raise ValueError("SSE URL 禁止指向内网、回环或 metadata 地址")


def validate_stdio_command(command: str) -> None:
    """校验 stdio command：禁止绝对路径和 shell 解释器。"""
    if not command:
        raise ValueError("stdio command 不能为空")
    if "/" in command or "\\" in command:
        raise ValueError("stdio command 禁止使用绝对路径")
    if command.lower() in _DENIED_STDIO_COMMANDS:
        raise ValueError(f"stdio command 禁止调用 shell 解释器: {command}")


class MCPClient:
    """MCP 客户端 - 统一管理 builtin / stdio / sse 三种传输

    builtin：进程内直接调用预设 handler（开箱即用）
    stdio/sse：通过 Python MCP SDK 建立会话调用（错误隔离，失败不影响主流程）
    """

    async def list_tools(self, server: MCPServer) -> list[dict[str, Any]]:
        """发现某 MCP Server 提供的工具"""
        if server.transport == Transport.BUILTIN:
            preset = get_preset_by_name(server.name)
            if preset is None:
                return []
            return [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["inputSchema"],
                }
                for t in preset["tools"]
            ]

        # stdio / sse：尝试连接获取工具列表
        tools = await self._safe_external(server, lambda s: self._list_tools_external(s))
        return tools or []

    async def call_tool(
        self, server: MCPServer, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """调用某 MCP Server 的指定工具"""
        if server.transport == Transport.BUILTIN:
            preset = get_preset_by_name(server.name)
            if preset is None:
                return {"success": False, "error": f"未找到内置服务: {server.name}"}
            handler = preset["handlers"].get(tool_name)
            if handler is None:
                return {"success": False, "error": f"工具 {tool_name} 不存在于 {server.name}"}
            try:
                result = await handler(arguments)
                return {"success": True, "result": result}
            except Exception as e:  # noqa: BLE001
                logger.warning(f"MCP 工具调用失败 {server.name}.{tool_name}: {e}")
                return {"success": False, "error": str(e)}

        # stdio / sse
        result = await self._safe_external(
            server, lambda s: self._call_tool_external(s, tool_name, arguments)
        )
        if result is None:
            return {"success": False, "error": "MCP Server 连接失败"}
        return {"success": True, "result": result}

    async def _safe_external(self, server: MCPServer, fn: Any) -> Any:
        """外部 MCP 调用的错误隔离包装"""
        try:
            return await asyncio.wait_for(fn(server), timeout=server.timeout)
        except TimeoutError:
            logger.warning(f"MCP Server {server.name} 调用超时")
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"MCP Server {server.name} 调用异常: {e}")
            return None

    async def _list_tools_external(self, server: MCPServer) -> list[dict[str, Any]]:
        """通过 MCP SDK 发现外部 stdio/sse 服务的工具"""
        try:
            from mcp import ClientSession
        except ImportError:
            return []

        async with (
            self._open_session(server) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema or {},
                }
                for t in result.tools
            ]

    async def _call_tool_external(
        self, server: MCPServer, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """通过 MCP SDK 调用外部服务工具"""
        try:
            from mcp import ClientSession
        except ImportError:
            raise RuntimeError("mcp SDK 未安装") from None

        async with (
            self._open_session(server) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            return {
                "content": [c.model_dump() for c in result.content] if result.content else [],
                "isError": result.isError,
            }

    def _open_session(self, server: MCPServer) -> Any:
        """根据传输模式打开 MCP 会话上下文（含安全校验）"""
        if server.transport == Transport.STDIO:
            from mcp.client.stdio import StdioServerParameters, stdio_client

            command = server.command or ""
            validate_stdio_command(command)
            parts = command.split() if command else []
            command = parts[0] if parts else ""
            args = parts[1:] if len(parts) > 1 else []
            if server.args:
                args = list(server.args)
            params = StdioServerParameters(
                command=command,
                args=args,
                env=server.env or None,
            )
            return stdio_client(params)
        if server.transport == Transport.SSE:
            from mcp.client.sse import sse_client

            validate_sse_url(server.url)
            return sse_client(server.url)
        raise ValueError(f"不支持的传输模式: {server.transport}")


def status_from_available(ok: bool) -> str:
    return ServerStatus.ONLINE.value if ok else ServerStatus.ERROR.value
