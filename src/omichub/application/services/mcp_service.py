"""MCP 应用服务 - Server CRUD、工具发现、调用路由、预设初始化"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.mcp import (
    CreateMCPServerDTO,
    MCPLogEntryDTO,
    MCPServerDTO,
    MCPToolDTO,
    UpdateMCPServerDTO,
)
from omichub.application.schemas.tool_invocation import ToolInvocationContext
from omichub.core.config import get_settings
from omichub.core.exceptions import ConflictError, NotFoundError, ValidationError
from omichub.domain.mcp.entities import MCPServer, MCPToolRegistry
from omichub.domain.mcp.services import MCPDomainService
from omichub.domain.mcp.value_objects import ServerStatus, Transport
from omichub.infrastructure.database.models.mcp_log import MCPLogModel
from omichub.infrastructure.database.repositories.mcp_repository import (
    SqlAlchemyMCPServerRepository,
)
from omichub.infrastructure.mcp.client import MCPClient, validate_sse_url, validate_stdio_command
from omichub.infrastructure.mcp.presets import (
    OMICHUB_PIPELINES_SERVER_ID,
    OMICHUB_PIPELINES_SERVER_NAME,
    OMICHUB_PLATFORM_SERVER_ID,
    OMICHUB_TOOLS_SERVER_ID,
    OMICHUB_TOOLS_SERVER_NAME,
    PRESET_SERVERS,
    _build_omichub_tools_preset,
    get_preset_by_name,
)


def _server_to_dto(s: MCPServer) -> MCPServerDTO:
    return MCPServerDTO(
        id=s.id,
        name=s.name,
        description=s.description,
        transport=s.transport.value,
        command=s.command,
        args=list(s.args or []),
        url=s.url,
        env=dict(s.env or {}),
        registry=s.registry,
        working_dir=s.working_dir,
        version=s.version,
        status=s.status.value if hasattr(s.status, "value") else str(s.status),
        is_enabled=s.is_enabled,
        timeout=s.timeout,
        auto_restart=s.auto_restart,
        is_preset=s.is_preset,
        tool_count=len(s.tools),
        tools=[_tool_to_dto(t) for t in s.tools],
        created_at=s.created_at,
    )


def _tool_to_dto(t: MCPToolRegistry | dict[str, Any]) -> MCPToolDTO:
    if isinstance(t, dict):
        return MCPToolDTO(
            name=t.get("name", ""),
            description=t.get("description", ""),
            input_schema=t.get("inputSchema", {}),
        )
    return MCPToolDTO(name=t.tool_name, description=t.description, input_schema=t.input_schema)


class MCPService:
    """MCP 集成应用服务"""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = SqlAlchemyMCPServerRepository(db)
        self._domain = MCPDomainService(self._repo)
        self._client = MCPClient()
        self._settings = get_settings()

    async def ensure_presets(self) -> None:
        """初始化预设 MCP 服务（含 omichub-tools 动态预设，幂等）"""
        valid_names = {p["name"] for p in PRESET_SERVERS} | {OMICHUB_TOOLS_SERVER_NAME}
        for server in await self._repo.list_all():
            if server.is_preset and server.name not in valid_names:
                await self._repo.delete(server.id, force=True)

        for preset in PRESET_SERVERS:
            existing = await self._repo.get_by_name(preset["name"])
            if existing is not None:
                # 预设工具随代码演进（如新增工作区文件工具），需把最新工具清单同步进库，
                # 否则已存在部署的 builtin 预设工具不会出现在 LLM 工具清单里。
                if preset["name"] in (OMICHUB_PIPELINES_SERVER_NAME, "omichub-platform"):
                    existing.tools = [
                        MCPToolRegistry(
                            tool_name=tool["name"],
                            description=tool["description"],
                            input_schema=tool["inputSchema"],
                            server_id=existing.id,
                        )
                        for tool in preset["tools"]
                    ]
                    existing.status = ServerStatus.ONLINE
                    existing.is_enabled = True
                    await self._repo.save(existing)
                continue
            preset_id = (
                OMICHUB_PLATFORM_SERVER_ID
                if preset["name"] == "omichub-platform"
                else OMICHUB_PIPELINES_SERVER_ID
                if preset["name"] == OMICHUB_PIPELINES_SERVER_NAME
                else uuid4()
            )
            tools = [
                MCPToolRegistry(
                    tool_name=t["name"],
                    description=t["description"],
                    input_schema=t["inputSchema"],
                    server_id=preset_id,
                )
                for t in preset["tools"]
            ]
            server = MCPServer(
                id=preset_id,
                name=preset["name"],
                description=preset["description"],
                transport=Transport.BUILTIN,
                status=ServerStatus.ONLINE,
                tools=tools,
                timeout=self._settings.mcp_default_timeout,
                auto_restart=True,
                is_preset=True,
            )
            await self._repo.save(server)

        # 动态生信工具箱 preset
        omichub_preset = _build_omichub_tools_preset()
        existing_omichub = await self._repo.get_by_id(OMICHUB_TOOLS_SERVER_ID)
        if existing_omichub is None:
            tools = [
                MCPToolRegistry(
                    tool_name=t["name"],
                    description=t["description"],
                    input_schema=t["inputSchema"],
                    server_id=OMICHUB_TOOLS_SERVER_ID,
                )
                for t in omichub_preset["tools"]
            ]
            server = MCPServer(
                id=OMICHUB_TOOLS_SERVER_ID,
                name=OMICHUB_TOOLS_SERVER_NAME,
                description=omichub_preset["description"],
                transport=Transport.BUILTIN,
                status=ServerStatus.ONLINE,
                tools=tools,
                timeout=self._settings.mcp_default_timeout,
                auto_restart=True,
                is_preset=True,
            )
            await self._repo.save(server)

    async def list_servers(self, active_only: bool = False) -> list[MCPServerDTO]:
        await self.ensure_presets()
        servers = await self._repo.list_all(active_only=active_only)
        return [_server_to_dto(s) for s in servers]

    async def get_server(self, server_id: UUID) -> MCPServerDTO:
        await self.ensure_presets()
        server = await self._repo.get_by_id(server_id)
        if server is None:
            raise NotFoundError("MCP Server 不存在")
        return _server_to_dto(server)

    async def register_server(self, req: CreateMCPServerDTO) -> MCPServerDTO:
        """注册新的外部 MCP Server（stdio/sse）"""
        existing = await self._repo.get_by_name(req.name)
        if existing is not None:
            raise ConflictError(f"MCP Server 名称已存在: {req.name}")
        transport = (
            Transport(req.transport) if req.transport in ("stdio", "sse") else Transport.STDIO
        )
        if transport == Transport.STDIO:
            try:
                validate_stdio_command(req.command or "")
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        elif transport == Transport.SSE:
            try:
                validate_sse_url(req.url or "")
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        server = MCPServer(
            id=uuid4(),
            name=req.name,
            description=req.description,
            transport=transport,
            command=req.command,
            args=list(req.args or []),
            url=req.url,
            env=req.env,
            registry=req.registry,
            working_dir=req.working_dir,
            status=ServerStatus.OFFLINE,
            timeout=req.timeout,
            auto_restart=req.auto_restart,
            is_preset=False,
        )
        server = await self._domain.register_server(server)
        return _server_to_dto(server)

    async def delete_server(self, server_id: UUID) -> bool:
        return await self._repo.delete(server_id)

    async def update_server(self, server_id: UUID, req: UpdateMCPServerDTO) -> MCPServerDTO:
        """更新 MCP Server 配置"""
        server = await self._repo.get_by_id(server_id)
        if server is None:
            raise NotFoundError("MCP Server 不存在")
        data = req.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(server, key, value)
        # 校验更新后的配置
        transport = server.transport
        if transport == Transport.STDIO:
            try:
                validate_stdio_command(server.command or "")
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        elif transport == Transport.SSE:
            try:
                validate_sse_url(server.url or "")
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
        await self._repo.save(server)
        return _server_to_dto(server)

    async def test_server(self, server_id: UUID) -> dict[str, Any]:
        """测试连接并发现工具"""
        try:
            tools = await self.list_tools(server_id)
            await self._add_log(
                server_id, "info", f"测试连接成功，发现 {len(tools)} 个工具", "internal"
            )
            return {"success": True, "tool_count": len(tools), "status": "online"}
        except Exception as e:  # noqa: BLE001
            await self._add_log(server_id, "error", f"测试连接失败: {e}", "internal")
            return {"success": False, "tool_count": 0, "status": "error", "error": str(e)}

    async def list_tools(self, server_id: UUID) -> list[MCPToolDTO]:
        """获取指定 Server 的工具列表（builtin 即时返回；外部即时发现）"""
        server = await self._repo.get_by_id(server_id)
        if server is None:
            raise NotFoundError("MCP Server 不存在")
        tools = await self._client.list_tools(server)
        # 更新存储的工具快照 + 状态
        server.tools = [
            MCPToolRegistry(
                tool_name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                server_id=server.id,
            )
            for t in tools
        ]
        await self._domain.mark_online(server.id)
        await self._repo.save(server)
        return [_tool_to_dto(t) for t in tools]

    async def invoke_tool(
        self, server_id: UUID, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """调用指定 Server 的工具（带路由校验与错误隔离）"""
        server = await self._repo.get_by_id(server_id)
        if server is None:
            raise NotFoundError("MCP Server 不存在")
        # 路由校验：确认工具属于该 server（builtin 允许未刷入快照的直接调用）
        routed = await self._domain.route_tool_call(tool_name)
        if (routed is None or routed.id != server.id) and server.transport != Transport.BUILTIN:
            raise NotFoundError(f"工具 {tool_name} 不属于该 Server")
        result = await self._client.call_tool(server, tool_name, arguments)
        if not result.get("success"):
            await self._domain.mark_error(server.id)
            await self._add_log(
                server_id,
                "error",
                f"工具调用失败 {tool_name}: {result.get('error', '')}",
                "internal",
            )
        else:
            await self._add_log(server_id, "info", f"工具调用成功 {tool_name}", "internal")
        return result

    async def invoke_pipeline_tool(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str = "pipeline-frontend",
    ) -> dict[str, Any]:
        """以当前用户上下文调用内置 omichub-pipelines 工具。"""
        await self.ensure_presets()
        server = await self._repo.get_by_id(OMICHUB_PIPELINES_SERVER_ID)
        if server is None or server.name != OMICHUB_PIPELINES_SERVER_NAME:
            raise NotFoundError("omichub-pipelines MCP Server 不存在")
        preset = get_preset_by_name(OMICHUB_PIPELINES_SERVER_NAME)
        tool_names = {tool["name"] for tool in (preset or {}).get("tools", [])}
        if tool_name not in tool_names:
            raise NotFoundError(f"流水线工具不存在: {tool_name}")
        context = ToolInvocationContext(
            user_id=user_id,
            session_id=session_id,
            db=self._db,
        )
        result = await self._client.call_tool(
            server,
            tool_name,
            arguments,
            user_id=user_id,
            context=context,
        )
        if result.get("success"):
            await self._add_log(server.id, "info", f"用户调用成功 {tool_name}", "frontend")
        else:
            await self._add_log(
                server.id,
                "error",
                f"用户调用失败 {tool_name}: {result.get('error', '')}",
                "frontend",
            )
        return result

    async def list_logs(self, server_id: UUID, tail: int = 100) -> list[MCPLogEntryDTO]:
        """获取 MCP Server 最近日志"""
        from sqlalchemy import desc, select

        result = await self._db.execute(
            select(MCPLogModel)
            .where(MCPLogModel.service_id == server_id)
            .order_by(desc(MCPLogModel.timestamp))
            .limit(tail)
        )
        logs = result.scalars().all()
        return [
            MCPLogEntryDTO(
                timestamp=log.timestamp,
                level=log.level,
                message=log.message,
                source=log.source,
            )
            for log in reversed(logs)
        ]

    async def _add_log(
        self, server_id: UUID, level: str, message: str, source: str = "internal"
    ) -> None:
        """写入一条 MCP 日志"""
        from datetime import datetime

        self._db.add(
            MCPLogModel(
                service_id=server_id,
                timestamp=datetime.utcnow(),
                level=level,
                message=message,
                source=source,
            )
        )
        await self._db.flush()
