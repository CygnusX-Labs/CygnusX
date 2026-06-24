"""MCP 服务路由"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/servers")
async def list_servers():
    """获取已注册的 MCP Server 列表"""
    return {"message": "list mcp servers"}


@router.post("/servers")
async def register_server():
    """注册新的 MCP Server"""
    return {"message": "register mcp server"}


@router.get("/servers/{server_id}/tools")
async def list_tools(server_id: str):
    """获取指定 MCP Server 的工具列表"""
    return {"server_id": server_id, "tools": []}
