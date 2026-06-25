"""API v1 路由汇总"""

from fastapi import APIRouter

from omichub.api.v1 import auth, cookies, flows, tasks, users
from omichub.api.v1.admin import admin_cookies

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(flows.router, prefix="/flows", tags=["Flows"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(cookies.router, prefix="/cookies", tags=["Cookies"])
api_router.include_router(admin_cookies.router, prefix="/admin/cookies", tags=["Admin-Cookies"])
