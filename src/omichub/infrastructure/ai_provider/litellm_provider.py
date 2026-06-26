"""LiteLLM 适配器 — 统一支持 100+ LLM provider"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import litellm
from loguru import logger

from omichub.core.config import get_settings
from omichub.domain.ai_provider.entities import AIProviderConfig


class LiteLLMProvider:
    """LiteLLM Provider 适配器

    通过 OpenAI 兼容格式统一调用各类 LLM，支持异步流式、工具调用、自定义 base_url。
    """

    def __init__(self, config: AIProviderConfig | None = None) -> None:
        self._config = config
        self._settings = get_settings()

    async def _get_config(self) -> AIProviderConfig | None:
        """获取生效配置：显式配置 > 数据库默认配置 > None"""
        if self._config is not None:
            return self._config

        # 尝试从数据库读取默认配置
        settings = self._settings
        if settings.ai_default_provider_id:
            try:
                from omichub.infrastructure.database.repositories.ai_provider_repository import (
                    SqlAlchemyAIProviderConfigRepository,
                )
                from omichub.infrastructure.database.session import get_session_factory

                factory = get_session_factory()
                if factory is not None:
                    from uuid import UUID

                    async with factory() as session:
                        repo = SqlAlchemyAIProviderConfigRepository(session)
                        config = await repo.get_by_id(UUID(settings.ai_default_provider_id))
                        if config and config.is_active:
                            return config
            except Exception as e:  # noqa: BLE001
                logger.debug(f"读取默认 AI Provider 失败: {e}")

        try:
            from omichub.infrastructure.database.session import get_session_factory

            factory = get_session_factory()
            if factory is not None:
                from omichub.infrastructure.database.repositories.ai_provider_repository import (
                    SqlAlchemyAIProviderConfigRepository,
                )

                async with factory() as session:
                    repo = SqlAlchemyAIProviderConfigRepository(session)
                    return await repo.get_default()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"读取默认 AI Provider 失败: {e}")

        return None

    def _build_kwargs(
        self, config: AIProviderConfig | None, messages: list[dict[str, str]], **overrides: Any
    ) -> dict[str, Any]:
        """构建 LiteLLM 调用参数"""
        if config is not None:
            kwargs: dict[str, Any] = {
                "model": config.model,
                "messages": messages,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "top_p": config.top_p,
                "timeout": config.timeout,
            }
            if config.api_key:
                kwargs["api_key"] = config.api_key
            if config.base_url:
                kwargs["api_base"] = config.base_url
            if config.extra_params:
                kwargs.update(config.extra_params)
        else:
            # 兜底：使用环境变量中的 Kimi/OpenAI 配置
            kwargs = {
                "model": self._settings.kimi_model,
                "messages": messages,
                "temperature": self._settings.ai_temperature,
                "api_key": self._settings.kimi_api_key,
                "api_base": self._settings.kimi_base_url,
            }
            if self._settings.openai_api_key and self._settings.llm_provider == "openai":
                kwargs.update(
                    {
                        "model": self._settings.openai_model,
                        "api_key": self._settings.openai_api_key,
                        "api_base": self._settings.openai_base_url,
                    }
                )

        # 覆盖参数
        for key in ("temperature", "max_tokens", "top_p", "timeout", "tools"):
            if key in overrides:
                kwargs[key] = overrides[key]

        return kwargs

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """非流式对话"""
        overrides: dict[str, Any] = {}
        if model:
            overrides["model"] = model
        if temperature is not None:
            overrides["temperature"] = temperature
        if tools is not None:
            overrides["tools"] = tools

        config = await self._get_config()
        kwargs = self._build_kwargs(config, messages, **overrides)
        logger.debug(f"LiteLLM chat call: model={kwargs.get('model')}")
        response = await litellm.acompletion(**kwargs)
        return response.model_dump() if hasattr(response, "model_dump") else dict(response)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """流式对话 - 逐 token 返回"""
        overrides: dict[str, Any] = {"stream": True}
        if model:
            overrides["model"] = model
        if temperature is not None:
            overrides["temperature"] = temperature

        config = await self._get_config()
        kwargs = self._build_kwargs(config, messages, **overrides)
        logger.debug(f"LiteLLM stream call: model={kwargs.get('model')}")
        try:
            stream = await litellm.acompletion(**kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue
                content = delta.content or ""
                if content:
                    yield content
        except Exception as e:  # noqa: BLE001
            logger.warning(f"LiteLLM 流式调用失败: {e}")
            raise

    async def is_configured(self) -> bool:
        """检查是否已配置有效 API Key 与模型"""
        config = await self._get_config()
        if config is not None:
            return bool(config.api_key) and bool(config.model)
        if self._settings.llm_provider == "openai":
            return bool(self._settings.openai_api_key) and bool(self._settings.openai_model)
        return bool(self._settings.kimi_api_key) and bool(self._settings.kimi_model)

    async def embeddings(self, text: str, model: str = "") -> list[float]:
        """文本嵌入向量（可选能力）"""
        config = await self._get_config()
        kwargs: dict[str, Any] = {"input": text}
        if model:
            kwargs["model"] = model
        elif config is not None:
            kwargs["model"] = config.model
        else:
            kwargs["model"] = "text-embedding-3-small"

        if config is not None:
            if config.api_key:
                kwargs["api_key"] = config.api_key
            if config.base_url:
                kwargs["api_base"] = config.base_url
        else:
            kwargs["api_key"] = self._settings.openai_api_key or self._settings.kimi_api_key

        response = await litellm.aembedding(**kwargs)
        data: dict[str, Any] = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        embedding_data: list[dict[str, Any]] = data.get("data", [{}])
        embedding: list[float] = embedding_data[0].get("embedding", []) if embedding_data else []
        return embedding
