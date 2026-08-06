"""OpenAI 兼容 LLM Provider — 借鉴 Cherry Studio 的 ProviderManager 架构

使用 httpx 直接对接 OpenAI /chat/completions SSE 流式接口，
替代 litellm 依赖，降低运维复杂度（1 人维护原则）。

支持绝大多数国产模型（DeepSeek / Kimi / Qwen / 智谱等），
所有接口遵循 OpenAI Chat Completions API 规范。
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from omichub.core.telemetry import get_meter, get_tracer
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel


def _sanitize_log_message(message: str) -> str:
    """脱敏日志消息：抹去可能的 Bearer token / api_key 等敏感字段。"""
    if not message:
        return message
    # Bearer token
    message = re.sub(
        r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer [REDACTED]", message, flags=re.IGNORECASE
    )
    # api_key=... / "api_key": "..."
    message = re.sub(
        r"(api[_\-]?key['\"]?\s*[:=]\s*['\"])[a-zA-Z0-9_\-\.]{20,}(['\"])",
        r"\1[REDACTED]\2",
        message,
        flags=re.IGNORECASE,
    )
    return message


def _usage_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


# 带 tools 首尝空响应后，会降级为不带 tools 重试；此时系统词里仍描述着工具，
# 模型容易在正文里以文本形式「模拟」工具调用并编造结果。追加一条明确约束，
# 让模型直接用自然语言作答，而不是输出 <tool_use> 之类的伪调用文本。
_NO_TOOL_FALLBACK_NOTE = (
    "\n\n[重要] 当前这一轮工具调用接口不可用。请不要尝试调用任何工具，"
    "也不要在回复中以文本形式模拟工具调用（如 <tool_use> 标签或工具调用 JSON），"
    "更不要编造工具的返回结果；请直接用自然语言、基于已有信息回答用户。"
)


def _strip_tool_artifacts(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去掉历史消息里的工具调用痕迹，供「不带 tools」的降级重试使用。

    - 丢弃 role=tool 的工具结果消息；
    - 去掉 assistant 消息里的 tool_calls / tool_call_id 字段；
    - 若 assistant 消息只有工具调用、没有正文，则整条丢弃。
    """
    cleaned: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            cleaned.append(msg)
            continue
        role = msg.get("role")
        if role == "tool":
            continue
        if role == "assistant" and msg.get("tool_calls"):
            content = msg.get("content")
            if not content:
                continue
            stripped = {k: v for k, v in msg.items() if k not in {"tool_calls", "tool_call_id"}}
            cleaned.append(stripped)
            continue
        cleaned.append({k: v for k, v in msg.items() if k != "tool_call_id"})
    return cleaned


