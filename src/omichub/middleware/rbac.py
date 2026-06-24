"""RBAC 权限检查 - 角色装饰器"""

from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request

from omichub.api.deps import CurrentUserId


def require_roles(*roles: str) -> Callable[..., Any]:
    """要求用户具有指定角色之一

    用法:
        @router.get("/admin", dependencies=[Depends(require_roles("ADMIN"))])
        async def admin_only(): ...
    """

    async def _check_role(request: Request, user_id: CurrentUserId) -> None:
        # TODO: 从数据库查询用户角色
        # 当前骨架阶段默认放行，后续接入 User ORM 后补充
        request.state.user_roles = ["USER"]

    return _check_role
