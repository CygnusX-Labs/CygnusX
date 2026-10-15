"""报告中心路由"""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse, PlainTextResponse, Response

from cygnusx.api.deps import CurrentUserId, DbSession
from cygnusx.application.schemas.report import (
    ReportFilterParams,
    ReportJobResponse,
    ReportListResponse,
    ReportResponse,
    ReportSnapshotResponse,
    ReportVersionTreeResponse,
    ToggleStarRequest,
)
from cygnusx.application.services.report_service import ReportService
from cygnusx.application.services.reproducible_report_service import ReproducibleReportService

router = APIRouter()


def get_report_service(db: DbSession) -> ReportService:
    """获取报告服务实例"""
    return ReportService(db)


ReportServiceDep = Annotated[ReportService, Depends(get_report_service)]


@router.get("/jobs/{job_id}", response_model=ReportJobResponse, summary="获取报告生成状态")
async def get_report_job(
    job_id: UUID, current_user_id: CurrentUserId, db: DbSession
) -> ReportJobResponse:
    return await ReproducibleReportService(db).get_job(current_user_id, job_id)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=ReportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="安全重试报告生成",
)
async def retry_report_job(
    job_id: UUID, current_user_id: CurrentUserId, db: DbSession
) -> ReportJobResponse:
    return await ReproducibleReportService(db).retry(current_user_id, job_id)


@router.get(
    "/{report_id}/snapshot",
    response_model=ReportSnapshotResponse,
    summary="获取报告证据快照",
)
async def get_report_snapshot(
    report_id: UUID, current_user_id: CurrentUserId, db: DbSession
) -> ReportSnapshotResponse:
    return await ReproducibleReportService(db).get_snapshot_for_report(current_user_id, report_id)


@router.post(
    "/{report_id}/delivery",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="生成科研交付包",
)
async def build_delivery_package(
    report_id: UUID,
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> ReportResponse:
    report = await service.build_delivery_package(report_id, current_user_id)
    return await service.get_report(report.id, current_user_id)


@router.get("", response_model=ReportListResponse, summary="获取报告列表")
async def list_reports(
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
    task_id: Annotated[UUID | None, Query(description="任务 ID")] = None,
    keyword: Annotated[str | None, Query(description="关键词搜索")] = None,
    flow_id: Annotated[str | None, Query(description="流程 ID")] = None,
    status: Annotated[str | None, Query(description="状态")] = None,
    date_range: Annotated[str | None, Query(description="时间范围: 7d/30d/90d")] = None,
    is_starred: Annotated[bool | None, Query(description="是否收藏")] = None,
    page: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, description="每页条数")] = 10,
) -> ReportListResponse:
    """获取当前用户的报告列表"""
    params = ReportFilterParams(
        task_id=task_id,
        keyword=keyword,
        flow_id=flow_id,
        status=status,
        date_range=date_range,
        is_starred=is_starred,
        page=page,
        page_size=page_size,
    )
    return await service.list_reports(current_user_id, params)


@router.get("/stats", summary="获取用户报告统计")
async def get_report_stats(
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> dict[str, int]:
    """获取当前用户的报告统计概览"""
    return await service.stats(current_user_id)


@router.get(
    "/{report_id}/versions",
    response_model=ReportVersionTreeResponse,
    summary="获取报告版本树",
)
async def list_report_versions(
    report_id: UUID,
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> ReportVersionTreeResponse:
    """获取原报告及其全部 Studio 衍生版本。"""
    return await service.list_versions(report_id, current_user_id)


@router.get("/{report_id}", response_model=ReportResponse, summary="获取报告详情")
async def get_report(
    report_id: UUID,
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> ReportResponse:
    """获取指定报告详情"""
    return await service.get_report(report_id, current_user_id)


@router.get(
    "/{report_id}/preview",
    response_class=PlainTextResponse,
    summary="预览报告 HTML",
)
async def preview_report(
    report_id: UUID,
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> str:
    """获取报告 HTML 内容，用于 iframe 预览"""
    return await service.preview_html(report_id, current_user_id)


@router.get(
    "/{report_id}/files/{file_id}/download",
    summary="下载报告文件",
)
async def download_report_file(
    report_id: UUID,
    file_id: UUID,
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> Response:
    """下载报告关联文件"""
    detail = await service.get_report(report_id, current_user_id)
    if detail.report_kind in {"reproducibility", "delivery"} or service._backend.name != "local":
        content, name = await service.object_download(report_id, file_id, current_user_id)
        return Response(
            content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
                "X-Content-Type-Options": "nosniff",
            },
        )
    path = await service.download_file(report_id, file_id, current_user_id)
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/octet-stream",
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除报告")
async def delete_report(
    report_id: UUID,
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> None:
    """删除报告记录（不删除底层文件）"""
    await service.delete_report(report_id, current_user_id)


@router.patch("/{report_id}/star", response_model=ReportResponse, summary="收藏/取消收藏报告")
async def toggle_star(
    report_id: UUID,
    req: ToggleStarRequest,
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> ReportResponse:
    """切换报告收藏状态"""
    return await service.toggle_star(report_id, current_user_id, req.is_starred)


@router.patch("/{report_id}/read", response_model=ReportResponse, summary="标记报告已读")
async def mark_read(
    report_id: UUID,
    current_user_id: CurrentUserId,
    service: ReportServiceDep,
) -> ReportResponse:
    """标记报告为已读"""
    return await service.mark_read(report_id, current_user_id)
