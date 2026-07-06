"""富集分析应用服务 —— 物种列表 + 提交编排。

编排流程（submit）：
1. species_id 从 YAML 权威解析 kegg_code/org_db/id_type（不信任前端回传值）；
2. 生成 task_id（UUID）+ 结果目录 /data/omichub/users/{user_id}/enrichment/{task_id}/；
3. 基因列表落盘 gene_list.txt（每行一个，去空行去重）；
4. 调 EnrichmentDockerRunner 跑 R 容器，产出 kegg_result.csv；
5. 解析 CSV → EnrichmentRowDTO[]；构造 Plotly JSON（Top 20 dot plot）；
6. 容器非 0 退出 / 超时 → 抛 TaskExecutionError（带 stderr 摘要）。

v1 同步执行（前端一次拿全结果，不轮询）；task_id 仅作关联 ID 与结果目录名，不落库 Task。
后续可升级为 Celery 任务 + DB Task 聚合根（仿 download_service）。
"""

from __future__ import annotations

import asyncio
import csv
import math
import uuid
from pathlib import Path
from typing import Any

from omichub.core.config import get_settings
from omichub.core.exceptions import NotFoundError, TaskExecutionError, ValidationError
from omichub.tools.enrichments.config import (
    EnrichmentConfigManager,
    SpeciesConfig,
    config_manager,
)
from omichub.tools.enrichments.runner import (
    EnrichmentDockerRunner,
    EnrichmentRunParams,
    enrichment_runner,
)
from omichub.tools.enrichments.schema import (
    EnrichmentResultDTO,
    EnrichmentRowDTO,
    SpeciesOptionDTO,
)

# Plotly Top N 通路展示数
_TOP_N = 20
# stderr 摘要最大长度（避免超长错误回传前端）
_STDERR_TAIL = 800