def normalize_token_usage(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """把不同 OpenAI 兼容服务的 usage 字段统一为标准三字段。"""
    if not isinstance(usage, dict):
        return None
    source = usage.get("token_usage") if isinstance(usage.get("token_usage"), dict) else usage
    prompt_tokens = _usage_int(
        source.get("prompt_tokens") or source.get("input_tokens") or source.get("input")
    )
    completion_tokens = _usage_int(
        source.get("completion_tokens") or source.get("output_tokens") or source.get("output")
    )
    total_tokens = _usage_int(source.get("total_tokens") or source.get("total"))
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    normalized = dict(usage)
    normalized.update(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    return normalized


def merge_token_usage(
    accumulated: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """累计多次模型请求的 token 用量（Studio 工具循环会产生多轮请求）。"""
    left = normalize_token_usage(accumulated)
    right = normalize_token_usage(current)
    if right is None:
        return left
    if left is None:
        return right
    return {
        "prompt_tokens": left["prompt_tokens"] + right["prompt_tokens"],
        "completion_tokens": left["completion_tokens"] + right["completion_tokens"],
        "total_tokens": left["total_tokens"] + right["total_tokens"],
    }


@dataclass
class ChatChunk:
    """流式输出数据块 — SSE 事件的统一抽象"""

    type: str  # "text" | "tool_calls" | "tool_call" | "tool_output" | "tool_result" | "plan" | "ask_request" | "approval_request" | "approval_resolved" | "error" | "done"
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ===== AI 调用遥测指标（全局代理 meter，未初始化时为 noop）=====
_ai_meter = get_meter("omichub.ai")
_ai_duration = _ai_meter.create_histogram(
    "ai.chat.duration", unit="ms", description="AI 模型调用耗时"
)
_ai_tokens = _ai_meter.create_counter(
    "ai.tokens", description="AI 模型 token 用量（按 prompt/completion 分）"
)


def record_ai_call_metrics(
    provider: str,
    model: str,
    status: str,
    duration_ms: float,
    usage: dict[str, Any] | None,
) -> None:
    """记录一次 AI 调用的耗时与 token 指标（容错，绝不抛异常）。

    同时把调用写入应用内指标缓冲（core.ai_metrics），供管理端趋势聚合与告警；
    该落库路径与 OTel 导出互补，任何失败都被吞掉，不影响调用链。
    """
    try:
        attrs = {"ai.provider": provider, "ai.model": model, "ai.status": status}
        _ai_duration.record(duration_ms, attrs)
        if usage:
            _ai_tokens.add(int(usage.get("prompt_tokens", 0)), {**attrs, "ai.token.kind": "prompt"})
            _ai_tokens.add(
                int(usage.get("completion_tokens", 0)),
                {**attrs, "ai.token.kind": "completion"},
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        from omichub.core.ai_metrics import record_ai_call
        from omichub.middleware.trace_context import get_session_id

        record_ai_call(provider, model, status, duration_ms, usage, get_session_id() or None)
    except Exception:  # noqa: BLE001
        pass


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
        deep_thinking: bool = False,
    ) -> AsyncIterator[ChatChunk]:
        """SSE 流式输出 — 对接 OpenAI /chat/completions 接口

        ``tools`` 为 OpenAI 标准工具定义列表；非空时注入请求，并在模型返回
        tool_calls 时累积分片，于流结束统一 yield 一个 type="tool_calls" chunk。
        ``deep_thinking`` 为 True 时注入 enable_thinking 参数（Qwen3 / DeepSeek 等）。

        内置空响应重试：若首次流式调用未产生任何 text/tool_calls chunk，
        自动重试一次；两次均空则 yield error。
        """
        has_yielded_text = False
        has_tool_calls = False
        last_usage: dict[str, Any] | None = None
        last_finish_reason: str | None = None
        retry_without_tools = False

        for attempt in range(2):
            attempt_had_text = False
            attempt_had_error = False
            attempt_tools = None if retry_without_tools else tools
            attempt_messages = messages
            attempt_system_prompt = system_prompt
            if retry_without_tools and tools:
                logger.info(f"模型 '{self.name}' 带 tools 返回空，尝试不带 tools 重试")
                # 降级为纯对话：系统词追加工具不可用说明，并清掉历史里的工具调用
                # 痕迹（tool 角色消息 / assistant 的 tool_calls 字段），避免模型在
                # 正文里以文本形式模拟工具调用、编造结果，也避免无 tools 时请求非法。
                attempt_system_prompt = (system_prompt or "") + _NO_TOOL_FALLBACK_NOTE
                attempt_messages = _strip_tool_artifacts(messages)

            async for chunk in self._stream_once(
                attempt_messages,
                attempt_system_prompt,
                temperature,
                max_tokens,
                attempt_tools,
                deep_thinking,
            ):
                if chunk.type == "text":
                    has_yielded_text = True
                    attempt_had_text = True
                    yield chunk
                elif chunk.type == "tool_calls":
                    has_tool_calls = True
                    yield chunk
                elif chunk.type == "done":
                    last_usage = chunk.metadata.get("usage")
                    last_finish_reason = chunk.metadata.get("finish_reason") or last_finish_reason
                elif chunk.type == "error":
                    attempt_had_error = True
                    if (
                        attempt == 0
                        and not has_yielded_text
                        and not has_tool_calls
                        and chunk.metadata.get("retryable")
                    ):
                        logger.warning(f"模型 '{self.name}' 瞬时网络失败且尚未输出，自动重试一次")
                        break
                    yield chunk
                    return
                else:
                    yield chunk

            if attempt_had_error and attempt == 0 and not has_yielded_text and not has_tool_calls:
                continue
            if attempt_had_text or attempt_had_error or has_tool_calls:
                break
            if attempt == 0:
                retry_without_tools = bool(tools)
                logger.info(f"模型 '{self.name}' 返回空内容，自动重试一次")

        if not has_yielded_text and not has_tool_calls:
            logger.error(
                f"[LLM空响应] provider={self.name} model={self.model} "
                f"messages={len(messages)} tools={bool(tools)} deep_thinking={deep_thinking}"
            )
            yield ChatChunk(
                type="error",
                content=f"当前模型 '{self.name}' 响应为空，请重新发送",
            )
        else:
            done_meta: dict[str, Any] = {}
            if last_usage:
                done_meta["usage"] = last_usage
            if last_finish_reason:
                done_meta["finish_reason"] = last_finish_reason
            yield ChatChunk(type="done", metadata=done_meta)

    async def _stream_once(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
        deep_thinking: bool,
    ) -> AsyncIterator[ChatChunk]:
        """单次流式 HTTP 调用（不含重试逻辑）"""
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
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if deep_thinking:
            payload["enable_thinking"] = True
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            logger.debug(
                f"[LLM请求] provider={self.name} model={self.model} "
                f"messages={len(api_messages)} tools={bool(tools)} deep_thinking={deep_thinking}"
            )
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
                    logger.error(
                        f"[LLM请求失败] provider={self.name} model={self.model} "
                        f"status={response.status_code} detail={detail}"
                    )
                    yield ChatChunk(
                        type="error",
                        content=f"请求失败（模型: {self.name}）: {detail}",
                    )
                    return

                buffer = ""
                # 累积流式 tool_calls 分片（OpenAI 按 index 分片下发）
                tool_acc: dict[int, dict[str, Any]] = {}
                usage: dict[str, Any] | None = None
                last_finish_reason: str | None = None

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
                            done_meta: dict[str, Any] = {}
                            if usage:
                                done_meta["usage"] = usage
                            if last_finish_reason:
                                done_meta["finish_reason"] = last_finish_reason
                            yield ChatChunk(type="done", metadata=done_meta)
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

                        # 有些 provider 在 choices 为空时下发 usage
                        if parsed.get("usage"):
                            usage = normalize_token_usage(parsed["usage"])

                        # 有些 provider（如 OpenAI 兼容）在 choices 最后一块带 usage
                        if choices and choices[0].get("usage"):
                            usage = normalize_token_usage(choices[0]["usage"])

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
                                metadata={"model": self.model},
                            )

                        # 累积 tool_calls 分片，不逐片 yield
                        for tc in delta.get("tool_calls", []) or []:
                            idx = tc.get("index", 0)
                            slot = tool_acc.setdefault(
                                idx,
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                },
                            )
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
                            last_finish_reason = finish
                            if finish == "content_filter":
                                yield ChatChunk(type="error", content="输出被内容安全过滤器拦截")
                                return

                # 流结束但未收到 [DONE]
                if self._emit_tool_calls(tool_acc):
                    yield ChatChunk(
                        type="tool_calls",
                        metadata={"tool_calls": self._materialize_tool_calls(tool_acc)},
                    )
                done_meta = {}
                if usage:
                    done_meta["usage"] = usage
                if last_finish_reason:
                    done_meta["finish_reason"] = last_finish_reason
                yield ChatChunk(type="done", metadata=done_meta)

        except httpx.TimeoutException:
            yield ChatChunk(
                type="error",
                content=f"请求超时（{self._timeout}s），请检查网络或增加 Timeout（模型: {self.name}）",
                metadata={"retryable": True},
            )
        except httpx.NetworkError:
            yield ChatChunk(
                type="error",
                content=f"模型服务连接中断（{self.base_url}），请检查网络或 Base URL（模型: {self.name}）",
                metadata={"retryable": True},
            )
        except Exception as e:  # noqa: BLE001
            safe_msg = _sanitize_log_message(str(e))
            logger.error(f"LLM 调用异常: {safe_msg}")
            yield ChatChunk(
                type="error",
                content=f"调用模型时发生未预期错误（模型: {self.name}）: {safe_msg}",
            )

    async def validate(self) -> bool:
        """验证 API Key 和连接是否正常"""
        try:
            models = await self.list_models()
            return len(models) > 0
        except Exception:  # noqa: BLE001
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """调用 /v1/models 返回远程模型列表。"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10, verify=True) as client:
            resp = await client.get(f"{self.base_url}/models", headers=headers)
            if resp.status_code == 401:
                raise RuntimeError(f"API Key 无效或已过期（模型: {self.name}）")
            if resp.status_code == 404:
                raise RuntimeError(f"该 Provider 不支持 /v1/models 端点（模型: {self.name}）")
            if resp.status_code >= 400:
                body = (await resp.aread()).decode()[:500]
                raise RuntimeError(f"发现模型失败（模型: {self.name}）: {body}")
            data = resp.json()
            models = data.get("data", [])
            return [
                {
                    "id": m.get("id", ""),
                    "name": m.get("name") or m.get("id", ""),
                    "owned_by": m.get("owned_by", "unknown"),
                }
                for m in models
                if m.get("id")
            ]

    @staticmethod
    def _emit_tool_calls(tool_acc: dict[int, dict[str, Any]]) -> bool:
        return bool(tool_acc) and any(slot["function"].get("name") for slot in tool_acc.values())

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
        """统一入口：流式聊天（带 Trace/Log/Metrics 埋点）"""
        provider = self.get_or_create(config)
        tracer = get_tracer("omichub.ai")
        with tracer.start_as_current_span(
            "ai.chat",
            attributes={"ai.provider": provider.name, "ai.model": provider.model},
        ) as span:
            start = time.perf_counter()
            status = "success"
            usage: dict[str, Any] | None = None
            finish_reason: str | None = None
            try:
                async for chunk in provider.chat_stream(messages, system_prompt, **kwargs):
                    if chunk.type == "done":
                        usage = normalize_token_usage(chunk.metadata.get("usage"))
                        finish_reason = chunk.metadata.get("finish_reason") or finish_reason
                    elif chunk.type == "error":
                        status = "error"
                    yield chunk
            except Exception as exc:  # noqa: BLE001
                status = "error"
                span.record_exception(exc)
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                span.set_attribute("ai.status", status)
                span.set_attribute("ai.duration_ms", round(duration_ms, 2))
                if finish_reason:
                    span.set_attribute("ai.finish_reason", finish_reason)
                if usage:
                    span.set_attribute("ai.prompt_tokens", usage.get("prompt_tokens", 0))
                    span.set_attribute("ai.completion_tokens", usage.get("completion_tokens", 0))
                    span.set_attribute("ai.total_tokens", usage.get("total_tokens", 0))
                record_ai_call_metrics(provider.name, provider.model, status, duration_ms, usage)
                logger.bind(
                    event="ai.chat",
                    provider=provider.name,
                    model=provider.model,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                    finish_reason=finish_reason,
                    usage=usage,
                ).info("ai.chat completed")


# 全局 Provider 管理器实例
provider_manager = ProviderManager()
