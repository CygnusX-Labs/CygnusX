"""文件路由 — 列表 / 分块上传 / 配额 / 下载 / 删除 / 目录 / 样本"""

import os
import uuid
from pathlib import Path
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.file import (
    DataFileDTO,
    DirectoryCreateRequest,
    DirectoryDTO,
    FileListResponse,
    FilePickerItemDTO,
    MoveFileRequest,
    QuotaResponse,
    SampleCreateRequest,
    SampleDTO,
    SampleListResponse,
    SyncResponse,
    UploadChunkResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadMergeRequest,
    UploadMergeResponse,
)
from omichub.application.services.file_service import FileService

router = APIRouter()


def get_file_service(db: DbSession) -> FileService:
    """获取文件服务实例（注入 DB 会话）"""
    return FileService(db)


FileServiceDep = Annotated[FileService, Depends(get_file_service)]


@router.get("", response_model=FileListResponse, summary="获取文件列表")
async def list_files(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
    directory: Annotated[str | None, Query(description="按目录过滤，空串=根目录")] = None,
) -> FileListResponse:
    """获取当前用户的文件列表（可按目录过滤，按创建时间倒序）"""
    return await service.list_files(UUID(current_user_id), directory=directory)


@router.get("/quota", response_model=QuotaResponse, summary="获取存储配额")
async def get_quota(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
) -> QuotaResponse:
    """获取当前用户存储配额与已用空间"""
    return await service.get_quota(UUID(current_user_id))


@router.post("/sync", response_model=SyncResponse, summary="同步磁盘文件到文件列表")
async def sync_files(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
) -> SyncResponse:
    """扫描当前用户目录，把磁盘有但未登记的文件登记进 file_records（只增不删），并重算配额。

    用于手动放入的文件、旧任务未登记产物等。返回新增文件数与字节数。
    """
    return await service.sync_user_files(UUID(current_user_id))


# ===== 用户目录 =====
@router.get("/directories", response_model=list[DirectoryDTO], summary="目录列表")
async def list_directories(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
) -> list[DirectoryDTO]:
    """获取当前用户的所有目录（前端组装成树）"""
    return await service.list_directories(UUID(current_user_id))


@router.post("/directories", response_model=DirectoryDTO, summary="创建目录")
async def create_directory(
    current_user_id: CurrentUserId,
    req: DirectoryCreateRequest,
    service: FileServiceDep,
) -> DirectoryDTO:
    """创建用户自定义目录（自动建物理目录）"""
    return await service.create_directory(UUID(current_user_id), req)


@router.delete("/directories", summary="删除目录")
async def delete_directory(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
    path: Annotated[str, Query(description="要删除的目录路径")] = "",
) -> dict:
    """删除目录（含其下文件回退到根目录）"""
    await service.delete_directory(UUID(current_user_id), path)
    return {"deleted": True}


@router.get("/picker", response_model=list[FilePickerItemDTO], summary="文件选择器数据")
async def list_files_for_picker(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
    directory: Annotated[str | None, Query()] = None,
    file_type: Annotated[str | None, Query(description="按文件类型过滤，如 fastq/bam")] = None,
) -> list[FilePickerItemDTO]:
    """供分析文件选择器：返回文件 + 绝对路径"""
    return await service.list_files_for_picker(UUID(current_user_id), directory=directory, file_type=file_type)


@router.put("/{file_id}/move", response_model=DataFileDTO, summary="移动文件到目录")
async def move_file(
    current_user_id: CurrentUserId,
    file_id: UUID,
    req: MoveFileRequest,
    service: FileServiceDep,
) -> DataFileDTO:
    """移动文件到指定目录（空串 = 根目录）"""
    return await service.move_file(UUID(current_user_id), file_id, req.directory)


@router.post("/upload/init", response_model=UploadInitResponse, summary="初始化分块上传")
async def init_upload(
    current_user_id: CurrentUserId,
    req: UploadInitRequest,
    service: FileServiceDep,
) -> UploadInitResponse:
    """初始化分块上传：配额前置校验 + 秒传/断点续传判定。

    配额超限返回 403。
    """
    return await service.init_upload(UUID(current_user_id), req)


