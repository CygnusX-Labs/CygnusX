"""RNAFlow 项目配置构建器

将 OmicsHub 前端提交的表单参数与样本表转换为 RNAFlow 可识别的：
- project config.yaml
- samples.csv
- contrasts.csv
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import yaml

# RNAFlow Snakefile 的固定路径（可通过环境变量覆盖）
DEFAULT_RNAFLOW_SNAKEFILE = Path("/home/zj/pipeline/RNAFlow/snakefile")

# 链特异性词汇映射：OmicsHub UI value -> RNAFlow Library_Types value
STRANDNESS_MAP = {
    "unstranded": "fr-unstranded",
    "forward": "fr-secondstrand",
    "reverse": "fr-firststrand",
}


def build_rnaflow_project(
    work_dir: str | Path,
    parameters: dict[str, Any],
    sample_rows: list[dict[str, Any]],
    comparisons: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """构建 RNAFlow 项目所需的所有输入文件。

    Args:
        work_dir: OmicsHub 为该任务分配的工作目录
        parameters: 前端表单提交并经快照锁定的参数字典
        sample_rows: 样本表行数据，每行需包含 sample/sample_name/group
        comparisons: 差异比较组列表，每项需包含 Control/Treat

    Returns:
        生成的文件路径字典：{"config", "samples", "contrasts"}
    """
    work_path = Path(work_dir)
    work_path.mkdir(parents=True, exist_ok=True)

    samples_path = work_path / "samples.csv"
    contrasts_path = work_path / "contrasts.csv"
    config_path = work_path / "config.yaml"

    _write_samples_csv(sample_rows, samples_path)
    _write_contrasts_csv(comparisons or [], contrasts_path)

    rnaflow_config = _build_rnaflow_config(
        parameters=parameters,
        samples_csv=str(samples_path),
        contrasts_csv=str(contrasts_path),
        workflow_dir=str(work_path),
    )
    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(rnaflow_config, f, sort_keys=False, allow_unicode=True)

    return {
        "config": config_path,
        "samples": samples_path,
        "contrasts": contrasts_path,
    }


def _build_rnaflow_config(
    parameters: dict[str, Any],
    samples_csv: str,
    contrasts_csv: str,
    workflow_dir: str,
) -> dict[str, Any]:
    """根据前端参数构造 RNAFlow config.yaml 内容。"""
    strandness = parameters.get("Library_Types") or parameters.get("strandness", "unstranded")
    library_types = STRANDNESS_MAP.get(strandness, strandness)

    execution_mode = parameters.get("execution_mode", "local")

    config: dict[str, Any] = {
        "project_name": parameters.get("project_name", "OmicsHub_Project"),
        "Genome_Version": parameters.get("Genome_Version", "hg38"),
        "species": parameters.get("species", ""),
        "client": parameters.get("client", "内部测试"),
        "raw_data_path": _normalize_raw_data_path(parameters.get("raw_data_path", "")),
        "sample_csv": samples_csv,
        "paired_csv": contrasts_csv,
        "workflow": workflow_dir,
        "data_deliver": parameters.get("data_deliver", str(Path(workflow_dir).parent / "data_deliver")),
        "execution_mode": execution_mode,
        "queue_id": parameters.get("queue_id", "default"),
        "Library_Types": library_types,
        "only_qc": parameters.get("only_qc", False),
        "report": parameters.get("report", True),
        "deg": parameters.get("deg", True),
        "fastq_screen": parameters.get("fastq_screen", True),
        "call_variant": parameters.get("call_variant", False),
        "detect_novel_transcripts": parameters.get("detect_novel_transcripts", False),
        "rmats": parameters.get("rmats", True),
        "gene_fusion": parameters.get("gene_fusion", False),
    }

    loki_url = parameters.get("loki_url")
    if loki_url:
        config["loki_url"] = loki_url

    return config


def _normalize_raw_data_path(value: Any) -> list[str]:
    """统一 raw_data_path 为字符串列表。"""
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        path = value.strip()
        if path:
            return [path]
    return []


def _write_samples_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """写入 RNAFlow samples.csv。

    要求每行至少包含 sample、sample_name、group。
    """
    fieldnames = ["sample", "sample_name", "group"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "sample": row.get("sample", row.get("sample_id", "")),
                "sample_name": row.get("sample_name", row.get("sample", "")),
                "group": row.get("group", ""),
            })


def _write_contrasts_csv(comparisons: list[dict[str, Any]], path: Path) -> None:
    """写入 RNAFlow contrasts.csv (Control, Treat)。"""
    fieldnames = ["Control", "Treat"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for comp in comparisons:
            control = comp.get("Control") or comp.get("control_group", "")
            treat = comp.get("Treat") or comp.get("treatment_group", "")
            if control and treat:
                writer.writerow({"Control": control, "Treat": treat})


def dump_sample_preview(rows: list[dict[str, Any]]) -> str:
    """生成样本表 CSV 预览字符串（用于日志/调试）。"""
    if not rows:
        return ""
    fieldnames = ["sample", "sample_name", "group"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "sample": row.get("sample", row.get("sample_id", "")),
            "sample_name": row.get("sample_name", row.get("sample", "")),
            "group": row.get("group", ""),
        })
    return output.getvalue()
