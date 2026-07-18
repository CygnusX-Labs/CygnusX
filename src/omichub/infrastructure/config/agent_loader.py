"""Agent YAML 加载器 —— 从 data/ai/*.yaml 加载助手配置

启动时由 AgentService 调用，按 OmicHub.yaml 中 agents.enabled 列表加载对应 YAML。
每个 YAML 文件定义一个助手的完整配置（模型、MCP、技能、提示词等）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from omichub.core.config import get_settings
from omichub.infrastructure.config.prompt_loader import get_prompt
from omichub.infrastructure.config.runtime_image_loader import get_runtime_images


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

    prompt_ref = str(data.get("prompt_ref") or "").strip()
    if prompt_ref:
        prompt = get_prompt(prompt_ref)
        if not prompt:
            logging.getLogger(__name__).warning(
                "Agent prompt_ref 无法解析: %s -> %s", yaml_path, prompt_ref
            )
            return None
        data["system_prompt"] = prompt

    # 可选 studio 段（OmicStudio 工作台）：{enabled: bool, image?: str}
    # 结构非法时剔除该段，不影响 Agent 本体加载
    studio = data.get("studio")
    if studio is not None:
        if not isinstance(studio, dict):
            data.pop("studio", None)
        else:
            cleaned: dict[str, Any] = {}
            if "enabled" in studio:
                enabled = studio["enabled"]
                cleaned["enabled"] = (
                    enabled.strip().lower() in {"1", "true", "yes", "on"}
                    if isinstance(enabled, str)
                    else bool(enabled)
                )
            runtime_profile = str(studio.get("runtime_profile") or "").strip()
            required_capabilities = {
                str(value).strip()
                for value in studio.get("required_capabilities", [])
                if str(value).strip()
            }
            if runtime_profile:
                try:
                    _, profile = get_runtime_images().select(
                        required_capabilities, "studio", runtime_profile
                    )
                except (KeyError, ValueError, LookupError, RuntimeError) as exc:
                    logging.getLogger(__name__).warning(
                        "Agent Studio 运行时无效 %s: %s", yaml_path, exc
                    )
                    return None
                cleaned["runtime_profile"] = runtime_profile
                cleaned["required_capabilities"] = sorted(required_capabilities)
                cleaned["image"] = profile.image
            elif studio.get("image"):
                cleaned["image"] = str(studio["image"])
            data["studio"] = cleaned

    return data
