"""聊天 Runtime 选择入口。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from omichub.application.services.chat.runtimes.base import ChatRuntime, ChatRuntimeRequest
from omichub.application.services.chat.runtimes.direct_chat_runtime import DirectChatRuntime
from omichub.application.services.chat.runtimes.langgraph_runtime import LangGraphChatRuntime
from omichub.application.services.chat.runtimes.legacy_runtime import LegacyChatRuntime
from omichub.application.services.chat.runtimes.overdrive_runtime import OverdriveChatRuntime
from omichub.application.services.chat.runtimes.studio_runtime import StudioChatRuntime
from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk

if TYPE_CHECKING:
    from omichub.application.services.chat_service import ChatService


class ChatRouterService:
    """根据请求选择已经完成迁移的 Runtime。"""

    def __init__(self, service: ChatService) -> None:
        self._service = service

    def select_runtime(self, request: ChatRuntimeRequest) -> ChatRuntime:
        """未迁移分支统一回落到 Legacy，避免提前改变任何业务语义。"""
        runtime = str(request.runtime_context.get("runtime") or "").lower()
        if runtime == "direct":
            return DirectChatRuntime(self._service)
        if runtime == "langgraph":
            return LangGraphChatRuntime(self._service)
        if request.overdrive:
            return OverdriveChatRuntime(self._service)
        if request.mode == "studio":
            return StudioChatRuntime(self._service)
        return LegacyChatRuntime(self._service)

    async def stream(self, request: ChatRuntimeRequest) -> AsyncIterator[ChatChunk]:
        runtime = self.select_runtime(request)
        async for chunk in runtime.run(request):
            yield chunk
