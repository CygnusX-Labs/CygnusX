"""项目路由 —— 管理用户的分析项目。"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cygnusx.api.deps import CurrentJwtUserId, CurrentUserId, DbSession
from cygnusx.application.schemas.project import ProjectCapabilityStatus, ProjectOverviewResponse
from cygnusx.application.services.project_overview_service import ProjectOverviewService
from cygnusx.application.services.project_service import ProjectService

router = APIRouter()


def get_project_service(db: DbSession) -> ProjectService:
    return ProjectService(db)


def get_project_overview_service(db: DbSession) -> ProjectOverviewService:
    return ProjectOverviewService(db)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
ProjectOverviewServiceDep = Annotated[ProjectOverviewService, Depends(get_project_overview_service)]


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    description: str = Field(default="", max_length=2000, description="项目描述（可选）")
    customer: str = Field(default="", max_length=200, description="客户名称（可选）")


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    status: Literal["active", "completed", "handed_over"] | None = Field(
        None, description="项目状态：active/completed/handed_over"
    )
    # RFC 7396: omitted keys stay unchanged; null removes a key.
    settings: dict[str, Any] | None = Field(None, description="项目级设置 JSON 对象")


@router.get("", summary="列出用户项目")
async def list_projects(
    current_user_id: CurrentUserId,
    service: ProjectServiceDep,
) -> list[dict[str, Any]]:
    """只读返回当前用户的分析项目；磁盘导入使用显式同步端点。"""
    from uuid import UUID

    return await service.list_projects(UUID(current_user_id))


@router.get("/count", summary="项目计数")
async def count_projects(
    current_user_id: CurrentUserId,
    service: ProjectServiceDep,
) -> dict[str, int]:
    """返回当前用户的项目数量（供 OverviewStats 等组件使用）。"""
    from uuid import UUID

    return {"count": await service.count_projects(UUID(current_user_id))}


@router.post("", status_code=201, summary="创建项目")
async def create_project(
    current_user_id: CurrentUserId,
    service: ProjectServiceDep,
    req: ProjectCreateRequest,
) -> dict[str, Any]:
    """创建新的分析项目。自动生成路径安全的 slug 并同步创建对应目录。"""
    from uuid import UUID

    try:
        return await service.create_project(
            UUID(current_user_id), req.name, req.description, req.customer
        )
    except Exception as exc:
        from cygnusx.core.exceptions import ConflictError, ValidationError

        if isinstance(exc, (ConflictError, ValidationError)):
            raise HTTPException(
                status_code=400 if isinstance(exc, ValidationError) else 409, detail=str(exc)
            ) from exc
        raise


@router.post("/sync-from-disk", summary="显式同步当前用户的历史项目目录")
async def sync_projects_from_disk(
    current_user_id: CurrentJwtUserId, service: ProjectServiceDep
) -> dict[str, int]:
    from uuid import UUID

    return await service.sync_from_disk(UUID(current_user_id))


@router.get("/{project_id}/capability-status", response_model=ProjectCapabilityStatus)
async def project_capability_status(
    project_id: str, current_user_id: CurrentUserId, service: ProjectServiceDep
) -> ProjectCapabilityStatus:
    from uuid import UUID

    try:
        return await service.capability_status(UUID(current_user_id), UUID(project_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的项目 ID") from exc


@router.get("/{project_id}", summary="获取项目详情")
async def get_project(
    current_user_id: CurrentUserId,
    service: ProjectServiceDep,
    project_id: str,
) -> dict[str, Any]:
    """获取单个项目的详细信息。"""
    from uuid import UUID

    try:
        return await service.get_project(UUID(current_user_id), UUID(project_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的项目 ID") from exc
    except Exception as exc:
        from cygnusx.core.exceptions import NotFoundError

        if isinstance(exc, NotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise


@router.get(
    "/{project_id}/overview",
    response_model=ProjectOverviewResponse,
    summary="项目总览（历史分析）",
)
async def get_project_overview(
    current_user_id: CurrentUserId,
    service: ProjectOverviewServiceDep,
    project_id: str,
    session_limit: int = Query(50, ge=1, le=200, description="会话列表每页条数"),
    session_offset: int = Query(0, ge=0, description="会话列表偏移"),
    session_status: Literal["active", "archived", "deleted"] = Query(
        "active", description="会话状态过滤：active/archived/deleted"
    ),
) -> dict[str, Any]:
    """聚合项目元数据、项目下的聊天会话与磁盘 runs 目录中的历史分析运行。"""
    from uuid import UUID

    try:
        return await service.get_overview(
            UUID(current_user_id),
            UUID(project_id),
            session_limit=session_limit,
            session_offset=session_offset,
            session_status=session_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的项目 ID") from exc
    except Exception as exc:
        from cygnusx.core.exceptions import NotFoundError

        if isinstance(exc, NotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise


@router.patch("/{project_id}", summary="更新项目")
async def update_project(
    current_user_id: CurrentUserId,
    service: ProjectServiceDep,
    project_id: str,
    req: ProjectUpdateRequest,
) -> dict[str, Any]:
    """原子修改名称/描述/状态和 Merge Patch 设置，保留 slug 与物理路径。"""
    from uuid import UUID

    from cygnusx.core.exceptions import NotFoundError
    from cygnusx.core.exceptions import ValidationError as DomainValidationError

    try:
        return await service.update_project(
            UUID(current_user_id), UUID(project_id), req.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的项目 ID") from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if isinstance(exc, NotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise


@router.delete("/{project_id}", status_code=204, summary="删除项目")
async def delete_project(
    current_user_id: CurrentUserId,
    service: ProjectServiceDep,
    project_id: str,
) -> None:
    """删除项目（仅清 DB 记录，物理文件保留）。"""
    from uuid import UUID

    try:
        await service.delete_project(UUID(current_user_id), UUID(project_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的项目 ID") from exc
    except Exception as exc:
        from cygnusx.core.exceptions import NotFoundError

        if isinstance(exc, NotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise
