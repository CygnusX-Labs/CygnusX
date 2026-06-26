"""API v1 路由汇总"""

from fastapi import APIRouter

from omichub.api.v1 import (
    ai,
    auth,
    cookies,
    docs,
    files,
    flows,
    mcp,
    notification,
    sandbox,
    site_settings,
    tasks,
    users,
)
from omichub.api.v1.admin import admin_cookies
from omichub.api.v1.admin import ai_providers as admin_ai_providers
from omichub.api.v1.admin import users as admin_users

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(site_settings.router, prefix="/site-settings", tags=["SiteSettings"])
api_router.include_router(docs.router, prefix="/docs", tags=["Docs"])
api_router.include_router(flows.router, prefix="/flows", tags=["Flows"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(files.router, prefix="/files", tags=["Files"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(cookies.router, prefix="/cookies", tags=["Cookies"])
api_router.include_router(admin_cookies.router, prefix="/admin/cookies", tags=["Admin-Cookies"])
api_router.include_router(admin_users.router, prefix="/admin/users", tags=["Admin-Users"])
api_router.include_router(
    admin_ai_providers.router, prefix="/admin/ai-providers", tags=["Admin-AI-Providers"]
)
api_router.include_router(ai.router, prefix="/ai", tags=["AI Copilot"])
api_router.include_router(notification.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["MCP"])
api_router.include_router(sandbox.router, prefix="/sandbox", tags=["Sandbox"])
