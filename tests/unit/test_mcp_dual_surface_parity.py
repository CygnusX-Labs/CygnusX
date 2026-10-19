"""内/外双端 MCP 一致性测试。

防止"内外双端漂移"：外部 mcp-server（FastMCP + tools.yaml + REST 桥）与内置
builtin presets（cygnusx-platform / cygnusx-pipelines / cygnusx-tools）共享同一批
流水线与下载能力，任何一端改名、丢确认门都会在这里被拦下。
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import yaml

from cygnusx.application.services.tool_bridge_service import ToolBridgeService
from cygnusx.infrastructure.mcp.pipeline_preset import (
    PIPELINE_HANDLERS,
    PIPELINE_TOOLS,
)
from cygnusx.infrastructure.mcp.presets import (
    PLATFORM_HANDLERS,
    PLATFORM_PRESET_TOOLS,
    _platform_submit_download,
)
from cygnusx.infrastructure.mcp.research_preset import RESEARCH_HANDLERS, RESEARCH_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_TOOLS_YAML = REPO_ROOT / "mcp-server" / "tools.yaml"
EXTERNAL_PIPELINES_PY = REPO_ROOT / "mcp-server" / "tools" / "pipelines.py"
EXTERNAL_RESEARCH_PY = REPO_ROOT / "mcp-server" / "tools" / "research_resources.py"


def _external_groups() -> dict[str, list[dict]]:
    config = yaml.safe_load(EXTERNAL_TOOLS_YAML.read_text(encoding="utf-8"))
    return {group["id"]: group.get("tools", []) for group in config["groups"]}


def test_platform_preset_tool_handler_parity() -> None:
    tool_names = {tool["name"] for tool in PLATFORM_PRESET_TOOLS}
    assert tool_names == set(PLATFORM_HANDLERS), (
        "cygnusx-platform preset 工具与 handler 注册表漂移: "
        f"缺 handler: {tool_names - set(PLATFORM_HANDLERS)}, "
        f"孤儿 handler: {set(PLATFORM_HANDLERS) - tool_names}"
    )


def test_pipeline_preset_tool_handler_parity() -> None:
    tool_names = {tool["name"] for tool in PIPELINE_TOOLS}
    assert tool_names == set(PIPELINE_HANDLERS)


def test_pipeline_tool_names_match_external_tools_yaml() -> None:
    internal_names = {tool["name"] for tool in PIPELINE_TOOLS}
    external_names = {tool["name"] for tool in _external_groups()["pipelines"]}
    assert internal_names == external_names, (
        f"内外流水线工具名漂移: 仅内部 {internal_names - external_names}, "
        f"仅外部 {external_names - internal_names}"
    )


def test_research_data_tool_names_match_external_tools_yaml() -> None:
    internal_names = {tool["name"] for tool in RESEARCH_TOOLS}
    external_names = {
        tool["name"]
        for group_id in (
            "genome",
            "plant_te",
            "expression",
            "pathways",
            "protein_structure",
            "clinical_literature",
            "string_interactions",
        )
        for tool in _external_groups()[group_id]
    }
    assert internal_names == external_names
    assert internal_names == set(RESEARCH_HANDLERS)


def test_research_data_external_signatures_match_builtin_schemas() -> None:
    tree = ast.parse(EXTERNAL_RESEARCH_PY.read_text(encoding="utf-8"))
    external: dict[str, tuple[set[str], set[str]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or not node.name.startswith("cygnusx_"):
            continue
        names = [argument.arg for argument in node.args.args]
        defaulted = (
            {
                name
                for name, _ in zip(
                    names[-len(node.args.defaults) :], node.args.defaults, strict=True
                )
            }
            if node.args.defaults
            else set()
        )
        external[node.name] = (set(names), set(names) - defaulted)

    internal = {
        tool["name"]: (
            set(tool["inputSchema"]["properties"]),
            set(tool["inputSchema"].get("required", [])),
        )
        for tool in RESEARCH_TOOLS
    }
    assert external == internal

    clinvar_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "cygnusx_clinvar_get"
    )
    type_argument = next(arg for arg in clinvar_fn.args.args if arg.arg == "identifier_type")
    literal_type = type_argument.annotation.left
    assert isinstance(literal_type, ast.Subscript)
    assert isinstance(literal_type.value, ast.Name) and literal_type.value.id == "Literal"
    internal_clinvar = next(
        tool for tool in RESEARCH_TOOLS if tool["name"] == "cygnusx_clinvar_get"
    )
    assert list(ast.literal_eval(literal_type.slice)) == internal_clinvar["inputSchema"]["properties"][
        "identifier_type"
    ]["enum"]


def test_external_pipeline_submits_declare_confirmation_gate() -> None:
    pipelines_group = {tool["name"]: tool for tool in _external_groups()["pipelines"]}
    submit_names = {name for name in pipelines_group if name.endswith("_submit")}
    assert {"rna_seq_submit", "atac_seq_submit"} <= submit_names
    source = EXTERNAL_PIPELINES_PY.read_text(encoding="utf-8")
    for name in submit_names:
        assert pipelines_group[name].get("requires_confirm") is True, (
            f"外部 {name} 未在 tools.yaml 标记 requires_confirm"
        )
        match = re.search(rf"async def {name}\((.*?)\)", source, re.DOTALL)
        assert match is not None, f"外部注册函数 {name} 缺失"
        assert "user_confirmed" in match.group(1), (
            f"外部 {name} 注册函数缺少 user_confirmed 确认参数"
        )


def test_platform_submit_download_confirmation_surface_declared() -> None:
    tool = next(t for t in PLATFORM_PRESET_TOOLS if t["name"] == "platform_submit_download")
    assert "_confirmation_id" in tool["inputSchema"]["properties"], (
        "platform_submit_download schema 缺少 _confirmation_id 控制参数声明"
    )
    assert "confirmation_id" in tool["description"]
    handler_source = inspect.getsource(_platform_submit_download)
    assert "create_for_tool" in handler_source
    assert "consume_tool_confirmation" in handler_source


def test_bridge_no_legacy_confirmed_self_bypass() -> None:
    source = inspect.getsource(ToolBridgeService.execute)
    assert 'arguments.get("_confirmed")' not in source, (
        "requires_confirm 门禁止恢复 _confirmed 模型自证旁路"
    )
    assert "_confirmation_id" in source
