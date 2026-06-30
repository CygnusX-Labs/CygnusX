"""数据下载路由 — EBI/NCBI 测序数据下载入口。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.download import DownloadRequest
from omichub.application.schemas.task import TaskListResponse, TaskResponse
from omichub.application.services.download_service import DownloadService
from omichub.core.config import get_settings
from omichub.core.exceptions import ValidationError

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
