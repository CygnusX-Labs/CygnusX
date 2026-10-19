"""工具注册入口 — 基于 config.yaml 的 tool_groups 开关按需加载；注册完成后做启动一致性自校验"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Any

from client.api_client import CygnusXAPIClient
from core.config import settings
from core.logger import logger
from fastmcp import FastMCP

_GROUP_REGISTRY: dict[str, str] = {
    "tasks": "tools.tasks",
    "runs": "tools.runs",
    "flows": "tools.flows",
    "analysis": "tools.analysis",
    "downloads": "tools.downloads",
    "files": "tools.files",
    "reports": "tools.reports",
    "sandbox": "tools.sandbox",
    "platform": "tools.platform",
    "pipelines": "tools.pipelines",
    "seqout": "tools.seqout",
    "biothings": "tools.biothings",
    "genome": "tools.research_resources",
    "plant_te": "tools.research_resources",
    "expression": "tools.research_resources",
    "pathways": "tools.research_resources",
    "protein_structure": "tools.research_resources",
    "clinical_literature": "tools.research_resources",
    "string_interactions": "tools.research_resources",
}

_TOOLS_YAML = Path(__file__).resolve().parent.parent / "tools.yaml"


def _load_tool_descriptions() -> dict[str, tuple[str | None, str]]:
    """Load exact tool-name descriptions from the external server registry."""
    try:
        import yaml

        raw: dict[str, Any] = yaml.safe_load(_TOOLS_YAML.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[自校验] 读取 tools.yaml 描述失败，运行时描述兜底不可用: {}", exc)
        return {}

    descriptions: dict[str, tuple[str | None, str]] = {}
    ambiguous_names: set[str] = set()
    for group in raw.get("groups") or []:
        group_id = str(group.get("id") or "unknown")
        for tool in group.get("tools") or []:
            name = str(tool.get("name") or "")
            description = tool.get("description")
            if not name or name in ambiguous_names:
                continue
            if name in descriptions:
                logger.warning(
                    "[自校验] 工具描述名冲突: tool={} groups={},{}",
                    name,
                    descriptions[name][1],
                    group_id,
                )
                descriptions.pop(name, None)
                ambiguous_names.add(name)
                continue
            descriptions[name] = (
                description if isinstance(description, str) else None,
                group_id,
            )
    return descriptions


class _DescriptionAwareMCP:
    """Use the public FastMCP decorator API to supply registry descriptions."""

    def __init__(self, mcp: FastMCP, descriptions: dict[str, tuple[str | None, str]]) -> None:
        self._mcp = mcp
        self._descriptions = descriptions

    def __getattr__(self, name: str) -> Any:
        return getattr(self._mcp, name)

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        explicit = kwargs.get("description")
        tool_name = kwargs.get("name")
        if not tool_name and args and isinstance(args[0], str):
            tool_name = args[0]

        def register(fn: Any) -> Any:
            name = str(tool_name or getattr(fn, "__name__", ""))
            description = kwargs.get("description")
            if not isinstance(description, str) or not description.strip():
                fallback = self._descriptions.get(name)
                if fallback and fallback[0] and fallback[0].strip():
                    kwargs["description"] = fallback[0]
            return self._mcp.tool(*args, **kwargs)(fn)

        if callable(args[0]) if args else False:
            return register(args[0])
        if isinstance(explicit, str) and explicit.strip():
            return self._mcp.tool(*args, **kwargs)
        return register


def _verify_tools_yaml_consistency(mcp: FastMCP, registered_groups: set[str]) -> None:
    """启动一致性自校验: tools.yaml 声明 ↔ 实际注册的工具名 / 工具组。

    只输出 warning 日志，不抛异常、不阻断启动。
    FastMCP 3.x 无同步的 tool manager，`mcp.list_tools()` 为协程；
    本函数在模块导入阶段（无运行中事件循环）通过 asyncio.run 收集。
    """
    try:
        import yaml
    except ImportError:
        logger.warning("[自校验] PyYAML 不可用，跳过 tools.yaml 一致性校验")
        return

    try:
        raw: dict[str, Any] = yaml.safe_load(_TOOLS_YAML.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning(f"[自校验] 读取 tools.yaml 失败，跳过一致性校验: {e}")
        return

    groups = raw.get("groups") or []
    declared_groups = {str(g["id"]) for g in groups if g.get("id")}
    declared_tools_by_group: dict[str, set[str]] = {
        str(g["id"]): {str(t["name"]) for t in (g.get("tools") or []) if t.get("name")}
        for g in groups
        if g.get("id")
    }

    # 工具组 ↔ _GROUP_REGISTRY keys
    registry_groups = set(_GROUP_REGISTRY)
    only_in_yaml = declared_groups - registry_groups
    only_in_registry = registry_groups - declared_groups
    if only_in_yaml or only_in_registry:
        logger.warning(
            "[自校验] tools.yaml 工具组与 _GROUP_REGISTRY 不一致: "
            f"仅 yaml 声明={sorted(only_in_yaml)}, 仅 registry 注册={sorted(only_in_registry)}"
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        logger.warning("[自校验] 当前已有事件循环，跳过导入阶段工具级校验")
        return

    try:
        registered_tools = {t.name for t in asyncio.run(mcp.list_tools())}
    except Exception as e:
        logger.warning(f"[自校验] 收集已注册工具失败，跳过工具级校验: {e}")
        return

    # 仅比对本次实际启用（已注册）的工具组，避免禁用组造成误报
    declared_tools: set[str] = set()
    for group_id in registered_groups:
        declared_tools |= declared_tools_by_group.get(group_id, set())

    missing = declared_tools - registered_tools  # yaml 声明但未注册
    extra = registered_tools - declared_tools  # 已注册但 yaml 未声明
    if missing or extra:
        logger.warning(
            "[自校验] tools.yaml 与已注册工具不一致: "
            f"声明未注册={sorted(missing)}, 注册未声明={sorted(extra)}"
        )
    else:
        logger.info(f"[自校验] tools.yaml 与已注册工具一致 ({len(registered_tools)} 个工具)")

    registered_by_name = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    registry_descriptions = _load_tool_descriptions()
    for name in sorted(registered_tools):
        tool = registered_by_name[name]
        description = getattr(tool, "description", None)
        if isinstance(description, str) and description.strip():
            continue
        fn = getattr(tool, "fn", None)
        try:
            source = inspect.getsourcefile(fn) or "unknown"
            line = inspect.getsourcelines(fn)[1]
            source = f"{source}:{line}"
        except (OSError, TypeError):
            source = "unknown"
        group = next(
            (group_id for group_id, names in declared_tools_by_group.items() if name in names),
            None,
        )
        registry_source = (
            f"tools.yaml tool={name} group={group}" if group else "tools.yaml entry missing"
        )
        registry_description = registry_descriptions.get(name)
        description_status = (
            "missing"
            if registry_description is None
            else "empty"
            if registry_description[0] == ""
            else "whitespace"
            if registry_description[0] is not None and not registry_description[0].strip()
            else "nonempty"
        )
        logger.warning(
            "[自校验] MCP 工具缺少有效描述: tool={} runtime_source={} registry_source={} registry_description={}",
            name,
            source,
            registry_source,
            description_status,
        )


def register_all_tools(mcp: FastMCP, api: CygnusXAPIClient) -> None:
    registered_mcp = _DescriptionAwareMCP(mcp, _load_tool_descriptions())
    registered_groups: set[str] = set()
    for group_id, module_path in _GROUP_REGISTRY.items():
        if not settings.is_tool_group_enabled(group_id):
            logger.info(f"工具组 [{group_id}] 已禁用，跳过注册")
            continue
        module = importlib.import_module(module_path)
        if group_id == "genome":
            module.register_genome(registered_mcp, api)
        elif group_id == "plant_te":
            module.register_plant_te(registered_mcp, api)
        elif group_id == "expression":
            module.register_expression(registered_mcp, api)
        elif group_id == "pathways":
            module.register_pathways(registered_mcp, api)
        elif group_id == "protein_structure":
            module.register_protein(registered_mcp, api)
        elif group_id == "clinical_literature":
            module.register_clinical_literature(registered_mcp, api)
        elif group_id == "string_interactions":
            module.register_string(registered_mcp, api)
        else:
            module.register(registered_mcp, api)
        registered_groups.add(group_id)
        logger.debug(f"工具组 [{group_id}] 注册完成")

    _verify_tools_yaml_consistency(mcp, registered_groups)