@router.post("/upload/chunk", response_model=UploadChunkResponse, summary="上传分片")
async def upload_chunk(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
    upload_id: UUID = Form(...),  # noqa: B008
    index: int = Form(...),  # noqa: B008
    md5: str = Form(...),  # noqa: B008
    chunk: UploadFile = File(...),  # noqa: B008
) -> UploadChunkResponse:
    """接收单个文件分片，校验 MD5 后落盘并记录传输状态"""
    chunk_bytes = await chunk.read()
    return await service.save_chunk(UUID(current_user_id), upload_id, index, chunk_bytes, md5)


@router.post("/upload/merge", response_model=UploadMergeResponse, summary="合并分片")
async def merge_upload(
    current_user_id: CurrentUserId,
    req: UploadMergeRequest,
    service: FileServiceDep,
) -> UploadMergeResponse:
    """合并全部分片、完整性校验、原子累加配额"""
    return await service.merge_upload(UUID(current_user_id), req.upload_id)


@router.delete("/upload/{upload_id}", summary="取消上传")
async def cancel_upload(
    current_user_id: CurrentUserId,
    upload_id: UUID,
    service: FileServiceDep,
) -> dict:
    """取消上传：删除会话与临时分片"""
    await service.cancel_upload(UUID(current_user_id), upload_id)
    return {"deleted": True}


@router.post("/chat-upload", summary="聊天文件上传（供 AI 多模态/附件）")
async def upload_chat_file(
    current_user_id: CurrentUserId,
    file: UploadFile = File(...),  # noqa: B008 — FastAPI 上传参数标准写法
) -> dict:
    """接收聊天附件，保存到独立目录并返回访问 URL。"""
    upload_dir = "data/uploads/chat"
    os.makedirs(upload_dir, exist_ok=True)

    suffix = Path(file.filename or "").suffix
    file_id = uuid.uuid4().hex
    filename = f"{file_id}{suffix}"
    dest = os.path.join(upload_dir, filename)
    body = await file.read()
    async with await anyio.open_file(dest, "wb") as buffer:
        await buffer.write(body)

    return {
        "id": file_id,
        "name": file.filename or filename,
        "url": f"/api/v1/files/chat-upload/{filename}",
        "mime_type": file.content_type or "application/octet-stream",
    }


@router.get("/chat-upload/{filename}", summary="下载聊天附件")
async def download_chat_file(
    current_user_id: CurrentUserId,
    filename: str,
) -> FileResponse:
    """下载聊天上传的附件（仅允许访问 chat 目录下文件）。"""
    upload_dir = anyio.Path("data/uploads/chat")
    # 防止目录遍历
    safe_name = Path(filename).name
    path = upload_dir / safe_name
    if not await path.is_file():
        from omichub.core.exceptions import NotFoundError
        raise NotFoundError("文件不存在")
    return FileResponse(str(path), filename=safe_name)


@router.get("/{file_id}/download", summary="下载文件")
async def download_file(
    current_user_id: CurrentUserId,
    file_id: UUID,
    service: FileServiceDep,
) -> FileResponse:
    """下载文件（强制归属校验，越权返回 404）"""
    path = await service.get_file_path(UUID(current_user_id), file_id)
    return FileResponse(path, filename=path.name)


@router.delete("/{file_id}", summary="删除文件")
async def delete_file(
    current_user_id: CurrentUserId,
    file_id: UUID,
    service: FileServiceDep,
) -> dict:
    """删除文件并扣减配额"""
    await service.delete_file(UUID(current_user_id), file_id)
    return {"deleted": True}


# ===== 样本（供流程引擎读取文件路径） =====
@router.get("/samples", response_model=SampleListResponse, summary="获取样本列表")
async def list_samples(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
) -> SampleListResponse:
    return await service.list_samples(UUID(current_user_id))


@router.post("/samples", response_model=SampleDTO, summary="创建样本")
async def create_sample(
    current_user_id: CurrentUserId,
    req: SampleCreateRequest,
    service: FileServiceDep,
) -> SampleDTO:
    """创建样本并关联已上传文件（校验文件归属）"""
    return await service.create_sample(UUID(current_user_id), req)
