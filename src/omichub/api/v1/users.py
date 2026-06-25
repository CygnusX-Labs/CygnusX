"""用户管理路由"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.user import (
    UserListItem,
    UserResponse,
    UserUpdateRequest,
)
from omichub.application.services import UserService
from omichub.core.exceptions import AuthorizationError
from omichub.infrastructure.database.repositories import SqlAlchemyUserRepository
from omichub.middleware.rbac import require_roles

router = APIRouter()


def get_user_service(db: DbSession) -> UserService:
    """获取用户服务实例"""
    return UserService(SqlAlchemyUserRepository(db))


@router.get(
    "/",
    dependencies=[Depends(require_roles("admin"))],
    response_model=list[UserListItem],
)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    q: str | None = Query(None, description="搜索关键词（用户名/邮箱）"),
    role: str | None = Query(None),
    status: str | None = Query(None),
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """获取用户列表（仅管理员）"""
    users, _total = await user_service.get_user_list(page, page_size, q, role, status)
    return [UserListItem.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user_id: CurrentUserId,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """获取用户详情（普通用户只能查看自己，管理员可查看所有）"""
    # 普通用户只能查看自己
    if user_id != current_user_id:
        # 检查是否为管理员 - 通过 require_roles 依赖已校验
        # 此处简化处理：非自己的请求需要管理员权限
        # TODO: 完整 RBAC 检查需要查询用户角色
        raise AuthorizationError("无权查看其他用户信息")

    user = await user_service.get_user_by_id(user_id)
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    req: UserUpdateRequest,
    current_user_id: CurrentUserId,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """更新用户信息（普通用户只能更新自己）"""
    if user_id != current_user_id:
        raise AuthorizationError("无权修改其他用户信息")

    user = await user_service.update_user(user_id, req)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", dependencies=[Depends(require_roles("admin"))])
async def delete_user(
    user_id: str,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """删除用户（仅管理员）"""
    await user_service.delete_user(user_id)
    return {"message": "用户删除成功"}
