"""MCP 服务路由 - CRUD、工具发现、工具调用（全部管理员守卫）"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends

from omichub.api.deps import DbSession
from omichub.api.v1.admin.users import AdminRequired
from omichub.application.schemas.mcp import (
    CreateMCPServerDTO,
    InvokeToolDTO,
    MCPLogEntryDTO,
    MCPServerDTO,
    MCPToolDTO,
    UpdateMCPServerDTO,
)
from omichub.application.services.mcp_service import MCPService

router = APIRouter()


def get_mcp_service(db: DbSession) -> MCPService:
    return MCPService(db)


MCPServiceDep = Annotated[MCPService, Depends(get_mcp_service)]


@router.get("/servers", response_model=list[MCPServerDTO], summary="MCP Server 列表")
async def list_servers(
    _admin: AdminRequired,
    service: MCPServiceDep,
    active_only: bool = False,
) -> list[MCPServerDTO]:
    return await service.list_servers(active_only=active_only)


@router.post(
    "/servers",
    response_model=MCPServerDTO,
    status_code=201,
    summary="注册外部 MCP Server",
)
async def register_server(
    _admin: AdminRequired,
    service: MCPServiceDep,
    req: CreateMCPServerDTO,
) -> MCPServerDTO:
    return await service.register_server(req)


@router.put("/servers/{server_id}", response_model=MCPServerDTO, summary="更新 MCP Server")
async def update_server(
    _admin: AdminRequired,
    service: MCPServiceDep,
    server_id: UUID,
    req: UpdateMCPServerDTO,
) -> MCPServerDTO:
    return await service.update_server(server_id, req)


@router.get("/servers/{server_id}", response_model=MCPServerDTO, summary="Server 详情")
async def get_server(
    _admin: AdminRequired,
    service: MCPServiceDep,
    server_id: UUID,
) -> MCPServerDTO:
    return await service.get_server(server_id)


@router.delete("/servers/{server_id}", summary="删除 Server")
async def delete_server(
    _admin: AdminRequired,
    service: MCPServiceDep,
    server_id: UUID,
) -> dict[str, bool]:
    ok = await service.delete_server(server_id)
    return {"deleted": ok}


@router.post("/servers/{server_id}/test", summary="测试 MCP Server 连接")
async def test_server(
    _admin: AdminRequired,
    service: MCPServiceDep,
    server_id: UUID,
) -> dict[str, Any]:
    return await service.test_server(server_id)


@router.get(
    "/servers/{server_id}/tools",
    response_model=list[MCPToolDTO],
    summary="发现 Server 工具",
)
async def list_tools(
    _admin: AdminRequired,
    service: MCPServiceDep,
    server_id: UUID,
) -> list[MCPToolDTO]:
    return await service.list_tools(server_id)


@router.post(
    "/servers/{server_id}/tools/{tool_name}/invoke",
    summary="调用 MCP 工具",
)
async def invoke_tool(
    _admin: AdminRequired,
    service: MCPServiceDep,
    server_id: UUID,
    tool_name: str,
    req: InvokeToolDTO,
) -> dict[str, Any]:
    if req.tool_name and req.tool_name != tool_name:
        from omichub.core.exceptions import ValidationError

        raise ValidationError("tool_name 与路径不一致")
    return await service.invoke_tool(server_id, tool_name, req.arguments)


@router.get(
    "/servers/{server_id}/logs",
    response_model=list[MCPLogEntryDTO],
    summary="MCP Server 运行日志",
)
async def list_logs(
    _admin: AdminRequired,
    service: MCPServiceDep,
    server_id: UUID,
    tail: int = 100,
) -> list[MCPLogEntryDTO]:
    return await service.list_logs(server_id, tail=tail)
