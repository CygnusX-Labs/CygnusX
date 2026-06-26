"""AI Provider YAML 配置加载器

支持从外置 YAML 文件同步 Provider 配置到数据库，便于 Docker / GitOps 部署。
YAML 中可使用 ${ENV_VAR} 或 ${ENV_VAR:-default} 语法引用环境变量。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, cast

import yaml
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.services.ai_provider_service import AIProviderConfigService
from omichub.core.config import get_settings
from omichub.domain.ai_provider.value_objects import ProviderType
from omichub.infrastructure.database.repositories.ai_provider_repository import (
    SqlAlchemyAIProviderConfigRepository,
)

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _interpolate_env(value: Any) -> Any:
    """递归替换字符串中的 ${ENV} / ${ENV:-default}"""
    if isinstance(value, str):
        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2)
            return os.environ.get(var_name, default if default is not None else "")
        return _ENV_PATTERN.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    return value


def _load_yaml(path: str) -> dict[str, Any]:
    """读取并解析 YAML，返回 providers 列表"""
    file_path = Path(path)
    if not file_path.exists():
        return {"providers": []}

    with open(file_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return cast(dict[str, Any], _interpolate_env(raw))


class AIProviderYamlLoader:
    """将 YAML 中的 Provider 配置同步到数据库"""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = SqlAlchemyAIProviderConfigRepository(db)
        self._service = AIProviderConfigService(db)

    async def load_and_sync(self) -> int:
        """加载 YAML 并同步，返回同步的 Provider 数量"""
        settings = get_settings()
        path = settings.ai_provider_config_yaml

        data = _load_yaml(path)
        providers = data.get("providers", [])
        if not providers:
            logger.debug(f"AI Provider YAML 未配置或为空: {path}")
            return 0

        existing = {c.name: c for c in await self._repo.list_all()}
        synced = 0
        any_default = False

        for item in providers:
            name = item.get("name", "")
            if not name:
                logger.warning("YAML 中存在未命名的 AI Provider，已跳过")
                continue

            is_default = bool(item.get("is_default", False))
            if is_default:
                any_default = True

            provider_type = ProviderType(
                item.get("provider_type", ProviderType.OPENAI_COMPATIBLE.value)
            )

            if name in existing:
                config = existing[name]
                config.provider_type = provider_type
                config.model = item.get("model", config.model)
                config.base_url = item.get("base_url", config.base_url)
                config.api_key = item.get("api_key", config.api_key)
                config.temperature = float(item.get("temperature", config.temperature))
                config.max_tokens = int(item.get("max_tokens", config.max_tokens))
                config.top_p = float(item.get("top_p", config.top_p))
                config.timeout = int(item.get("timeout", config.timeout))
                config.is_active = bool(item.get("is_active", config.is_active))
                config.is_default = is_default
                config.extra_params = item.get("extra_params", config.extra_params)
                config.mark_updated()
                logger.info(f"已更新 AI Provider: {name}")
            else:
                from omichub.domain.ai_provider.entities import AIProviderConfig

                config = AIProviderConfig.create(
                    name=name,
                    provider_type=provider_type,
                    model=item.get("model", ""),
                    base_url=item.get("base_url", ""),
                    api_key=item.get("api_key", ""),
                    temperature=float(item.get("temperature", 0.7)),
                    max_tokens=int(item.get("max_tokens", 2048)),
                    top_p=float(item.get("top_p", 1.0)),
                    timeout=int(item.get("timeout", 120)),
                    extra_params=item.get("extra_params", {}),
                )
                config.is_active = bool(item.get("is_active", True))
                config.is_default = is_default
                self._db.add(config)
                logger.info(f"已创建 AI Provider: {name}")

            synced += 1

        # 若 YAML 中没有任何默认配置，则将第一个 active 配置设为默认
        if not any_default:
            configs = await self._repo.list_all()
            active = [c for c in configs if c.is_active]
            if active and not any(c.is_default for c in configs):
                active[0].is_default = True
                active[0].mark_updated()
                logger.info(f"自动将 {active[0].name} 设为默认 AI Provider")

        await self._db.flush()
        return synced