class EnrichmentService:
    """富集分析服务。"""

    def __init__(
        self,
        manager: EnrichmentConfigManager | None = None,
        runner: EnrichmentDockerRunner | None = None,
    ) -> None:
        self._manager = manager or config_manager
        self._runner = runner or enrichment_runner
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # 物种列表
    # ------------------------------------------------------------------

    def list_species(self) -> list[SpeciesOptionDTO]:
        """返回 enabled 物种，display_name → label 对齐前端。"""
        return [
            SpeciesOptionDTO(
                id=s.id,
                label=s.display_name,
                kegg_code=s.kegg_code,
                org_db=s.org_db,
                id_type=s.id_type,
            )
            for s in self._manager.list_enabled_species()
        ]

    # ------------------------------------------------------------------
    # 提交分析
    # ------------------------------------------------------------------

    async def submit(
        self,
        user_id: str,
        species_id: str,
        gene_text: str | None,
    ) -> EnrichmentResultDTO:
        """提交 KEGG 富集分析，同步返回结果。"""
        species = self._require_species(species_id)
        genes = self._parse_genes(gene_text)
        if not genes:
            raise ValidationError("基因 ID 列表为空")

        task_id = uuid.uuid4().hex
        work_dir = self._work_dir(user_id, task_id)
        await asyncio.to_thread(work_dir.mkdir, parents=True, exist_ok=True)

        input_path = work_dir / "gene_list.txt"
        output_path = work_dir / "kegg_result.csv"
        await asyncio.to_thread(self._write_gene_list, input_path, genes)

        params = EnrichmentRunParams(
            input_path=str(input_path),
            output_path=str(output_path),
            kegg_code=species.kegg_code,
            org_db=species.org_db,
            id_type=species.id_type,
        )
        container_name = f"omichub-enrich-{task_id[:8]}"
        run_result = await self._runner.run(params, container_name)

        if run_result.returncode != 0:
            tail = run_result.stderr.strip()[-_STDERR_TAIL:] or run_result.stdout.strip()[-_STDERR_TAIL:]
            raise TaskExecutionError(
                f"富集分析失败 (exit={run_result.returncode}): {tail or '容器未给出错误信息'}"
            )

        rows = await asyncio.to_thread(self._read_result_csv, output_path)
        plotly_json = self._build_plotly_json(rows)
        return EnrichmentResultDTO(
            task_id=task_id,
            plotly_json=plotly_json,
            table_data=rows,
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _require_species(self, species_id: str) -> SpeciesConfig:
        species = self._manager.get_species(species_id)
        if species is None:
            raise NotFoundError(f"未知物种: {species_id}")
        if not species.enabled:
            raise ValidationError(f"物种已禁用: {species_id}")
        return species

    @staticmethod
    def _parse_genes(gene_text: str | None) -> list[str]:
        """解析基因列表：按行切分，去空白行，去重保序。"""
        if not gene_text:
            return []
        seen: set[str] = set()
        genes: list[str] = []
        for line in gene_text.splitlines():
            g = line.strip()
            if g and g not in seen:
                seen.add(g)
                genes.append(g)
        return genes

    @staticmethod
    def _write_gene_list(path: Path, genes: list[str]) -> None:
        """每行一个基因 ID，无表头（R 端 read.table(header=FALSE)$V1）。"""
        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(genes))
            f.write("\n")

    def _work_dir(self, user_id: str, task_id: str) -> Path:
        """结果目录：{data_mount}/users/{user_id}/enrichment/{task_id}/。"""
        return (
            Path(self._settings.enrichment_data_mount)
            / "users"
            / str(user_id)
            / "enrichment"
            / task_id
        )

    @staticmethod
    def _read_result_csv(path: Path) -> list[EnrichmentRowDTO]:
        """解析 clusterProfiler 输出 CSV → EnrichmentRowDTO[]。

        容错：pvalue/p.adjust/Count 解析失败时回退 0；空结果返回 []。
        """
        if not path.exists():
            return []
        rows: list[EnrichmentRowDTO] = []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                # p.adjust 缺列时回退 pvalue（部分导出工具不输出 p.adjust）
                p_adjust_val = raw.get("p.adjust")
                if p_adjust_val is None:
                    p_adjust_val = raw.get("pvalue")
                rows.append(
                    EnrichmentRowDTO(
                        id=(raw.get("ID") or "").strip(),
                        description=(raw.get("Description") or "").strip(),
                        gene_ratio=(raw.get("GeneRatio") or "").strip(),
                        pvalue=_to_float(raw.get("pvalue")),
                        p_adjust=_to_float(p_adjust_val),
                        count=_to_int(raw.get("Count")),
                    )
                )
        # 显著性升序（最显著在前），供图表与表格默认排序
        rows.sort(key=lambda r: r.p_adjust)
        return rows

    @staticmethod
    def _build_plotly_json(rows: list[EnrichmentRowDTO]) -> dict[str, Any] | None:
        """构造 Plotly dot plot JSON（Top N，最显著置顶）。无数据返回 None。"""
        if not rows:
            return None

        top = rows[:_TOP_N]
        # 反转：最显著排在列表末尾 → Plotly 默认 y 轴自下而上递增 → 置顶
        top = list(reversed(top))

        x: list[float] = []
        y: list[str] = []
        sizes: list[float] = []
        colors: list[float] = []
        text: list[str] = []
        for r in top:
            x.append(_gene_ratio_to_float(r.gene_ratio, r.count))
            y.append(r.description or r.id)
            sizes.append(min(8.0 + r.count * 2.0, 30.0))
            # p_adjust=0 时 -log10 无界，钳到 0 防溢出
            colors.append(-math.log10(r.p_adjust) if r.p_adjust > 0 else 0.0)
            text.append(r.id)

        return {
            "data": [
                {
                    "type": "scatter",
                    "mode": "markers",
                    "x": x,
                    "y": y,
                    "text": text,
                    "hovertemplate": (
                        "<b>%{text}</b><br>%{y}<br>GeneRatio=%{x:.4f}"
                        "<br>-log10(p.adjust)=%{marker.color:.2f}<extra></extra>"
                    ),
                    "marker": {
                        "size": sizes,
                        "color": colors,
                        "colorscale": "Viridis",
                        "showscale": True,
                        "colorbar": {"title": {"text": "-log10(p.adjust)"}},
                        "line": {"width": 0.5, "color": "rgba(120,120,120,0.6)"},
                    },
                }
            ],
            "layout": {
                "title": {"text": f"KEGG Pathway Enrichment Top {len(top)}"},
                "xaxis": {"title": {"text": "GeneRatio"}},
                "yaxis": {"title": {"text": "Pathway"}, "automargin": True},
                "margin": {"l": 24, "r": 24, "t": 50, "b": 40},
                "height": 460,
                "hovermode": "closest",
            },
        }


def _to_float(v: object) -> float:
    try:
        return float(str(v).strip()) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_int(v: object) -> int:
    try:
        return int(float(str(v).strip())) if v not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


def _gene_ratio_to_float(ratio: str, count: int) -> float:
    """GeneRatio '5/100' → 0.05；解析失败回退 count。"""
    try:
        num, denom = ratio.split("/", 1)
        return float(num) / float(denom) if float(denom) else float(count)
    except (ValueError, ZeroDivisionError):
        return float(count)
