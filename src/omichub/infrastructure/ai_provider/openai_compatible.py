"""OpenAI 兼容 LLM Provider — 借鉴 Cherry Studio 的 ProviderManager 架构

使用 httpx 直接对接 OpenAI /chat/completions SSE 流式接口，
替代 litellm 依赖，降低运维复杂度（1 人维护原则）。

支持绝大多数国产模型（DeepSeek / Kimi / Qwen / 智谱等），
所有接口遵循 OpenAI Chat Completions API 规范。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel


@dataclass
class ChatChunk:
    """流式输出数据块 — SSE 事件的统一抽象"""

    type: str  # "text" | "tool_call" | "error" | "done"
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class OpenAICompatibleProvider:
    """OpenAI 兼容 Provider

    适用于绝大多数国产模型（Kimi / DeepSeek / Qwen / 通义千问 / 智谱等）。
    所有接口遵循 OpenAI Chat Completions API 规范。
    """

    def __init__(self, config: AIProviderConfigModel) -> None:
        self.config = config
        self.name = config.name
        self.model = config.model
        self.base_url = config.base_url.rstrip("/")
        self._api_key = config.api_key or ""
        self._timeout = config.timeout or 120

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """SSE 流式输出 — 对接 OpenAI /chat/completions 接口

        ``tools`` 为 OpenAI 标准工具定义列表；非空时注入请求，并在模型返回
        tool_calls 时累积分片，于流结束统一 yield 一个 type="tool_calls" chunk。
        """
        api_messages: list[dict[str, str]] = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(self._timeout, connect=10),
                    verify=True,
                    follow_redirects=True,
                ) as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response,
            ):
                if response.status_code == 401:
                    yield ChatChunk(
                        type="error",
                        content=f"API Key 无效或已过期，请检查模型 '{self.name}' 的配置",
                    )
                    return
                if response.status_code == 429:
                    yield ChatChunk(
                        type="error",
                        content=f"请求频率过高（模型: {self.name}），请稍后重试",
                    )
                    return
                if response.status_code == 404:
                    yield ChatChunk(
                        type="error",
                        content=f"模型 '{self.model}' 不存在，请检查模型名称是否正确",
                    )
                    return
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode()[:500] if body else f"HTTP {response.status_code}"
                    yield ChatChunk(
                        type="error",
                        content=f"请求失败（模型: {self.name}）: {detail}",
                    )
                    return

                buffer = ""
                # 累积流式 tool_calls 分片（OpenAI 按 index 分片下发）
                tool_acc: dict[int, dict[str, Any]] = {}

                async for chunk in response.aiter_text():
                    buffer += chunk
                    lines = buffer.split("\n")
                    buffer = lines.pop() if not buffer.endswith("\n") else ""

                    for line in lines:
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue

                        data = line[6:]
                        if data == "[DONE]":
                            if self._emit_tool_calls(tool_acc):
                                yield ChatChunk(
                                    type="tool_calls",
                                    metadata={"tool_calls": self._materialize_tool_calls(tool_acc)},
                                )
                            yield ChatChunk(type="done")
                            return

                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        if "error" in parsed:
                            err = parsed["error"]
                            yield ChatChunk(
                                type="error",
                                content=f"模型错误（{self.name}）: {err.get('message', '未知错误')}",
                            )
                            return

                        choices = parsed.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # DeepSeek 特有: reasoning_content（思考过程）
                        reasoning = delta.get("reasoning_content", "")
                        if reasoning:
                            yield ChatChunk(
                                type="text",
                                content=reasoning,
                                metadata={"is_reasoning": True},
                            )

                        content = delta.get("content", "")
                        if content:
                            yield ChatChunk(
                                type="text",
                                content=content,
                                metadata={
                                    "model": self.model,
                                    **({"usage": parsed["usage"]} if parsed.get("usage") else {}),
                                },
                            )

                        # 累积 tool_calls 分片，不逐片 yield
                        for tc in delta.get("tool_calls", []) or []:
                            idx = tc.get("index", 0)
                            slot = tool_acc.setdefault(idx, {
                                "id": "", "type": "function",
                                "function": {"name": "", "arguments": ""},
                            })
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            if tc.get("type"):
                                slot["type"] = tc["type"]
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                slot["function"]["name"] += fn["name"]
                            if fn.get("arguments"):
                                slot["function"]["arguments"] += fn["arguments"]

                        finish = choices[0].get("finish_reason")
                        if finish and finish != "null":
                            if finish == "content_filter":
                                yield ChatChunk(type="error", content="输出被内容安全过滤器拦截")
                                return

                # 流结束但未收到 [DONE]
                if self._emit_tool_calls(tool_acc):
                    yield ChatChunk(
                        type="tool_calls",
                        metadata={"tool_calls": self._materialize_tool_calls(tool_acc)},
                    )
                yield ChatChunk(type="done")

        except httpx.TimeoutException:
            yield ChatChunk(
                type="error",
                content=f"请求超时（{self._timeout}s），请检查网络或增加 Timeout（模型: {self.name}）",
            )
        except httpx.ConnectError:
            yield ChatChunk(
                type="error",
                content=f"无法连接到模型服务（{self.base_url}），请检查 Base URL（模型: {self.name}）",
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"LLM 调用异常: {e}")
            yield ChatChunk(
                type="error",
                content=f"调用模型时发生未预期错误（模型: {self.name}）: {e}",
            )

    async def validate(self) -> bool:
        """验证 API Key 和连接是否正常"""
        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=10, verify=True) as client:
                resp = await client.get(f"{self.base_url}/models", headers=headers)
                return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _emit_tool_calls(tool_acc: dict[int, dict[str, Any]]) -> bool:
        return bool(tool_acc) and any(
            slot["function"].get("name") for slot in tool_acc.values()
        )

    @staticmethod
    def _materialize_tool_calls(tool_acc: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        return [tool_acc[i] for i in sorted(tool_acc)]


class ProviderManager:
    """Provider 管理器 — 借鉴 Cherry Studio 的 ProviderRegistry

    单例模式，统一管理所有 LLM Provider 的创建、缓存和调用。
    当模型配置变更时，调用 clear_cache 清除缓存。
    """

    _instance: ProviderManager | None = None
    _providers: dict[str, OpenAICompatibleProvider] = {}

    def __new__(cls) -> ProviderManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_or_create(self, config: AIProviderConfigModel) -> OpenAICompatibleProvider:
        """获取或创建 Provider（带缓存）"""
        cache_key = str(config.id)
        if cache_key in self._providers:
            return self._providers[cache_key]

        provider = OpenAICompatibleProvider(config)
        self._providers[cache_key] = provider
        return provider

    def clear_cache(self, model_id: str | None = None) -> None:
        """清除 Provider 缓存"""
        if model_id:
            self._providers.pop(model_id, None)
        else:
            self._providers.clear()

    async def chat_stream(
        self,
        config: AIProviderConfigModel,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatChunk]:
        """统一入口：流式聊天"""
        provider = self.get_or_create(config)
        async for chunk in provider.chat_stream(messages, system_prompt, **kwargs):
            yield chunk


# 全局 Provider 管理器实例
provider_manager = ProviderManager()
