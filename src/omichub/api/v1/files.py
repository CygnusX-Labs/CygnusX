"""文件路由"""

from typing import Annotated

from fastapi import APIRouter, Depends

from omichub.api.deps import CurrentUserId
from omichub.application.schemas.file import FileListResponse
from omichub.application.services.file_service import FileService

router = APIRouter()


def get_file_service() -> FileService:
    """获取文件服务实例"""
    return FileService()


FileServiceDep = Annotated[FileService, Depends(get_file_service)]


@router.get("", response_model=FileListResponse, summary="获取文件列表")
async def list_files(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
) -> FileListResponse:
    """获取当前用户的上传文件列表"""
    return service.list_files(current_user_id)


@router.get("/samples")
async def list_samples() -> dict[str, str]:
    """获取样本列表"""
    return {"message": "list samples"}


@router.post("/upload")
async def upload_file() -> dict[str, str]:
    """上传文件"""
    return {"message": "upload file"}


@router.get("/{file_id}/download")
async def download_file(file_id: str) -> dict[str, str]:
    """下载文件"""
    return {"file_id": file_id}
