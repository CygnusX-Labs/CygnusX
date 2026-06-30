"""仪表板统计 — 管理员全平台视角（全局态势）。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.services.stats_service import StatsService
from omichub.core.exceptions import AuthorizationError

router = APIRouter()


async def require_admin(current_user_id: CurrentUserId) -> None:
    """校验当前用户为管理员（沿用本仓各 admin router 的既有写法）。"""
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


def get_stats_service(db: DbSession) -> StatsService:
    """获取统计服务实例"""
    return StatsService(db)


StatsServiceDep = Annotated[StatsService, Depends(get_stats_service)]


@router.get("/status", summary="全平台任务状态分布")
async def admin_status(_admin: AdminRequired, service: StatsServiceDep) -> dict:
    """各状态任务数（pending/queued/running/success/failed/cancelled）。"""
    return await service.admin_status()


@router.get("/flows", summary="流程使用占比")
async def admin_flows(_admin: AdminRequired, service: StatsServiceDep) -> list[dict]:
    """各生信流程累计调用频次（降序）。"""
    return await service.admin_flow_usage()


@router.get("/users", summary="全平台用户与活跃度")
async def admin_users(_admin: AdminRequired, service: StatsServiceDep) -> dict:
    """注册用户总数 + 近 7 天活跃用户数。"""
    return await service.admin_user_stats()


@router.get("/recent-failed", summary="近期失败任务监控")
async def admin_recent_failed(
    _admin: AdminRequired,
    service: StatsServiceDep,
    limit: Annotated[int, Query(ge=1, le=50, description="返回条数")] = 10,
) -> list[dict]:
    """跨用户拉取近期失败任务（实时，不缓存）。"""
    return await service.admin_recent_failed(limit)
