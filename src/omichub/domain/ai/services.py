"""AI 域服务 - 上下文管理、工具编排"""

from uuid import UUID

from omichub.domain.ai.entities import Conversation
from omichub.domain.ai.repositories import IConversationRepository


class AIDomainService:
    """AI 域服务"""

    def __init__(self, repo: IConversationRepository):
        self._repo = repo

    async def create_conversation(
        self, user_id: UUID, title: str = "新对话", model: str = ""
    ) -> Conversation:
        """创建新对话"""
        # TODO: 实现
        raise NotImplementedError

    async def build_context_messages(
        self, conversation: Conversation, system_prompt: str
    ) -> list[dict[str, str]]:
        """构建发送给 LLM 的消息列表"""
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for msg in conversation.context_window.messages:
            messages.append({"role": msg.role.value, "content": msg.content})
        return messages

    async def compress_context(self, conversation: Conversation) -> Conversation:
        """长对话上下文压缩（摘要）"""
        # TODO: 调用 LLM 生成摘要
        conversation.context_window.truncate()
        return await self._repo.save(conversation)
