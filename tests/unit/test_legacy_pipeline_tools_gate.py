"""阶段 3（MCP 工具固定化）LEGACY_PIPELINE_TOOLS 开关测试。

默认 true = 现状保持（旧工具可见）；false = 默认清单只剩固定工具，
旧四件套转为迁移提示/同名 stub，可回退。
"""

from __future__ import annotations

import pytest

from cygnusx.core.config import get_settings
from cygnusx.infrastructure.mcp.pipeline_preset import (
    CYGNUSX_PIPELINES_SERVER_NAME,
    PIPELINE_TOOLS,
    build_pipeline_preset,
)
from cygnusx.infrastructure.mcp.presets import _build_cygnusx_tools_preset
from cygnusx.tools.schema_loader import ToolsSchemaLoader


@pytest.fixture
def legacy_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "legacy_pipeline_tools", False)


@pytest.fixture
def legacy_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(get_settings(), "legacy_pipeline_tools", True)


def _per_flow_prepare_tools(loader: ToolsSchemaLoader) -> list[str]:
    return [
        t.name
        for t in loader._load_flow_tools()
        if t.extra and t.extra.get("tool_role") == "prepare"
    ]


def test_legacy_on_keeps_per_flow_tools(legacy_on: None) -> None:
    loader = ToolsSchemaLoader()
    names = _per_flow_prepare_tools(loader)
    assert "cygnusx_prepare_rna_seq_submission" in names


def test_legacy_off_removes_per_flow_tools_keeps_query_tools(legacy_off: None) -> None:
    loader = ToolsSchemaLoader()
    names = _per_flow_prepare_tools(loader)
    assert names == []
    # 通用 status/summary 查询工具保留（复用通用任务工具前仍可用）
    all_names = {t.name for t in loader._load_flow_tools()}
    assert "cygnusx_get_analysis_task_status" in all_names
    assert "cygnusx_get_analysis_task_summary" in all_names


def test_legacy_off_builtin_preset_only_fixed_tools(legacy_off: None) -> None:
    preset = _build_cygnusx_tools_preset()
    names = {t["name"] for t in preset["tools"]}
    assert not any(n.startswith("cygnusx_prepare_") and n.endswith("_submission") for n in names)
    # 固定工具仍在清单内
    assert "cygnusx_prepare" in names
    assert "cygnusx_submit" in names


def test_legacy_on_builtin_preset_has_per_flow_tools(legacy_on: None) -> None:
    preset = _build_cygnusx_tools_preset()
    names = {t["name"] for t in preset["tools"]}
    assert "cygnusx_prepare_rna_seq_submission" in names


def test_legacy_off_pipeline_preset_becomes_migration_shell(legacy_off: None) -> None:
    preset = build_pipeline_preset()
    assert preset["name"] == CYGNUSX_PIPELINES_SERVER_NAME
    assert preset["tools"] == []
    assert preset["handlers"] == {}
    assert "已迁移" in preset["description"]
    assert "cygnusx_prepare" in preset["description"]


def test_legacy_on_pipeline_preset_unchanged(legacy_on: None) -> None:
    preset = build_pipeline_preset()
    assert {t["name"] for t in preset["tools"]} == {t["name"] for t in PIPELINE_TOOLS}
    assert "已迁移" not in preset["description"]
