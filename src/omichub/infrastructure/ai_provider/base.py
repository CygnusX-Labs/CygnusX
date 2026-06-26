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
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """非流式对话；传入 tools 时返回可能包含 tool_calls"""
        ...

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """流式对话 - 逐 token 返回（async generator，调用无需 await）"""
        ...

    async def embeddings(
        self, text: str, model: str = ""
    ) -> list[float]:
        """文本嵌入向量"""
        ...
