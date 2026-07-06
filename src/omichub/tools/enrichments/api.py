"""富集分析（KEGG / GO）路由 —— 物种列表 + 提交分析。

- GET  /enrichment/species   返回 YAML 中 enabled 物种
- POST /enrichment/submit     multipart 提交，同步返回 Plotly JSON + 结果表

鉴权：所有接口要求登录（CurrentUserId）。结果落到 /data/omichub/users/{user_id}/
enrichment/{task_id}/，user_id 取自 JWT，不信任查询参数。

物种三字码 / OrgDb / ID 类型由后端按 species_id 从 YAML 权威解析，前端回传的同名
字段仅为展示，不参与容器调用（防篡改）。
"""

from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from omichub.api.deps import CurrentUserId
from omichub.tools.enrichments.schema import (
    EnrichmentResultDTO,
    SpeciesListResponse,
)
from omichub.tools.enrichments.service import EnrichmentService

# 路由元数据：供 omichub.tools.register_tool_routers 自动发现挂载
prefix = "/enrichment"
tags = ["Enrichment 富集分析"]

router = APIRouter()


@lru_cache(maxsize=1)
def get_enrichment_service() -> EnrichmentService:
    """获取 EnrichmentService 单例（无状态，配置自带 mtime 热重载）。"""
    return EnrichmentService()


EnrichmentServiceDep = Annotated[EnrichmentService, Depends(get_enrichment_service)]


@router.get("/species", response_model=SpeciesListResponse, summary="获取可用物种列表")
async def list_species(
    _user: CurrentUserId,
    service: EnrichmentServiceDep,
) -> SpeciesListResponse:
    """返回 YAML 中 enabled=true 的物种（前端下拉数据源）。"""
    species = service.list_species()
    return SpeciesListResponse(data=species)


@router.post("/submit", response_model=EnrichmentResultDTO, summary="提交富集分析任务")
async def submit_enrichment(
    current_user_id: CurrentUserId,
    service: EnrichmentServiceDep,
    species_id: Annotated[str, Form(description="物种 ID（YAML 中 id）")],
    gene_text: Annotated[str | None, Form(description="手动输入的基因 ID 列表，每行一个")] = None,
    gene_file: Annotated[UploadFile | None, File(description="基因 ID 文件 (.txt/.csv/.tsv)")] = None,
) -> EnrichmentResultDTO:
    """提交 KEGG 富集分析。

    基因列表支持文本（gene_text）或文件（gene_file）二选一；同时提供时以文件为准。
    物种参数由后端按 species_id 从配置解析，容器调用前不使用前端回传的 kegg_code 等。
    """
    text = gene_text
    if gene_file is not None:
        raw = await gene_file.read()
        await gene_file.close()
        text = raw.decode("utf-8", errors="replace")
    return await service.submit(
        user_id=current_user_id,
        species_id=species_id,
        gene_text=text,
    )
