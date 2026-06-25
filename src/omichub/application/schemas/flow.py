"""流程相关 DTO 模型"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from omichub.application.schemas.base import OmicsHubBaseSchema
from omichub.domain.flow.entities import FlowConfig, Parameter


class FlowMetaDTO(OmicsHubBaseSchema):
    """流程元信息 DTO"""

    id: str
    name: str
    category: str
    version: str
    description: str
    author: str | None = None
    tags: list[str] = []
    icon: str | None = None
    docs_url: str | None = None


class FlowListItemDTO(OmicsHubBaseSchema):
    """流程列表项 DTO — 用于列表展示"""

    id: str
    name: str
    category: str
    version: str
    description: str
    author: str | None = None
    tags: list[str] = []
    icon: str | None = None
    docs_url: str | None = None
    parameter_count: int = 0
    has_sample_sheet: bool = False


class FlowDetailDTO(OmicsHubBaseSchema):
    """流程详情 DTO — 完整 FlowConfig"""

    meta: FlowMetaDTO
    parameters: list[Parameter]
    execution: dict[str, Any]
    sample_sheet: dict[str, Any] | None = None


class FlowListResponse(OmicsHubBaseSchema):
    """流程列表响应"""

    items: list[FlowListItemDTO]
    total: int


class FlowReloadResponse(OmicsHubBaseSchema):
    """流程热重载响应"""

    loaded: int
    message: str


def flow_config_to_list_item(config: FlowConfig) -> FlowListItemDTO:
    """FlowConfig → FlowListItemDTO"""
    return FlowListItemDTO(
        id=config.meta.id,
        name=config.meta.name,
        category=config.meta.category,
        version=config.meta.version,
        description=config.meta.description,
        author=config.meta.author,
        tags=config.meta.tags,
        icon=config.meta.icon,
        docs_url=config.meta.docs_url,
        parameter_count=len(config.parameters),
        has_sample_sheet=config.sample_sheet is not None,
    )


def flow_config_to_detail(config: FlowConfig) -> FlowDetailDTO:
    """FlowConfig → FlowDetailDTO"""
    return FlowDetailDTO(
        meta=FlowMetaDTO(
            id=config.meta.id,
            name=config.meta.name,
            category=config.meta.category,
            version=config.meta.version,
            description=config.meta.description,
            author=config.meta.author,
            tags=config.meta.tags,
            icon=config.meta.icon,
            docs_url=config.meta.docs_url,
        ),
        parameters=config.parameters,
        execution=config.execution.model_dump(),
        sample_sheet=config.sample_sheet.model_dump() if config.sample_sheet else None,
    )


def export_flow_json_schema() -> dict[str, Any]:
    """导出 FlowConfig 的 JSON Schema (Draft 2020-12) — 供前端使用"""
    adapter = TypeAdapter(FlowConfig)
    return adapter.json_schema()


def export_parameter_json_schema() -> dict[str, Any]:
    """导出 Parameter 的独立 JSON Schema — 供前端动态表单校验"""
    adapter = TypeAdapter(Parameter)
    return adapter.json_schema()
