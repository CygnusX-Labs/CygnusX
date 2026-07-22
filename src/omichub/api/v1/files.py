"""文件路由 — 列表 / 分块上传 / 配额 / 下载 / 删除 / 目录 / 样本"""

import uuid
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
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
from omichub.core.exceptions import ValidationError
from omichub.infrastructure.config.storage_config import get_user_chat_upload_dir

router = APIRouter()

# 聊天文件上传允许/禁止的扩展名
_CHAT_UPLOAD_BLOCKED_SUFFIXES = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".com",
        ".scr",
        ".msi",
        ".dll",
        ".sh",
        ".bash",
        ".zsh",
        ".csh",
        ".fish",
        ".ps1",
        ".vbs",
        ".js",
        ".jar",
        ".apk",
        ".app",
        ".dmg",
    }
)
_CHAT_UPLOAD_ALLOWED_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".bmp",
        ".ico",
        ".pdf",
        ".txt",
        ".md",
        ".doc",
        ".docx",
        ".csv",
        ".tsv",
        ".json",
        ".yaml",
        ".yml",
        ".fastq",
        ".fq",
        ".fasta",
        ".fa",
        ".fna",
        ".bam",
        ".cram",
        ".sam",
        ".vcf",
        ".gff",
        ".gtf",
        ".bed",
        ".h5ad",
        ".rds",
        ".gz",
        ".zip",
        ".tar",
        ".bz2",
        ".xz",
    }
)


def _validate_chat_upload_filename(filename: str | None) -> None:
    """校验聊天上传文件名：必须带扩展名，禁止可执行文件。"""
    if not filename:
        raise ValidationError("文件名不能为空")
    suffixes = [s.lower() for s in Path(filename).suffixes]
    if not suffixes:
        raise ValidationError("上传文件必须带扩展名")
    for suffix in suffixes:
        if suffix in _CHAT_UPLOAD_BLOCKED_SUFFIXES:
            raise ValidationError(f"禁止上传可执行文件: {suffix}")
    if suffixes[-1] not in _CHAT_UPLOAD_ALLOWED_SUFFIXES:
        raise ValidationError(f"不支持的文件类型: {suffixes[-1]}")


def get_file_service(db: DbSession) -> FileService:
    """获取文件服务实例（注入 DB 会话）"""
    return FileService(db)


FileServiceDep = Annotated[FileService, Depends(get_file_service)]


@router.get("", response_model=FileListResponse, summary="获取文件列表")
async def list_files(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
    directory: Annotated[str | None, Query(description="按目录过滤，空串=根目录")] = None,
    source: Annotated[str | None, Query(description="按来源过滤: upload/pipeline/blast/enrichment 等")] = None,
) -> FileListResponse:
    """获取当前用户的文件列表（可按目录或来源过滤，按创建时间倒序）"""
    return await service.list_files(UUID(current_user_id), directory=directory, source=source)


@router.get("/tree", summary="统一文件树")
async def file_tree(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
) -> dict[str, Any]:
    """聚合视图：按来源分组返回用户所有文件，供前端渲染统一文件树。"""
    return await service.get_file_tree(UUID(current_user_id))


@router.get("/quota", response_model=QuotaResponse, summary="获取存储配额")
async def get_quota(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
) -> QuotaResponse:
    """获取当前用户存储配额与已用空间"""
    return await service.get_quota(UUID(current_user_id))


@router.get("/preview", summary="预览文件内容")
async def preview_file(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
    path: Annotated[str, Query(description="相对于用户数据根目录的文件路径")],
    max_lines: Annotated[int, Query(ge=1, le=500, description="最多返回行数")] = 50,
) -> dict[str, Any]:
    """读取用户目录下文本文件的前 N 行（供 MCP Server / AI 助手查看分析结果）。"""
    from omichub.core.config import get_settings

    settings = get_settings()
    user_root = Path(settings.storage_path) / "users" / current_user_id
    target = (user_root / path).resolve()

    if not str(target).startswith(str(user_root.resolve())):
        raise ValidationError("路径越权")
    if not target.is_file():
        raise ValidationError("文件不存在")

    max_bytes = 200 * 1024
    if target.stat().st_size > max_bytes * 2:
        return {
            "path": path,
            "truncated": True,
            "total_size": target.stat().st_size,
            "lines": [],
            "message": f"文件过大 ({target.stat().st_size} bytes)，仅返回前 {max_lines} 行",
        }

    lines: list[str] = []
    async with await anyio.open_file(target, mode="r", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            lines.append(line.rstrip("\n"))

    return {
        "path": path,
        "truncated": len(lines) >= max_lines,
        "total_size": target.stat().st_size,
        "lines": lines,
    }


@router.post("/sync", response_model=SyncResponse, summary="同步磁盘文件到文件列表")
async def sync_files(
    current_user_id: CurrentUserId,
    service: FileServiceDep,
) -> SyncResponse:
    """对账当前用户目录与 file_records，并重算配额。

    用于手动放入文件、旧任务未登记产物、手工删除物理文件后的页面自愈。
    返回新增、清理和显示名修正统计。
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
) -> dict[str, Any]:
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
    return await service.list_files_for_picker(
        UUID(current_user_id), directory=directory, file_type=file_type
    )


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
) -> dict[str, Any]:
    """取消上传：删除会话与临时分片"""
    await service.cancel_upload(UUID(current_user_id), upload_id)
    return {"deleted": True}


@router.post("/chat-upload", summary="聊天文件上传（供 AI 多模态/附件）")
async def upload_chat_file(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008 — FastAPI 上传参数标准写法
) -> dict[str, Any]:
    """接收聊天附件，保存到用户隔离目录并返回访问 URL。

    用户身份直接取自 AuthMiddleware 注入的 request.state.user_id，
    避免上传接口重复查询数据库，降低抖动/版本校验带来的失败面。
    """
    current_user_id: str = getattr(request.state, "user_id", "") or ""
    if not current_user_id:
        from omichub.core.exceptions import AuthenticationError

        raise AuthenticationError("无法识别当前用户")

    _validate_chat_upload_filename(file.filename)
    upload_dir = get_user_chat_upload_dir(current_user_id)

    suffix = Path(file.filename or "").suffix
    file_id = uuid.uuid4().hex
    filename = f"{file_id}{suffix}"
    dest = upload_dir / filename
    body = await file.read()
    async with await anyio.open_file(dest, "wb") as buffer:
        await buffer.write(body)

    return {
        "id": file_id,
        "name": file.filename or filename,
        "url": f"/api/v1/files/chat-upload/{current_user_id}/{filename}",
        "mime_type": file.content_type or "application/octet-stream",
    }


@router.get("/chat-upload/{user_id}/{filename}", summary="下载聊天附件")
async def download_chat_file(
    request: Request,
    user_id: str,
    filename: str,
) -> FileResponse:
    """下载聊天上传的附件（仅允许访问当前用户自己的聊天文件）。"""
    current_user_id: str = getattr(request.state, "user_id", "") or ""
    if not current_user_id or user_id != current_user_id:
        from omichub.core.exceptions import AuthorizationError

        raise AuthorizationError("无权访问该附件")
    upload_dir = get_user_chat_upload_dir(current_user_id)
    # 防止目录遍历：仅取 basename
    safe_name = Path(filename).name
    path = upload_dir / safe_name
    if not path.is_file():
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
) -> dict[str, Any]:
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
