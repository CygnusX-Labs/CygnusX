"""文档与知识库 API"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from omichub.api.deps import CurrentUserId
from omichub.application.services.docs_service import DocsService
from omichub.core.exceptions import AuthorizationError, ValidationError

router = APIRouter()

service = DocsService()


async def require_admin(current_user_id: CurrentUserId) -> None:
    """校验当前用户为管理员（沿用本仓 admin router 既有写法）。"""
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


class DocContentUpdate(BaseModel):
    """文档正文更新请求"""

    content: str = Field(description="新的 Markdown 正文")


@router.get("/knowledge", tags=["Docs"])
async def list_knowledge() -> dict[str, Any]:
    """获取实验室知识库导航列表"""
    return service.list_knowledge()


@router.get("/knowledge/{doc_id}", tags=["Docs"])
async def get_knowledge_doc(doc_id: str) -> dict[str, Any]:
    """获取指定知识库文档内容"""
    return service.get_knowledge_doc(doc_id)


@router.put("/knowledge/{doc_id}", tags=["Docs"], summary="保存知识库文档")
async def save_knowledge_doc(
    doc_id: str,
    payload: DocContentUpdate,
    _admin: AdminRequired,
) -> dict[str, Any]:
    """保存知识库文档正文（仅管理员，落盘 .md 文件，重启后自动加载）。"""
    if not payload.content:
        raise ValidationError("正文不能为空")
    return service.save_knowledge_doc(doc_id, payload.content)


_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/knowledge/upload", tags=["Docs"], summary="上传知识库图片")
async def upload_knowledge_image(
    file: Annotated[UploadFile, File(description="图片文件")],
    _admin: AdminRequired,
) -> dict[str, str]:
    """上传知识库配图，保存到 docs/knowledge/figure，返回可引用的静态 URL。"""
    if not file.filename:
        raise ValidationError("未提供文件名")

    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise ValidationError(f"不支持的图片格式: {ext}")

    content = await file.read()
    if len(content) > _MAX_IMAGE_SIZE:
        raise ValidationError("图片大小不能超过 10MB")

    upload_dir = anyio.Path("docs/knowledge/figure")
    await upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    dest = upload_dir / filename
    await dest.write_bytes(content)

    return {"url": f"/docs-static/knowledge/figure/{filename}", "filename": filename}


@router.get("/docs", tags=["Docs"])
async def list_docs() -> dict[str, Any]:
    """获取文档中心导航列表"""
    return service.list_docs()


@router.get("/docs/{doc_id}", tags=["Docs"])
async def get_doc(doc_id: str) -> dict[str, Any]:
    """获取指定文档内容"""
    return service.get_doc(doc_id)
