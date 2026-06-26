"""AI Provider 配置应用服务"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.ai_provider import (
    AIProviderConfigCreateDTO,
    AIProviderConfigDTO,
    AIProviderConfigTestResponse,
    AIProviderConfigUpdateDTO,
)
from omichub.core.exceptions import NotFoundError
from omichub.domain.ai_provider.entities import AIProviderConfig
from omichub.domain.ai_provider.services import AIProviderConfigDomainService
from omichub.domain.ai_provider.value_objects import ProviderType
from omichub.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
from omichub.infrastructure.database.repositories.ai_provider_repository import (
    SqlAlchemyAIProviderConfigRepository,
)


def _to_dto(config: AIProviderConfig) -> AIProviderConfigDTO:
    return AIProviderConfigDTO(
        id=config.id,
        name=config.name,
        provider_type=config.provider_type.value,
        model=config.model,
        base_url=config.base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        top_p=config.top_p,
        timeout=config.timeout,
        is_active=config.is_active,
        is_default=config.is_default,
        extra_params=config.extra_params,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


class AIProviderConfigService:
    """AI Provider 配置应用服务"""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = SqlAlchemyAIProviderConfigRepository(db)
        self._domain = AIProviderConfigDomainService(self._repo)

    async def list_configs(self) -> list[AIProviderConfigDTO]:
        configs = await self._repo.list_all()
        return [_to_dto(c) for c in configs]

    async def get_config(self, config_id: UUID) -> AIProviderConfigDTO:
        config = await self._repo.get_by_id(config_id)
        if config is None:
            raise NotFoundError("AI Provider 配置不存在")
        return _to_dto(config)

    async def create_config(self, dto: AIProviderConfigCreateDTO) -> AIProviderConfigDTO:
        config = AIProviderConfig.create(
            name=dto.name,
            provider_type=ProviderType(dto.provider_type),
            model=dto.model,
            base_url=dto.base_url,
            api_key=dto.api_key,
            temperature=dto.temperature,
            max_tokens=dto.max_tokens,
            top_p=dto.top_p,
            timeout=dto.timeout,
            extra_params=dto.extra_params,
        )
        self._domain.validate(config)
        config = await self._domain.prepare_new_default(config)
        config = await self._repo.save(config)
        return _to_dto(config)

    async def update_config(
        self, config_id: UUID, dto: AIProviderConfigUpdateDTO
    ) -> AIProviderConfigDTO:
        config = await self._repo.get_by_id(config_id)
        if config is None:
            raise NotFoundError("AI Provider 配置不存在")

        config.name = dto.name
        config.provider_type = ProviderType(dto.provider_type)
        config.model = dto.model
        config.base_url = dto.base_url
        config.temperature = dto.temperature
        config.max_tokens = dto.max_tokens
        config.top_p = dto.top_p
        config.timeout = dto.timeout
        config.is_active = dto.is_active
        config.extra_params = dto.extra_params
        if dto.api_key:
            config.api_key = dto.api_key
        config.mark_updated()

        self._domain.validate(config)
        config = await self._repo.save(config)
        return _to_dto(config)

    async def delete_config(self, config_id: UUID) -> bool:
        return await self._repo.delete(config_id)

    async def set_default(self, config_id: UUID) -> AIProviderConfigDTO:
        config = await self._domain.set_default(config_id)
        return _to_dto(config)

    async def test_config(self, config_id: UUID, message: str = "") -> AIProviderConfigTestResponse:
        config = await self._repo.get_by_id(config_id)
        if config is None:
            raise NotFoundError("AI Provider 配置不存在")
        try:
            provider = LiteLLMProvider(config)
            response = await provider.chat(
                messages=[{"role": "user", "content": message or "你好，请简要介绍一下自己。"}]
            )
            content = ""
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "") or ""
            return AIProviderConfigTestResponse(success=True, response=str(content))
        except Exception as e:  # noqa: BLE001
            return AIProviderConfigTestResponse(success=False, error=str(e))

    async def get_active_default(self) -> AIProviderConfig | None:
        return await self._repo.get_default()
