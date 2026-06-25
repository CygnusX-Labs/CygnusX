"""饼干积分 — 管理端路由"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.cookie import (
    AdjustBalanceRequest,
    CookieAccountDTO,
    CookieStatsDTO,
    CookieTransactionDTO,
    PricingCreateRequest,
)
from omichub.application.services.cookie_service import CookieService
from omichub.core.exceptions import AuthorizationError

router = APIRouter()


def get_cookie_service(db: DbSession) -> CookieService:
    return CookieService(db)


CookieServiceDep = Annotated[CookieService, Depends(get_cookie_service)]


async def require_admin(current_user_id: CurrentUserId) -> None:
    """简化版管理员校验 — 后续可接入完整 RBAC"""
    from omichub.infrastructure.database.session import get_session_factory
    from omichub.infrastructure.database.models.user import UserModel

    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(UserModel.role).where(UserModel.id == UUID(current_user_id))
        )
        role = result.scalar_one_or_none()
        if role != "admin":
            raise AuthorizationError("需要管理员权限")


AdminRequired = Annotated[None, Depends(require_admin)]


@router.get("/accounts", response_model=list[CookieAccountDTO], summary="所有账户")
async def list_accounts(
    _admin: AdminRequired,
    service: CookieServiceDep,
    status: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[CookieAccountDTO]:
    return await service.list_all_accounts(status, offset, limit)


@router.post("/accounts/{user_id}/adjust", response_model=CookieTransactionDTO, summary="调整余额")
async def adjust_balance(
    user_id: UUID,
    req: AdjustBalanceRequest,
    current_user_id: CurrentUserId,
    _admin: AdminRequired,
    service: CookieServiceDep,
) -> CookieTransactionDTO:
    return await service.adjust_balance(user_id, req.amount, req.reason, UUID(current_user_id))


@router.put("/accounts/{user_id}/freeze", response_model=CookieAccountDTO, summary="冻结账户")
async def freeze_account(
    user_id: UUID,
    current_user_id: CurrentUserId,
    _admin: AdminRequired,
    service: CookieServiceDep,
    reason: str = "",
) -> CookieAccountDTO:
    return await service.freeze_account(user_id, reason, UUID(current_user_id))


@router.put("/accounts/{user_id}/unfreeze", response_model=CookieAccountDTO, summary="解冻账户")
async def unfreeze_account(
    user_id: UUID,
    _admin: AdminRequired,
    service: CookieServiceDep,
) -> CookieAccountDTO:
    return await service.unfreeze_account(user_id)


@router.put("/accounts/{user_id}/suspend", response_model=CookieAccountDTO, summary="停用账户")
async def suspend_account(
    user_id: UUID,
    current_user_id: CurrentUserId,
    _admin: AdminRequired,
    service: CookieServiceDep,
    reason: str = "",
) -> CookieAccountDTO:
    return await service.suspend_account(user_id, reason, UUID(current_user_id))


@router.get("/transactions", response_model=list[CookieTransactionDTO], summary="全局交易流水")
async def list_all_transactions(
    _admin: AdminRequired,
    service: CookieServiceDep,
    offset: int = 0,
    limit: int = 50,
) -> list[CookieTransactionDTO]:
    return await service.list_all_transactions(offset, limit)


@router.get("/stats", response_model=CookieStatsDTO, summary="系统统计")
async def get_stats(
    _admin: AdminRequired,
    service: CookieServiceDep,
) -> CookieStatsDTO:
    return await service.get_stats()


@router.get("/pricing", summary="所有定价策略(含停用)")
async def list_all_pricing(
    _admin: AdminRequired,
    service: CookieServiceDep,
):
    return await service.list_pricing(active_only=False)


@router.post("/pricing", summary="创建定价策略")
async def create_pricing(
    req: PricingCreateRequest,
    current_user_id: CurrentUserId,
    _admin: AdminRequired,
    service: CookieServiceDep,
):
    return await service.create_pricing(req, UUID(current_user_id))


@router.put("/pricing/{pricing_id}", summary="更新定价策略")
async def update_pricing(
    pricing_id: int,
    req: PricingCreateRequest,
    current_user_id: CurrentUserId,
    _admin: AdminRequired,
    service: CookieServiceDep,
):
    return await service.update_pricing(pricing_id, req, UUID(current_user_id))


@router.delete("/pricing/{pricing_id}", summary="删除定价策略")
async def delete_pricing(
    pricing_id: int,
    _admin: AdminRequired,
    service: CookieServiceDep,
):
    ok = await service.delete_pricing(pricing_id)
    return {"deleted": ok}
