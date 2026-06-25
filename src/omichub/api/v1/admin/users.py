"""用户管理 — 管理端路由 (审批/列表)"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.api.deps import CurrentUserId, DbSession
from omichub.core.exceptions import AuthorizationError, NotFoundError

router = APIRouter()


async def require_admin(current_user_id: CurrentUserId) -> None:
    from omichub.infrastructure.database.models.user import UserModel
    from omichub.infrastructure.database.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(UserModel.role).where(UserModel.id == UUID(current_user_id))
        )
        role = result.scalar_one_or_none()
        if role != "admin":
            raise AuthorizationError("需要管理员权限")


AdminRequired = Annotated[None, Depends(require_admin)]


@router.get("", summary="所有用户列表")
async def list_users(
    _admin: AdminRequired,
    db: DbSession,
    status: Annotated[str | None, Query()] = None,
    offset: int = 0,
    limit: int = 100,
):
    from omichub.infrastructure.database.models.user import UserModel

    query = select(
        UserModel.id,
        UserModel.username,
        UserModel.email,
        UserModel.role,
        UserModel.status,
        UserModel.created_at,
        UserModel.last_login_at,
    )
    if status:
        query = query.where(UserModel.status == status)
    query = query.order_by(desc(UserModel.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    return [
        {
            "id": str(row.id),
            "username": row.username,
            "email": row.email,
            "role": row.role,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None,
        }
        for row in result.all()
    ]


@router.put("/{user_id}/approve", summary="审批通过用户")
async def approve_user(
    user_id: UUID,
    _admin: AdminRequired,
    db: DbSession,
):
    from omichub.infrastructure.database.models.user import UserModel

    user = await db.get(UserModel, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    if user.status != "pending":
        return {"message": f"用户当前状态为 {user.status}，无需审批"}
    user.status = "active"
    await db.flush()
    return {"id": str(user.id), "username": user.username, "status": user.status}


@router.put("/{user_id}/reject", summary="拒绝用户注册")
async def reject_user(
    user_id: UUID,
    _admin: AdminRequired,
    db: DbSession,
    reason: str = "",
):
    from omichub.infrastructure.database.models.user import UserModel

    user = await db.get(UserModel, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    user.status = "rejected"
    await db.flush()
    return {"id": str(user.id), "username": user.username, "status": "rejected", "reason": reason}


@router.put("/{user_id}/role", summary="修改用户角色")
async def update_user_role(
    user_id: UUID,
    _admin: AdminRequired,
    db: DbSession,
    role: str = "user",
):
    from omichub.infrastructure.database.models.user import UserModel

    if role not in ("admin", "user"):
        raise AuthorizationError("角色只能是 admin 或 user")
    user = await db.get(UserModel, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    user.role = role
    await db.flush()
    return {"id": str(user.id), "username": user.username, "role": user.role}
