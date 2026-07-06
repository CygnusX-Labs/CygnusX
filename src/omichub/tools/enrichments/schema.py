"""富集分析（KEGG / GO）Schema —— 物种选项 / 富集结果行 / 提交结果 DTO。

字段命名与前端 `frontend/src/types/enrichment.ts` 对齐：
- SpeciesOption 用 `label`（非方案文档的 display_name），以前端为准；
- EnrichmentResult.plotly_json 为 `{ data, layout }`，供 Plotly.js 直接 newPlot。
"""

from __future__ import annotations

from typing import Any

from omichub.application.schemas.base import OmicsHubBaseSchema


class SpeciesOptionDTO(OmicsHubBaseSchema):
    """物种下拉选项（前端 SpeciesOption）。

    仅暴露前端渲染所需字段；kegg_rdata / kegg_supported 等离线扩展字段
    留在配置层不外泄，待后续离线 fallback 启用时再加。
    """

    id: str
    label: str
    kegg_code: str
    org_db: str
    id_type: str


class SpeciesListResponse(OmicsHubBaseSchema):
    """GET /enrichment/species 响应包络（前端解 { data: [...] }）。"""

    data: list[SpeciesOptionDTO] = []


class EnrichmentRowDTO(OmicsHubBaseSchema):
    """单条富集结果（前端 EnrichmentRow）。

    字段映射自 clusterProfiler::enrichKEGG 输出列：
      ID → id, Description → description, GeneRatio → gene_ratio,
      pvalue → pvalue, p.adjust → p_adjust, Count → count。
    """

    id: str
    description: str
    gene_ratio: str
    pvalue: float
    p_adjust: float
    count: int


class EnrichmentResultDTO(OmicsHubBaseSchema):
    """POST /enrichment/submit 响应。

    - task_id：UUID 关联 ID（同时是结果目录名 / CSV 导出文件名后缀）；v1 不落库 Task。
    - plotly_json：`{ data, layout }`，前端 Plotly.newPlot 直接消费；无结果时为 None。
    - table_data：完整富集结果行（前端分页展示 + CSV 导出）。
    """

    task_id: str
    plotly_json: dict[str, Any] | None = None
    table_data: list[EnrichmentRowDTO] = []
