"""内置 Agent 声明式配置的一致性回归。

纯文件层校验（不触库、不加载重依赖），保护三处容易随专家增减而漂移的契约：

1. handoff 白名单：目标必须是活跃专家、不能指向 router、不能自转交；
2. MAS 能力登记：agents.enabled 中每个专家都必须在 agent_capabilities.yaml 登记；
3. 路由提示词候选表：router.md 中出现的 agent_id 必须存在于运行时目录。

历史事故见 README §11.2 与记忆 router-session-handoff-source-agent。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

AI_DIR = Path("data/ai")
SITE_YAML = Path("data/OmicHub.yaml")
CAPABILITIES_YAML = AI_DIR / "mas" / "agent_capabilities.yaml"
ABILITY_YAML = AI_DIR / "agent_ability.yaml"
ROUTER_PROMPT = AI_DIR / "prompts" / "router.md"
STANDARD_PROMPT_SECTIONS = (
    "角色与职责边界",
    "对话与执行模式",
    "输入确认",
    "知识检索与证据规则",
    "方法论与专业决策",
    "工具、Skill 与工作区协议",
    "执行确认与安全边界",
    "输出与交付规范",
    "失败、降级与诚实约束",
    "转介、交接与协作",
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _enabled_agent_files() -> list[str]:
    return [str(name) for name in _load(SITE_YAML)["agents"]["enabled"]]


def _agent_configs() -> dict[str, dict]:
    """file key -> raw YAML dict（含 orchestrator 若文件存在）。"""
    configs: dict[str, dict] = {}
    for name in _enabled_agent_files():
        configs[name] = _load(AI_DIR / f"{name}.yaml")
    return configs


def _agent_id_index() -> dict[str, dict]:
    """agent_id -> raw YAML dict，供跨 Agent 引用校验。"""
    return {cfg["agent_id"]: cfg for cfg in _agent_configs().values()}


def _is_router(cfg: dict) -> bool:
    return bool((cfg.get("features") or {}).get("router"))


def _is_orchestrator(cfg: dict) -> bool:
    return bool((cfg.get("features") or {}).get("mas_orchestrator"))


# --------------------------------------------------------------------------- #
# 1. handoff 白名单一致性
# --------------------------------------------------------------------------- #


def test_handoff_targets_are_valid_active_agents() -> None:
    """allowed_targets 中的每个目标（"*" 除外）必须是已启用的 agent_id。"""
    index = _agent_id_index()
    valid_ids = set(index)
    for agent_id, cfg in index.items():
        handoff = cfg.get("handoff") or {}
        targets = [str(t) for t in handoff.get("allowed_targets", [])]
        for target in targets:
            if target == "*":
                continue
            assert target in valid_ids, (
                f"{agent_id} 的 handoff.allowed_targets 引用了不存在的目标: {target}"
            )


def test_handoff_never_targets_router_or_self() -> None:
    """运行时禁止转交给 router（features.router），也不应自转交。"""
    index = _agent_id_index()
    router_ids = {aid for aid, cfg in index.items() if _is_router(cfg)}
    for agent_id, cfg in index.items():
        targets = [str(t) for t in (cfg.get("handoff") or {}).get("allowed_targets", [])]
        assert agent_id not in targets, f"{agent_id} 不应把自己列入 handoff 白名单"
        for target in targets:
            if target == "*":
                continue
            assert target not in router_ids, (
                f"{agent_id} 的 handoff 白名单不能指向路由 Agent: {target}"
            )


def test_handoff_max_hops_within_server_ceiling() -> None:
    """max_hops_per_session 服务端上限为 10。"""
    for agent_id, cfg in _agent_id_index().items():
        handoff = cfg.get("handoff") or {}
        if "max_hops_per_session" not in handoff:
            continue
        hops = int(handoff["max_hops_per_session"])
        assert 1 <= hops <= 10, f"{agent_id} 的 max_hops_per_session 越界: {hops}"


# --------------------------------------------------------------------------- #
# 2. MAS 能力登记覆盖率
# --------------------------------------------------------------------------- #


def test_all_expert_agents_registered_in_mas_capabilities() -> None:
    """agents.enabled 中每个“专家”都必须在 agent_capabilities.yaml 登记。

    router（纯分派入口）与 orchestrator（编排器本身）不作为可分派节点，豁免。
    """
    registered = set(_load(CAPABILITIES_YAML)["agents"])
    for name, cfg in _agent_configs().items():
        if _is_router(cfg) or _is_orchestrator(cfg):
            continue
        agent_id = cfg["agent_id"]
        assert agent_id in registered, (
            f"专家 {agent_id}（{name}.yaml）未在 MAS agent_capabilities.yaml 登记，"
            f"MAS 模式下会被编排器视为不存在"
        )


def test_mas_capabilities_have_no_stale_entries() -> None:
    """能力表不应登记已不存在的 agent_id（防删专家后遗留孤儿条目）。"""
    valid_ids = set(_agent_id_index())
    for agent_id in _load(CAPABILITIES_YAML)["agents"]:
        assert agent_id in valid_ids, (
            f"agent_capabilities.yaml 登记了不存在的 agent_id: {agent_id}"
        )


def test_all_enabled_agents_have_runtime_ability_records() -> None:
    """动态 handoff 目录必须覆盖每个启用 Agent。"""
    registered = set(_load(ABILITY_YAML)["agents"])
    for agent_id in _agent_id_index():
        assert agent_id in registered, f"{agent_id} 未登记到 agent_ability.yaml"


def test_runtime_ability_records_have_required_fields() -> None:
    required = {"summary", "capabilities", "not_suitable_for", "handoff_when", "preferred_inputs"}
    for agent_id, ability in _load(ABILITY_YAML)["agents"].items():
        assert required <= set(ability), f"{agent_id} 的能力目录缺少字段"
        assert ability["summary"]
        for key in required - {"summary"}:
            assert isinstance(ability[key], list) and ability[key], f"{agent_id}.{key} 不能为空"


def test_all_enabled_agent_prompts_follow_standard_section_order() -> None:
    """统一章节必须直接写入每个启用 Agent 的源提示词。"""
    for name, config in _agent_configs().items():
        prompt_file = str(config.get("prompt_file") or "").strip()
        assert prompt_file, f"{name}.yaml 缺少 prompt_file，无法验证源提示词结构"
        text = (AI_DIR / prompt_file).read_text(encoding="utf-8")
        positions = []
        for section in STANDARD_PROMPT_SECTIONS:
            heading = f"## {section}"
            assert heading in text, f"{prompt_file} 缺少统一章节：{section}"
            positions.append(text.index(heading))
        assert positions == sorted(positions), f"{prompt_file} 的统一章节顺序不正确"


# --------------------------------------------------------------------------- #
# 3. 路由提示词候选表一致性
# --------------------------------------------------------------------------- #


def test_router_prompt_catalog_ids_exist() -> None:
    """router.md 候选表中出现的 agent_id 必须是已启用的 Agent。"""
    text = ROUTER_PROMPT.read_text(encoding="utf-8")
    catalog_ids = re.findall(r"^\|\s*(agent-[a-z-]+|shania)\s*\|", text, re.MULTILINE)
    assert catalog_ids, "未能从 router.md 解析出候选表 agent_id，检查表格格式是否变化"
    valid_ids = set(_agent_id_index())
    for agent_id in catalog_ids:
        assert agent_id in valid_ids, (
            f"router.md 候选表引用了不存在的 agent_id: {agent_id}"
        )
