"""LLM Provider 抽象接口"""

from collections.abc import AsyncIterator
from typing import Any, Protocol


class LLMProvider(Protocol):
    """LLM 提供者统一接口"""

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        """同步对话"""
        ...

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """流式对话 - 逐 token 返回"""
        ...

    async def embeddings(
        self, text: str, model: str = ""
    ) -> list[float]:
        """文本嵌入向量"""
        ...
