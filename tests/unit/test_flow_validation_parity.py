"""校验插件与新旧路径校验对等矩阵（MCP 工具固定化 · 阶段 2）。

对等矩阵：6 类非法输入，旧路径（PipelineController.prepare → 四件套 API 底层）
与统一固定工具路径（AnalysisFlowToolService.prepare）必须同样拒绝。
两条路径共享 FlowSubmissionValidator；矩阵锁定差异面（工作区数据 / 样本-FASTQ
匹配）在插件化后对齐，防止未来回归。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.analysis_flow_tool_service import AnalysisFlowToolService
from cygnusx.application.services.pipeline_controller import PipelineController
from cygnusx.domain.flow.submission_validator import FlowSubmissionValidator
from cygnusx.domain.flow.validation_plugins import (
    check_workspace_fastq,
    get_flow_validation_plugin,
    missing_sample_fastq_files,
)


class _FakeAsyncSession(AsyncSession):
    def __init__(self):
        pass


class _Factory:
    """指向 tmp 目录的伪造路径工厂。"""

    def __init__(self, root: Path):
        self._root = root

    def user_root(self, user_id: str) -> Path:
        return self._root / user_id


def _context(user_id: str = "u1") -> ToolInvocationContext:
    return ToolInvocationContext(user_id=user_id, session_id="s-parity", db=_FakeAsyncSession())


def _touch_fastq(directory: Path, sample: str, paired: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{sample}_R1.fastq.gz").write_text("@r1\nACGT\n+\nIIII\n")
    if paired:
        (directory / f"{sample}_R2.fastq.gz").write_text("@r2\nACGT\n+\nIIII\n")


def _sample_sheet(samples: list[str]) -> list[dict[str, Any]]:
    groups = ["ctrl", "treat"]
    return [
        {"sample": s, "sample_name": f"Sample{s}", "group": groups[i % 2]}
        for i, s in enumerate(samples)
    ]


def _valid_sheet() -> list[dict[str, Any]]:
    return [
        {"sample": "S1", "sample_name": "Sample1", "group": "ctrl"},
        {"sample": "S2", "sample_name": "Sample2", "group": "treat"},
    ]


def _valid_comparisons() -> list[dict[str, Any]]:
    return [{"name": "TvsC", "Control": "ctrl", "Treat": "treat"}]


def _new_path_args(raw_data_path: str = "raw") -> dict[str, Any]:
    return {
        "name": "demo",
        "parameters": {
            "project_name": "P",
            "Genome_Version": "hg38",
            "species": "human",
            "client": "parity-test",
            "raw_data_path": raw_data_path,
        },
        "sample_sheet": _valid_sheet(),
        "comparisons": _valid_comparisons(),
    }


def _old_path_request(raw_data_path: str = "raw") -> dict[str, Any]:
    return {
        "raw_data_path": raw_data_path,
        "species": "human",
        "genome_version": "hg38",
        "sample_sheet": _valid_sheet(),
        "comparisons": _valid_comparisons(),
        "library_type": "fr-unstranded",
        "task_name": "demo",
        "project_name": "P",
    }


@pytest.fixture(autouse=True)
def isolated_confirmations(monkeypatch: pytest.MonkeyPatch) -> None:
    from cygnusx.application.services import tool_confirmation_service as module

    monkeypatch.setattr(
        module,
        "_confirmation_service",
        module.ToolConfirmationService(module._MemoryStore()),
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """tmp 用户工作区（u1/raw 含 S1/S2 双端 FASTQ）+ 全链路路径工厂补丁。"""
    user_root = tmp_path / "u1"
    raw = user_root / "raw"
    _touch_fastq(raw, "S1")
    _touch_fastq(raw, "S2")

    factory = _Factory(tmp_path)
    monkeypatch.setattr(
        "cygnusx.application.services.pipeline_controller.get_path_factory", lambda: factory
    )
    monkeypatch.setattr(
        "cygnusx.domain.flow.submission_validator.get_path_factory", lambda: factory
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.storage.get_path_factory", lambda: factory
    )
    return raw


async def _new_path_rejects(args: dict[str, Any]) -> list[str]:
    result = await AnalysisFlowToolService(context=_context()).prepare(
        "rna_seq", args, create_confirmation=False
    )
    assert result.get("valid") is False, f"统一路径应拒绝，实际通过: {result}"
    return [e["code"] for e in result.get("errors", [])]


async def _old_path_rejects(request: dict[str, Any]) -> Any:
    controller = PipelineController(_context())
    result = await controller.prepare("rna_seq", request)
    assert result.get("valid") is False, f"旧路径应拒绝，实际通过: {result}"
    return [e["code"] for e in result.get("errors", [])]


# ============ 插件单元测试 ============


def test_plugin_registry() -> None:
    assert get_flow_validation_plugin("fastq_workspace") is not None
    assert get_flow_validation_plugin("no_such_plugin") is None


def test_check_workspace_fastq_and_missing_samples(workspace: Path) -> None:
    report = check_workspace_fastq(workspace)
    assert report["valid"] is True
    assert report["fastq_count"] == 4
    assert report["paired_end"] is True

    assert missing_sample_fastq_files(workspace, [{"sample": "S1"}]) == []
    assert missing_sample_fastq_files(workspace, [{"sample": "S9"}]) == ["S9"]


def test_check_workspace_fastq_empty_dir(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    report = check_workspace_fastq(empty)
    assert report["valid"] is False
    assert report["warnings"] == ["未发现 FASTQ 文件"]


@pytest.mark.asyncio
async def test_unknown_plugin_reports_error(workspace: Path) -> None:
    """流程配置引用未知插件名 → UNKNOWN_VALIDATION_PLUGIN，不静默跳过。"""
    from cygnusx.application.services.flow_service import FlowService

    flow = FlowService().get_flow_config("rna_seq")
    ai = flow.ai.model_copy(update={"validation_plugins": ["no_such_plugin"]}) if flow.ai else None
    tampered = flow.model_copy(update={"ai": ai})
    result = await FlowSubmissionValidator().validate(
        _context(), tampered, _new_path_args()
    )
    assert result.valid is False
    assert any(e.code == "UNKNOWN_VALIDATION_PLUGIN" for e in result.errors)


# ============ 校验对等矩阵（6 类非法输入 × 双路径） ============


@pytest.mark.asyncio
async def test_parity_1_workspace_without_data(workspace: Path) -> None:
    """工作区无数据：两路径均以 INVALID_WORKSPACE_DATA 拒绝。"""
    old_codes = await _old_path_rejects(_old_path_request(raw_data_path="no_such_dir"))
    new_codes = await _new_path_rejects(_new_path_args(raw_data_path="no_such_dir"))
    assert "INVALID_WORKSPACE_DATA" in old_codes
    assert "INVALID_WORKSPACE_DATA" in new_codes


@pytest.mark.asyncio
async def test_parity_2_sample_fastq_not_found(workspace: Path) -> None:
    """样本-FASTQ 不匹配：两路径均以 SAMPLE_FASTQ_NOT_FOUND 拒绝。"""
    old_req = _old_path_request()
    old_req["sample_sheet"] = _valid_sheet() + [
        {"sample": "S9", "sample_name": "Sample9", "group": "ctrl"}
    ]
    new_args = _new_path_args()
    new_args["sample_sheet"] = old_req["sample_sheet"]

    old_codes = await _old_path_rejects(old_req)
    new_codes = await _new_path_rejects(new_args)
    assert "SAMPLE_FASTQ_NOT_FOUND" in old_codes
    assert "SAMPLE_FASTQ_NOT_FOUND" in new_codes


@pytest.mark.asyncio
async def test_parity_3_missing_required_parameter(workspace: Path) -> None:
    """缺必填参数：旧路径请求模型拒绝，统一路径校验器 MISSING_REQUIRED 拒绝。

    注：流程参数普遍声明 default（缺失补默认值属契约合法行为），故本类用
    无默认值的 task_name 参数做对等断言。
    """
    from pydantic import ValidationError

    old_req = _old_path_request()
    del old_req["task_name"]
    with pytest.raises(ValidationError):
        await PipelineController(_context()).prepare("rna_seq", old_req)

    new_args = _new_path_args()
    del new_args["name"]
    new_codes = await _new_path_rejects(new_args)
    assert "MISSING_REQUIRED" in new_codes


@pytest.mark.asyncio
async def test_parity_4_comparison_group_not_found(workspace: Path) -> None:
    """比较组引用不存在的分组：两路径均以 GROUP_NOT_FOUND 拒绝。"""
    bad_comparisons = [{"name": "XvsY", "Control": "ghost", "Treat": "treat"}]

    old_req = _old_path_request()
    old_req["comparisons"] = bad_comparisons
    new_args = _new_path_args()
    new_args["comparisons"] = bad_comparisons

    old_codes = await _old_path_rejects(old_req)
    new_codes = await _new_path_rejects(new_args)
    assert "GROUP_NOT_FOUND" in old_codes
    assert "GROUP_NOT_FOUND" in new_codes


@pytest.mark.asyncio
async def test_parity_5_sample_sheet_missing_column(workspace: Path) -> None:
    """样本表缺必填列（group）：两路径均以 MISSING_REQUIRED 拒绝。"""
    bad_sheet = [
        {"sample": "S1", "sample_name": "Sample1"},
        {"sample": "S2", "sample_name": "Sample2", "group": "treat"},
    ]
    old_req = _old_path_request()
    old_req["sample_sheet"] = bad_sheet
    new_args = _new_path_args()
    new_args["sample_sheet"] = bad_sheet

    old_codes = await _old_path_rejects(old_req)
    new_codes = await _new_path_rejects(new_args)
    assert "MISSING_REQUIRED" in old_codes
    assert "MISSING_REQUIRED" in new_codes


@pytest.mark.asyncio
async def test_parity_6_quota_exceeded(workspace: Path) -> None:
    """超资源配额（比较组数 > max_comparisons=10）：两路径均以
    MAX_COMPARISONS_EXCEEDED 拒绝。"""
    many = [
        {"name": f"C{i}", "Control": "ctrl", "Treat": "treat"} for i in range(11)
    ]
    old_req = _old_path_request()
    old_req["comparisons"] = many
    new_args = _new_path_args()
    new_args["comparisons"] = many

    old_codes = await _old_path_rejects(old_req)
    new_codes = await _new_path_rejects(new_args)
    assert "MAX_COMPARISONS_EXCEEDED" in old_codes
    assert "MAX_COMPARISONS_EXCEEDED" in new_codes


@pytest.mark.asyncio
async def test_parity_baseline_valid_input_passes(workspace: Path) -> None:
    """基线对照：合法输入在两路径都通过预检（统一路径 valid=True）。"""
    controller = PipelineController(_context())
    old_result = await controller.prepare("rna_seq", _old_path_request())
    assert old_result.get("valid") is True, old_result

    new_result = await AnalysisFlowToolService(context=_context()).prepare(
        "rna_seq", _new_path_args(), create_confirmation=False
    )
    assert new_result.get("valid") is True, new_result
