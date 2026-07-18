"""仪表板统计 — 当前用户视角（个人指标）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.services.stats_service import StatsService

router = APIRouter()


def get_stats_service(db: DbSession) -> StatsService:
    """获取统计服务实例"""
    return StatsService(db)


StatsServiceDep = Annotated[StatsService, Depends(get_stats_service)]


@router.get("/overview", summary="当前用户状态概览")
async def stats_overview(
    current_user_id: CurrentUserId,
    service: StatsServiceDep,
) -> dict:
    """运行中任务数 / 总任务数 / 累计样本数。"""
    return await service.user_overview(current_user_id)


@router.get("/trend", summary="当前用户任务提交趋势")
async def stats_trend(
    current_user_id: CurrentUserId,
    service: StatsServiceDep,
    days: Annotated[int, Query(ge=1, le=90, description="统计天数")] = 7,
) -> list[dict]:
    """近 N 天每日任务数 + 样本数（缺日补 0）。"""
    return await service.user_trend(current_user_id, days)


@router.get("/studio", summary="当前用户 Studio 用量与配额")
async def stats_studio_usage(
    current_user_id: CurrentUserId,
    service: StatsServiceDep,
    days: Annotated[int, Query(ge=1, le=90, description="统计天数")] = 30,
) -> dict:
    """Studio token、沙盒运行、产物与存储配额汇总。"""
    return await service.user_studio_usage(current_user_id, days)


@router.get("/progress", summary="当前用户引导进度画像")
async def stats_progress(
    current_user_id: CurrentUserId,
    service: StatsServiceDep,
) -> dict:
    """动态快速开始引导：三步完成状态 + 当前步骤。"""
    return await service.user_progress(current_user_id)
