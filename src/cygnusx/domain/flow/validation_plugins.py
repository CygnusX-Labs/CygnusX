"""Flow 提交前校验插件（MCP 工具固定化 · 阶段 2）。

可复用校验扩展点：流程 YAML 的 ``ai.validation_plugins`` 按名引用，
统一 prepare（``FlowSubmissionValidator``）按配置调用。**插件不增加 MCP 工具。**

内置插件：

- ``fastq_workspace``：工作区数据检查（数据目录存在性、FASTQ 组成、双端匹配）
  + 样本-FASTQ 匹配检查。逻辑与旧 PipelineController 同源（本模块为唯一实现），
  保证旧 pipelines 路径与统一固定工具路径的校验对等。

越界路径（不在当前用户工作区内）由 final path 校验或旧控制器报告，
插件一律跳过、不重复报错。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.domain.flow.entities import FlowConfig
from cygnusx.domain.flow.submission_validator import ValidationErrorItem

FASTQ_SUFFIXES = (".fastq", ".fq", ".fastq.gz", ".fq.gz")


def check_workspace_fastq(path: Path) -> dict[str, Any]:
    """扫描目录内 FASTQ 组成（与旧 PipelineController 行为一致）。"""
    fastq_files = sorted(
        p
        for p in path.rglob("*")
        if p.is_file() and p.name.lower().endswith(FASTQ_SUFFIXES)
    )
    r1 = [p for p in fastq_files if any(token in p.name for token in ("_R1", "_1."))]
    r2 = [p for p in fastq_files if any(token in p.name for token in ("_R2", "_2."))]
    warnings: list[str] = []
    if not fastq_files:
        warnings.append("未发现 FASTQ 文件")
    if (r1 or r2) and len(r1) != len(r2):
        warnings.append(f"双端文件数量不匹配：R1={len(r1)}，R2={len(r2)}")
    total_size = sum(p.stat().st_size for p in fastq_files)
    return {
        "valid": bool(fastq_files) and not any("不匹配" in item for item in warnings),
        "errors": [],
        "warnings": warnings,
        "fastq_count": len(fastq_files),
        "paired_end": bool(r1 and r2),
        "r1_count": len(r1),
        "r2_count": len(r2),
        "total_size_bytes": total_size,
        "estimated_samples": max(len(r1), len(r2), len(fastq_files)),
    }


def missing_sample_fastq_files(
    data_path: Path, sample_sheet: list[dict[str, Any]]
) -> list[str]:
    """返回样本表中未匹配到 FASTQ 文件的样本名（与旧 PipelineController 行为一致）。"""
    fastq_names = [
        p.name.lower()
        for p in data_path.rglob("*")
        if p.is_file() and p.name.lower().endswith(FASTQ_SUFFIXES)
    ]
    missing: list[str] = []
    for row in sample_sheet:
        sample = str(row.get("sample") or row.get("sample_name") or "").strip()
        if sample and not any(name.startswith(sample.lower()) for name in fastq_names):
            missing.append(sample)
    return missing


class FlowValidationPlugin(Protocol):
    """Flow 提交前校验插件协议。

    实现必须是纯校验：无副作用、不创建任务、不写存储。
    """

    name: str

    async def validate(
        self,
        context: ToolInvocationContext,
        flow: FlowConfig,
        arguments: dict[str, Any],
        normalized_params: dict[str, Any],
        sample_rows: list[dict[str, Any]],
    ) -> list[ValidationErrorItem]: ...


class FastqWorkspacePlugin:
    """工作区数据 + 样本-FASTQ 匹配校验（RNA/ATAC 共用）。"""

    name = "fastq_workspace"

    async def validate(
        self,
        context: ToolInvocationContext,
        flow: FlowConfig,
        arguments: dict[str, Any],
        normalized_params: dict[str, Any],
        sample_rows: list[dict[str, Any]],
    ) -> list[ValidationErrorItem]:
        from cygnusx.infrastructure.storage import get_path_factory

        raw = normalized_params.get("raw_data_path")
        if not isinstance(raw, str) or not raw:
            return []
        root = get_path_factory().user_root(context.user_id).resolve()
        candidate = Path(raw)
        path = (candidate if candidate.is_absolute() else root / candidate).resolve()
        if not path.is_relative_to(root):
            return []  # 越界路径由 final path 校验 / 旧控制器报告

        if not path.exists() or not path.is_dir():
            return [
                ValidationErrorItem(
                    field="parameters.raw_data_path",
                    code="INVALID_WORKSPACE_DATA",
                    message="数据目录不存在或不是目录",
                )
            ]

        errors: list[ValidationErrorItem] = []
        report = check_workspace_fastq(path)
        if not report["valid"]:
            for message in report["warnings"]:
                errors.append(
                    ValidationErrorItem(
                        field="parameters.raw_data_path",
                        code="INVALID_WORKSPACE_DATA",
                        message=message,
                    )
                )
        for sample in missing_sample_fastq_files(path, sample_rows):
            errors.append(
                ValidationErrorItem(
                    field="sample_sheet",
                    code="SAMPLE_FASTQ_NOT_FOUND",
                    message=f"样本未匹配到 FASTQ 文件: {sample}",
                )
            )
        return errors


_REGISTRY: dict[str, FlowValidationPlugin] = {
    FastqWorkspacePlugin.name: FastqWorkspacePlugin(),
}


def get_flow_validation_plugin(name: str) -> FlowValidationPlugin | None:
    """按名取校验插件；未知名返回 None（校验器会报 UNKNOWN_VALIDATION_PLUGIN）。"""
    return _REGISTRY.get(name)
