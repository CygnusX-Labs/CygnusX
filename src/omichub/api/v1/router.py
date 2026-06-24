"""API v1 路由聚合"""

from fastapi import APIRouter

from omichub.api.v1 import ai, auth, files, flows, mcp, tasks, users

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(users.router, prefix="/users", tags=["用户"])
api_router.include_router(flows.router, prefix="/flows", tags=["流程"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["任务"])
api_router.include_router(files.router, prefix="/files", tags=["文件"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI 对话"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["MCP 服务"])
