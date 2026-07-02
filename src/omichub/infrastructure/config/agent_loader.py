"""Agent YAML 加载器 —— 从 data/ai/*.yaml 加载助手配置

启动时由 AgentService 调用，按 OmicHub.yaml 中 agents.enabled 列表加载对应 YAML。
每个 YAML 文件定义一个助手的完整配置（模型、MCP、技能、提示词等）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from omichub.core.config import get_settings


def load_agent_configs() -> list[dict[str, Any]]:
    """加载启用的 Agent YAML 配置列表

    读取 OmicHub.yaml 的 agents.enabled，逐个加载 data/ai/{name}.yaml。
    文件不存在或解析失败时跳过并记录日志，不影响其他助手。
    """
    settings = get_settings()
    site_yaml_path = Path(settings.site_content_yaml)

    # 读取 OmicHub.yaml 获取 agents.enabled 列表
    enabled_names = _load_enabled_agents(site_yaml_path)
    if not enabled_names:
        return []

    # 逐个加载 data/ai/{name}.yaml
    agents_dir = site_yaml_path.parent / "ai"
    configs: list[dict[str, Any]] = []

    for name in enabled_names:
        yaml_path = agents_dir / f"{name}.yaml"
        config = _load_single_agent(yaml_path)
        if config:
            configs.append(config)

    return configs


def _load_enabled_agents(site_yaml_path: Path) -> list[str]:
    """从 OmicHub.yaml 读取 agents.enabled 列表"""
    if not site_yaml_path.exists():
        return []
    try:
        with site_yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        return []

    if not isinstance(data, dict):
        return []

    agents_section = data.get("agents", {})
    if not isinstance(agents_section, dict):
        return []

    enabled = agents_section.get("enabled", [])
    return [str(name) for name in enabled if name]


def _load_single_agent(yaml_path: Path) -> dict[str, Any] | None:
    """加载单个 Agent YAML 文件，失败返回 None"""
    if not yaml_path.exists():
        import logging
        logging.getLogger(__name__).warning(f"Agent YAML 不存在: {yaml_path}")
        return None

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Agent YAML 解析失败 {yaml_path}: {e}")
        return None

    if not isinstance(data, dict):
        return None

    # 必填字段校验
    if not data.get("agent_id"):
        import logging
        logging.getLogger(__name__).warning(f"Agent YAML 缺少 agent_id: {yaml_path}")
        return None

    return data
