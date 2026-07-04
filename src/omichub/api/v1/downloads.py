"""数据下载路由 — EBI/NCBI 测序数据下载入口。"""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.download import DownloadRequest
from omichub.application.schemas.download_progress import (
    DownloadProgressResponse,
    RunProgressDTO,
    StageProgressDTO,
)
from omichub.application.schemas.task import TaskListResponse, TaskResponse
from omichub.application.services.download_service import DownloadService
from omichub.core.config import get_settings
from omichub.core.exceptions import NotFoundError, ValidationError
from omichub.infrastructure.cache.redis_client import get_redis

router = APIRouter()


def get_download_service(db: DbSession) -> DownloadService:
    """获取下载服务实例"""
    return DownloadService(db)


DownloadServiceDep = Annotated[DownloadService, Depends(get_download_service)]


def _ensure_enabled() -> None:
    """未启用数据下载时拒绝（部署里装好二进制+sra-tools 再开）。"""
    if not get_settings().enable_ebi_download:
        raise ValidationError("数据下载功能未启用")


@router.post("", response_model=TaskResponse, summary="提交数据下载任务")
async def submit_download(
    current_user_id: CurrentUserId,
    req: DownloadRequest,
    service: DownloadServiceDep,
) -> TaskResponse:
    """提交一个 EBI/NCBI 数据下载任务，返回任务对象（可经 /tasks/{id} 查进度/日志）。"""
    _ensure_enabled()
    return await service.submit(current_user_id, req)


@router.get("", response_model=TaskListResponse, summary="数据下载任务列表")
async def list_downloads(
    current_user_id: CurrentUserId,
    service: DownloadServiceDep,
) -> TaskListResponse:
    """列出当前用户的数据下载任务。"""
    return await service.list_downloads(current_user_id)


@router.get(
    "/{task_id}/progress",
    response_model=DownloadProgressResponse,
    summary="获取下载任务逐运行进度",
)
async def get_download_progress(
    task_id: UUID,
    current_user_id: CurrentUserId,
    service: DownloadServiceDep,
) -> DownloadProgressResponse:
    """返回每个 SRR run 的分阶段进度（下载/解压/压缩）。

    数据来源：EBIDownload HTTP Progress API → Celery 轮询解密 → Redis。
    若 Redis 中无数据（任务未运行或 progress API 不可用），返回 source="unavailable"。
    """
    # 校验任务归属
    task_resp = await service.get_task_for_user(task_id, current_user_id)

    redis = get_redis()
    raw = await redis.get(f"download_progress:{task_id}")

    if raw is None:
        return DownloadProgressResponse(
            task_id=str(task_id),
            runs={},
            overall_percent=task_resp.progress * 100,
            source="unavailable",
        )

    runs_data = json.loads(raw)
    runs: dict[str, RunProgressDTO] = {}
    for run_id, rp in runs_data.items():
        runs[run_id] = RunProgressDTO(
            run_id=rp["run_id"],
            stage=rp["stage"],
            overall_percent=rp["overall_percent"],
            download=StageProgressDTO(**rp["download"]),
            extraction=StageProgressDTO(**rp["extraction"]),
            compression=StageProgressDTO(**rp["compression"]),
        )

    overall = sum(r.overall_percent for r in runs.values()) / len(runs) if runs else 0.0

    return DownloadProgressResponse(
        task_id=str(task_id),
        runs=runs,
        overall_percent=overall,
        source="progress_api",
    )
