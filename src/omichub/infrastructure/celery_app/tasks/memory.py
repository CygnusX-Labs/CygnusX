"""长期记忆的低优先级异步维护任务。"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from celery import shared_task
from sqlalchemy import select


def _conversation_text(messages: list[Any], *, limit: int = 8_000) -> str:
    """将会话压缩为可发送给摘要模型的纯文本，并避免把工具元数据送出。"""
    lines: list[str] = []
    used = 0
    for message in messages[-30:]:
        role = str(getattr(message, "role", ""))
        content = str(getattr(message, "content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        line = f"{role}: {content}"
        remaining = limit - used
        if remaining <= 0:
            break
        lines.append(line[:remaining])
        used += len(line)
    return "\n".join(lines)


def _summary_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = str(message.get("content", "")).strip()
    return re.sub(r"\s+", " ", content)[:200]


@shared_task(name="omichub.infrastructure.celery_app.tasks.memory.summarize_session")
def summarize_session(session_id: str) -> dict[str, str]:
    return asyncio.run(_summarize_session(session_id))


async def _summarize_session(session_id: str) -> dict[str, str]:
    from omichub.application.services.agent_memory_service import AgentMemoryService
    from omichub.core.config import get_settings
    from omichub.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
    from omichub.infrastructure.database.models.chat import ChatMessageModel, ChatSessionModel
    from omichub.infrastructure.database.session import get_session_factory

    settings = get_settings()
    if not settings.agent_memory_auto_summary_enabled:
        return {"status": "disabled"}

    async with get_session_factory()() as session:
        chat_session = await session.scalar(
            select(ChatSessionModel).where(ChatSessionModel.session_id == session_id)
        )
        if chat_session is None:
            return {"status": "missing"}
        messages = list(
            (await session.scalars(
                select(ChatMessageModel)
                .where(ChatMessageModel.session_id == session_id)
                .order_by(ChatMessageModel.created_at.asc())
            )).all()
        )
        if len(messages) < max(2, settings.agent_memory_auto_summary_min_messages):
            return {"status": "too_short"}
        conversation = _conversation_text(messages)
        if not conversation:
            return {"status": "empty"}

        provider = LiteLLMProvider()
        response = await provider.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "将以下科研助手会话提炼为一条跨会话有价值的自包含事实。"
                        "只输出一句中文，不超过 200 字；不要包含密钥、原始数据、工具调用细节或臆测。"
                    ),
                },
                {"role": "user", "content": conversation},
            ],
            model=settings.agent_memory_summary_model.strip(),
            temperature=0.1,
        )
        content = _summary_content(response)
        if not content:
            return {"status": "empty_model_response"}

        memory_service = AgentMemoryService(session)
        try:
            await memory_service.save_memory(
                user_id=chat_session.user_id,
                agent_id=chat_session.agent_id or None,
                scope="summary",
                content=content,
                source_session=session_id,
                confidence=0.7,
            )
        except Exception:
            return {"status": "rejected"}
        await session.commit()
        return {"status": "summarized"}


@shared_task(name="omichub.infrastructure.celery_app.tasks.memory.backfill_embeddings")
def backfill_embeddings(limit: int = 100) -> dict[str, int | str]:
    """为启用语义召回前产生的历史记忆补齐向量；由运维按需触发。"""
    return asyncio.run(_backfill_embeddings(limit))


async def _backfill_embeddings(limit: int) -> dict[str, int | str]:
    from omichub.application.services.agent_memory_service import AgentMemoryService
    from omichub.core.config import get_settings
    from omichub.infrastructure.database.models.agent_memory import AgentMemoryModel
    from omichub.infrastructure.database.session import get_session_factory

    settings = get_settings()
    if not (
        settings.agent_memory_semantic_retrieval_enabled
        and settings.agent_memory_embedding_model.strip()
    ):
        return {"status": "disabled", "updated": 0}
    async with get_session_factory()() as session:
        rows = list(
            (await session.scalars(
                select(AgentMemoryModel)
                .where(
                    AgentMemoryModel.status == "active",
                    AgentMemoryModel.embedding.is_(None),
                )
                .order_by(AgentMemoryModel.updated_at.asc())
                .limit(max(1, min(limit, 500)))
            )).all()
        )
        service = AgentMemoryService(session)
        for memory in rows:
            await service._populate_embedding(memory)
        await session.commit()
        return {"status": "completed", "updated": len(rows)}
