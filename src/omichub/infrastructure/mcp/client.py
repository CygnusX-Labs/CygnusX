"""MCP Client - MCP Server 生命周期管理、工具发现、调用路由与错误隔离"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from omichub.domain.mcp.entities import MCPServer
from omichub.domain.mcp.value_objects import ServerStatus, Transport
from omichub.infrastructure.mcp.presets import get_preset_by_name


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
                {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
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

    async def _safe_external(
        self, server: MCPServer, fn: Any
    ) -> Any:
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
        """根据传输模式打开 MCP 会话上下文"""
        if server.transport == Transport.STDIO:
            from mcp.client.stdio import StdioServerParameters, stdio_client

            params = StdioServerParameters(
                command=server.command.split()[0] if server.command else "",
                args=server.command.split()[1:] if server.command else [],
                env=server.env or None,
            )
            return stdio_client(params)
        if server.transport == Transport.SSE:
            from mcp.client.sse import sse_client

            return sse_client(server.url)
        raise ValueError(f"不支持的传输模式: {server.transport}")


def status_from_available(ok: bool) -> str:
    return ServerStatus.ONLINE.value if ok else ServerStatus.ERROR.value
