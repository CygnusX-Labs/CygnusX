"""MCP 服务路由 - CRUD、工具发现、工具调用"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.mcp import (
    CreateMCPServerDTO,
    InvokeToolDTO,
    MCPServerDTO,
    MCPToolDTO,
)
from omichub.application.services.mcp_service import MCPService

router = APIRouter()


def get_mcp_service(db: DbSession) -> MCPService:
    return MCPService(db)


MCPServiceDep = Annotated[MCPService, Depends(get_mcp_service)]


@router.get("/servers", response_model=list[MCPServerDTO], summary="MCP Server 列表")
async def list_servers(
    current_user_id: CurrentUserId,
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
    current_user_id: CurrentUserId,
    service: MCPServiceDep,
    req: CreateMCPServerDTO,
) -> MCPServerDTO:
    return await service.register_server(req)


@router.get("/servers/{server_id}", response_model=MCPServerDTO, summary="Server 详情")
async def get_server(
    current_user_id: CurrentUserId,
    service: MCPServiceDep,
    server_id: UUID,
) -> MCPServerDTO:
    return await service.get_server(server_id)


@router.delete("/servers/{server_id}", summary="删除 Server")
async def delete_server(
    current_user_id: CurrentUserId,
    service: MCPServiceDep,
    server_id: UUID,
) -> dict[str, bool]:
    ok = await service.delete_server(server_id)
    return {"deleted": ok}


@router.get(
    "/servers/{server_id}/tools",
    response_model=list[MCPToolDTO],
    summary="发现 Server 工具",
)
async def list_tools(
    current_user_id: CurrentUserId,
    service: MCPServiceDep,
    server_id: UUID,
) -> list[MCPToolDTO]:
    return await service.list_tools(server_id)


@router.post(
    "/servers/{server_id}/tools/{tool_name}/invoke",
    summary="调用 MCP 工具",
)
async def invoke_tool(
    current_user_id: CurrentUserId,
    service: MCPServiceDep,
    server_id: UUID,
    tool_name: str,
    req: InvokeToolDTO,
) -> dict[str, Any]:
    if req.tool_name and req.tool_name != tool_name:
        from omichub.core.exceptions import ValidationError

        raise ValidationError("tool_name 与路径不一致")
    return await service.invoke_tool(server_id, tool_name, req.arguments)
