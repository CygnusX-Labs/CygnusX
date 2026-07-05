"""报告中心 DTO 模型"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from omichub.application.schemas.base import OmicsHubBaseSchema, PaginationParams


class ReportFileResponse(OmicsHubBaseSchema):
    """报告文件响应"""

    id: UUID
    report_id: UUID
    name: str
    type: str
    size: int
    path: str
    is_primary: bool
    created_at: datetime


class ReportResponse(OmicsHubBaseSchema):
    """报告详情响应"""

    id: UUID
    task_id: UUID
    user_id: UUID
    flow_id: str
    flow_name: str
    flow_version: str
    flow_icon: str
    title: str
    description: str
    status: str
    sample_count: int
    duration: int
    created_at: datetime
    completed_at: datetime | None
    is_read: bool
    is_starred: bool
    files: list[ReportFileResponse] = []


class ReportListResponse(OmicsHubBaseSchema):
    """报告列表响应"""

    items: list[ReportResponse]
    total: int


class ReportFilterParams(PaginationParams):
    """报告列表过滤参数"""

    keyword: str | None = None
    flow_id: str | None = None
    status: str | None = None
    date_range: str | None = None  # 7d / 30d / 90d
    is_starred: bool | None = None


class ToggleStarRequest(OmicsHubBaseSchema):
    """收藏请求"""

    is_starred: bool
