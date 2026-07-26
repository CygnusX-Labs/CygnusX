"""Skill 管理 API — 管理员 CRUD + SKILL.md 标准导入（四入口 + 预览确认）"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile

from omichub.api.deps import DbSession
from omichub.api.v1.admin.users import AdminRequired
from omichub.application.schemas.skill import (
    CreateSkillDTO,
    GithubImportRequest,
    JsonImportRequest,
    SkillDTO,
    SkillImportConfirmDTO,
    SkillImportPreviewDTO,
    SkillMarketplaceItemDTO,
    SkillUpdateCheckDTO,
    UpdateSkillDTO,
)
from omichub.application.services.skill_import_service import SkillImportService
from omichub.application.services.skill_service import SkillService
from omichub.core.exceptions import BusinessError
from omichub.infrastructure.skills.skillmd import SkillParseError

router = APIRouter()

MAX_ZIP_UPLOAD_BYTES = 6 * 1024 * 1024


def get_skill_service(db: DbSession) -> SkillService:
    return SkillService(db)


def get_skill_import_service(db: DbSession) -> SkillImportService:
    return SkillImportService(db)


SkillServiceDep = Annotated[SkillService, Depends(get_skill_service)]
SkillImportServiceDep = Annotated[SkillImportService, Depends(get_skill_import_service)]


def _wrap_parse_error(exc: SkillParseError) -> BusinessError:
    return BusinessError(f"技能解析失败：{exc}")


@router.get("", response_model=list[SkillDTO], summary="技能列表")
async def list_skills(
    _admin: AdminRequired,
    service: SkillServiceDep,
    active_only: bool = False,
) -> list[SkillDTO]:
    return await service.list_skills(active_only=active_only)


@router.post("", response_model=SkillDTO, status_code=201, summary="创建技能")
async def create_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    req: CreateSkillDTO,
) -> SkillDTO:
    return await service.create_skill(req)


# ---------- 技能市场（内置可安装技能） ----------


@router.get(
    "/marketplace",
    response_model=list[SkillMarketplaceItemDTO],
    summary="技能市场列表",
)
async def list_marketplace(
    _admin: AdminRequired,
    service: SkillImportServiceDep,
) -> list[SkillMarketplaceItemDTO]:
    return await service.list_marketplace()


@router.post(
    "/marketplace/{skill_id}/install",
    response_model=SkillDTO,
    summary="安装市场技能",
)
async def install_marketplace(
    _admin: AdminRequired,
    service: SkillImportServiceDep,
    skill_id: str,
    overwrite: bool = False,
) -> SkillDTO:
    return await service.install_marketplace(skill_id, overwrite=overwrite)


# ---------- 导入：四入口统一先预览、确认后入库 ----------


@router.post(
    "/import/github",
    response_model=SkillImportPreviewDTO,
    summary="从 GitHub 仓库/子目录解析技能（预览）",
)
async def import_from_github(
    _admin: AdminRequired,
    service: SkillImportServiceDep,
    req: GithubImportRequest,
) -> SkillImportPreviewDTO:
    try:
        return await service.parse_from_github(req.url)
    except SkillParseError as exc:
        raise _wrap_parse_error(exc) from exc


@router.post(
    "/import/zip",
    response_model=SkillImportPreviewDTO,
    summary="上传 zip 技能包（预览）",
)
async def import_from_zip(
    _admin: AdminRequired,
    service: SkillImportServiceDep,
    file: UploadFile = File(...),
) -> SkillImportPreviewDTO:
    data = await file.read()
    if len(data) > MAX_ZIP_UPLOAD_BYTES:
        raise BusinessError(f"上传文件超过 {MAX_ZIP_UPLOAD_BYTES // 1024 // 1024}MB 上限")
    try:
        return await service.parse_from_zip(data)
    except SkillParseError as exc:
        raise _wrap_parse_error(exc) from exc


@router.post(
    "/import/json",
    response_model=SkillImportPreviewDTO,
    summary="JSON 粘贴导入（兼容旧格式，预览）",
)
async def import_from_json(
    _admin: AdminRequired,
    service: SkillImportServiceDep,
    req: JsonImportRequest,
) -> SkillImportPreviewDTO:
    try:
        return await service.parse_from_json(req.text)
    except SkillParseError as exc:
        raise _wrap_parse_error(exc) from exc


@router.post(
    "/import/confirm",
    response_model=SkillDTO,
    summary="确认导入（预览通过后入库）",
)
async def confirm_import(
    _admin: AdminRequired,
    service: SkillImportServiceDep,
    req: SkillImportConfirmDTO,
) -> SkillDTO:
    try:
        return await service.confirm_import(req.preview, overwrite=req.overwrite)
    except SkillParseError as exc:
        raise _wrap_parse_error(exc) from exc


@router.get("/{skill_id}", response_model=SkillDTO, summary="技能详情")
async def get_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    skill_id: str,
) -> SkillDTO:
    return await service.get_skill(skill_id)


@router.put("/{skill_id}", response_model=SkillDTO, summary="更新技能")
async def update_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    skill_id: str,
    req: UpdateSkillDTO,
) -> SkillDTO:
    return await service.update_skill(skill_id, req)


@router.delete("/{skill_id}", summary="删除技能")
async def delete_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    skill_id: str,
) -> dict[str, bool]:
    await service.delete_skill(skill_id)
    return {"deleted": True}


@router.post("/{skill_id}/toggle", response_model=SkillDTO, summary="启用/停用技能")
async def toggle_skill(
    _admin: AdminRequired,
    service: SkillServiceDep,
    skill_id: str,
) -> SkillDTO:
    return await service.toggle_skill(skill_id)


@router.post(
    "/{skill_id}/check-update",
    response_model=SkillUpdateCheckDTO,
    summary="检查上游更新",
)
async def check_update(
    _admin: AdminRequired,
    service: SkillImportServiceDep,
    skill_id: str,
) -> SkillUpdateCheckDTO:
    return await service.check_update(skill_id)
