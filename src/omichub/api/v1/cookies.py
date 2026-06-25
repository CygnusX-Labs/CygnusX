"""饼干积分 — 用户端路由"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.cookie import (
    CookieAccountDTO,
    CookieTransactionDTO,
    CostEstimateDTO,
)
from omichub.application.services.cookie_service import CookieService

router = APIRouter()


def get_cookie_service(db: DbSession) -> CookieService:
    return CookieService(db)


CookieServiceDep = Annotated[CookieService, Depends(get_cookie_service)]


@router.get("/account", response_model=CookieAccountDTO, summary="获取我的饼干账户")
async def get_account(
    current_user_id: CurrentUserId, service: CookieServiceDep
) -> CookieAccountDTO:
    return await service.get_account(UUID(current_user_id))


@router.get("/transactions", response_model=list[CookieTransactionDTO], summary="交易流水")
async def list_transactions(
    current_user_id: CurrentUserId,
    service: CookieServiceDep,
    txn_type: Annotated[str | None, Query()] = None,
    offset: int = 0,
    limit: int = 50,
) -> list[CookieTransactionDTO]:
    return await service.list_transactions(UUID(current_user_id), txn_type, offset, limit)


@router.get("/pricing", summary="查看定价策略")
async def list_pricing(service: CookieServiceDep):
    return await service.list_pricing(active_only=True)


@router.get("/estimate", response_model=CostEstimateDTO, summary="预估任务费用")
async def estimate_cost(
    current_user_id: CurrentUserId,
    service: CookieServiceDep,
    flow_id: str = Query(..., description="流程ID"),
) -> CostEstimateDTO:
    return await service.estimate_cost(UUID(current_user_id), flow_id)


@router.get("/balance-check", summary="检查余额是否足够")
async def balance_check(
    current_user_id: CurrentUserId,
    service: CookieServiceDep,
    amount: float = Query(..., description="需要的饼干数"),
):
    balance = await service.check_balance(UUID(current_user_id))
    return {"balance": float(balance), "sufficient": balance >= amount}
