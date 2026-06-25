"""ATACFlow 项目配置构建器

将 OmicsHub 前端提交的表单参数与样本表转换为 ATACFlow 可识别的：
- analysis config.yaml（通过 --config analysisyaml=... 传入）
- samples.csv
- contrasts.csv

ATACFlow 启动方式：
    snakemake -s /home/zj/pipeline/ATACFlow/snakefile \
        --config analysisyaml=<generated_config.yaml>

ATACFlow 本身会从 config/ 目录加载基础配置（config.yaml、reference.yaml、
run_parameter.yaml、cluster_config.yaml），随后用 analysisyaml 覆盖项目相关字段。
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import yaml

# ATACFlow Snakefile 的固定路径（可通过环境变量覆盖）
DEFAULT_ATACFLOW_SNAKEFILE = Path("/home/zj/pipeline/ATACFlow/snakefile")


# ATACFlow 的 Library_Types 与 OmicsHub UI 值一致，无需映射
# fr-unstranded / fr-firststrand / fr-secondstrand


def build_atacflow_project(
    work_dir: str | Path,
    parameters: dict[str, Any],
    sample_rows: list[dict[str, Any]],
    comparisons: list[dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """构建 ATACFlow 项目所需的所有输入文件。

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
    config_path = work_path / "analysis.yaml"

    _write_samples_csv(sample_rows, samples_path)
    _write_contrasts_csv(comparisons or [], contrasts_path)

    atacflow_config = _build_atacflow_config(
        parameters=parameters,
        samples_csv=str(samples_path),
        contrasts_csv=str(contrasts_path),
        workflow_dir=str(work_path),
    )
    with config_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(atacflow_config, f, sort_keys=False, allow_unicode=True)

    return {
        "config": config_path,
        "samples": samples_path,
        "contrasts": contrasts_path,
    }


def _build_atacflow_config(
    parameters: dict[str, Any],
    samples_csv: str,
    contrasts_csv: str,
    workflow_dir: str,
) -> dict[str, Any]:
    """根据前端参数构造 ATACFlow analysis.yaml 内容。"""
    execution_mode = parameters.get("execution_mode", "local")

    # data_deliver 默认为 workflow 父目录下的 data_deliver
    data_deliver = parameters.get("data_deliver") or str(Path(workflow_dir).parent / "data_deliver")

    config: dict[str, Any] = {
        "project_name": parameters.get("project_name", "OmicsHub_Project"),
        "Genome_Version": parameters.get("Genome_Version", "hg38"),
        "species": parameters.get("species", ""),
        "client": parameters.get("client", "内部测试"),
        "raw_data_path": _normalize_raw_data_path(parameters.get("raw_data_path", "")),
        "sample_csv": samples_csv,
        "paired_csv": contrasts_csv,
        "workflow": workflow_dir,
        "data_deliver": data_deliver,
        "execution_mode": execution_mode,
        "queue_id": parameters.get("queue_id", "default"),
        "Library_Types": parameters.get("Library_Types", "fr-firststrand"),
        "only_qc": parameters.get("only_qc", False),
        "report": parameters.get("report", True),
        "diff_peaks": parameters.get("diff_peaks", True),
        "fastq_screen": parameters.get("fastq_screen", True),
        "mapping_tools": parameters.get("mapping_tools", "bowtie2"),
        "peak_calling": {
            "use_pooled_peaks": parameters.get("use_pooled_peaks", True),
        },
    }

    loki_url = parameters.get("loki_url")
    if loki_url:
        config["loki_url"] = loki_url

    return config


def _normalize_raw_data_path(value: Any) -> list[str]:
    """统一 raw_data_path 为字符串列表（ATACFlow 支持多个 raw data 目录）。"""
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        path = value.strip()
        if path:
            return [path]
    return []


def _write_samples_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """写入 ATACFlow samples.csv。

    要求每行至少包含 sample、sample_name、group。
    """
    fieldnames = ["sample", "sample_name", "group"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "sample": row.get("sample", row.get("sample_id", "")),
                    "sample_name": row.get("sample_name", row.get("sample", "")),
                    "group": row.get("group", ""),
                }
            )


def _write_contrasts_csv(comparisons: list[dict[str, Any]], path: Path) -> None:
    """写入 ATACFlow contrasts.csv (Control, Treat)。"""
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
        writer.writerow(
            {
                "sample": row.get("sample", row.get("sample_id", "")),
                "sample_name": row.get("sample_name", row.get("sample", "")),
                "group": row.get("group", ""),
            }
        )
    return output.getvalue()
