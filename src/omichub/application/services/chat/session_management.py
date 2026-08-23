"""聊天会话标题、检索与 CRUD 管理能力。"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import anyio
from loguru import logger
from sqlalchemy import desc, select

from omichub.application.schemas.chat import (
    ChatMessageDTO,
    ChatSearchContentMatchDTO,
    ChatSessionDTO,
    ChatSessionSearchDTO,
)
from omichub.core.exceptions import NotFoundError
from omichub.infrastructure.ai_provider.openai_compatible import provider_manager
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel
from omichub.infrastructure.database.models.chat import ChatMessageModel, ChatSessionModel


class ChatSessionManagement:
    """供聊天 Runtime 和门面服务复用的会话管理混入。"""

    @staticmethod
    def _requires_fresh_web_search(
        query: str,
        features: dict[str, Any] | None = None,
    ) -> bool:
        """判断问题是否必须先联网核验，避免把模型记忆当作最新事实。"""
        from omichub.application.services.chat.configuration import FRESHNESS_SEARCH_TRIGGERS

        policy = (features or {}).get("web_search", {}) if isinstance(features, dict) else {}
        if policy is False:
            return False
        policy = policy if isinstance(policy, dict) else {}
        if str(policy.get("mode") or "").lower() in {"off", "disabled"}:
            return False
        configured_triggers = policy.get("triggers", [])
        if not isinstance(configured_triggers, (list, tuple, set)):
            configured_triggers = []
        triggers = [*FRESHNESS_SEARCH_TRIGGERS, *configured_triggers]
        normalized_query = query.casefold()
        return any(str(trigger).casefold() in normalized_query for trigger in triggers if trigger)

    @staticmethod
    def _web_search_is_disabled(features: dict[str, Any] | None = None) -> bool:
        """Return whether an Agent explicitly disables external search."""
        policy = (features or {}).get("web_search", {}) if isinstance(features, dict) else {}
        if policy is False:
            return True
        policy = policy if isinstance(policy, dict) else {}
        return str(policy.get("mode") or "").lower() in {"off", "disabled"}

    @staticmethod
    def _requires_professional_evidence_search(
        query: str,
        messages: list[dict[str, Any]],
        features: dict[str, Any] | None = None,
    ) -> bool:
        """Expose web fallback for professional learning without searching the web first."""
        from omichub.application.services.chat.configuration import (
            BIOINFORMATICS_DOMAIN_TRIGGERS,
            PROFESSIONAL_LEARNING_TRIGGERS,
        )

        if ChatSessionManagement._web_search_is_disabled(features):
            return False
        recent_context = "\n".join(
            str(item.get("content") or "") for item in messages[-8:] if item.get("role") == "user"
        ).casefold()
        normalized_query = query.casefold()
        has_domain = any(trigger in recent_context for trigger in BIOINFORMATICS_DOMAIN_TRIGGERS)
        has_learning_intent = any(
            trigger in normalized_query for trigger in PROFESSIONAL_LEARNING_TRIGGERS
        )
        return has_domain and has_learning_intent

    @staticmethod
    def _clean_session_title(value: str) -> str:
        cleaned = re.sub(r"[\"'《》「」\n\r]", "", value or "").strip()
        # 去除模型偶尔带回的前缀（如“标题：”“Title:”），让标题更干净
        cleaned = re.sub(r"^(标题|主题|title)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
        # 剥掉第三人称叙述前缀（如“用户想要…”“最初询问了…”），标题应是主题而非摘要
        cleaned = re.sub(
            r"^(用户|该用户|这位用户)\s*(想要|想|希望|询问|咨询|请教|请求|问|需要|要求|讨论了|了解)\s*",
            "",
            cleaned,
        )
        cleaned = re.sub(r"^(最初|一开始|首先)\s*(询问|问|咨询|提到|讨论)了?\s*", "", cleaned)
        return cleaned[:40]

    @staticmethod
    def _is_topic_title(title: str) -> bool:
        """校验 LLM 产出是"主题短语"而非"对话摘要"；摘要式产出应弃用并走 fallback。

        模型不遵守提示时会把对话复述成一句话（如"用户输入了hi，助手回复了……并询问
        有什么可以帮忙的"），这类产出有稳定特征：含人称词、叙述动词+了、句末标点或超长。
        """
        t = (title or "").strip()
        if not t or len(t) > 15:
            return False
        if re.search(r"[。，；！？、…]$", t):
            return False
        if re.search(r"用户|助手", t):
            return False
        return not re.search(r"(输入|回复|回答|询问|提问|提供|表达|说明|介绍|讨论|描述)了", t)

    @staticmethod
    def _fallback_session_title(message: str = "") -> str:
        text = re.sub(r"\s+", " ", message or "").strip()
        if text:
            return text[:15] + ("…" if len(text) > 15 else "")
        return f"新会话 {datetime.now().strftime('%m-%d')}"

    @staticmethod
    def _is_default_session_title(title: str | None) -> bool:
        """判断标题是否仍是创建时的默认占位（尚无 LLM 生成的真实标题）。"""
        t = (title or "").strip()
        if not t or t in {"新对话", "生成中...", "新会话"}:
            return True
        return bool(re.fullmatch(r"与 .+ 的对话", t)) or bool(
            re.fullmatch(r"新会话 \d{2}-\d{2}", t)
        )

    @staticmethod
    def _build_search_snippet(content: str, keyword: str) -> str:
        text = re.sub(r"\s+", " ", content or "")
        index = text.casefold().find(keyword.casefold())
        if index < 0:
            return text[:120]
        start = max(0, index - 45)
        end = min(len(text), index + len(keyword) + 75)
        prefix = "…" if start else ""
        suffix = "…" if end < len(text) else ""
        return f"{prefix}{text[start:end]}{suffix}"

    @staticmethod
    def _build_title_context(messages: list[ChatMessageModel]) -> tuple[str, str]:
        """构造标题生成的素材：首条用户消息作为主题锚点，最近若干轮用于捕捉细节。

        返回 (first_user_content, 拼好的多轮对话文本)。仅看首轮会让标题丢失后续
        多轮里用户真正关心的基因/流程/文件等细节，故这里把“锚点 + 最近窗口”一起喂给模型。
        """
        first_user = next((m for m in messages if m.role == "user"), None)
        anchor = (first_user.content if first_user else "")[:600]

        lines: list[str] = []
        if anchor.strip():
            lines.append(f"用户：{anchor}")
        # 最近窗口覆盖对话演进后的细节诉求；user 截 600、assistant 截 400 控制 token
        for m in messages[-6:]:
            if m is first_user:
                continue  # 首条已作为锚点加入，避免重复
            role = "用户" if m.role == "user" else "助手"
            snippet = (m.content or "")[: (600 if m.role == "user" else 400)].strip()
            if snippet:
                lines.append(f"{role}：{snippet}")
        return anchor, "\n".join(lines)

    async def _generate_title_with_llm(
        self,
        session: ChatSessionModel,
        messages: list[ChatMessageModel],
    ) -> str:
        result = await self._db.execute(
            select(AIProviderConfigModel).where(AIProviderConfigModel.id == session.model_id)
        )
        config = result.scalar_one_or_none()
        if not config or not config.api_key:
            return ""
        anchor, context = self._build_title_context(messages)
        if not context.strip():
            return ""
        system_prompt = (
            "你是会话标题生成器。阅读下面用户与助手的对话，生成一个简短但**具体**的标题。"
            "要求：1) 标题必须包含对话里出现的**具体对象与意图**，如基因/蛋白/通路名、样本或文件名、"
            "分析流程或工具名、要做的动作（差异分析、富集、画火山图、解读结果、排查报错等）；"
            "2) 抓住对话**最主要的诉求**，若多轮且话题演进，以最近/最核心的诉求为准，不要只复述第一轮；"
            "3) 优先具体，禁止空泛主题词。"
            "反例（太泛，禁止）：转录组分析咨询、生物信息问题、数据分析帮助。"
            "正例（具体，推荐）：DESeq2 差异分析与火山图、TP53 通路富集结果解读、FASTQ 质控报错排查。"
            "4) 标题是**对话主题本身**，不是对话摘要：禁止出现「用户」「助手」等人称或叙述词，"
            "禁止「用户想要…」「最初询问…」「讨论了…」这类第三人称叙述句式，"
            "直接用名词短语或动宾短语点出主题。"
            "反例（叙述句，禁止）：用户想要处理VCF文件并询问安装、用户咨询差异分析流程。"
            "正例（主题式，推荐）：VCF 文件处理与工具安装、RNA-seq 差异分析流程咨询。"
            "5) 用 6 到 15 个汉字，不加结尾标点、不加引号、不要解释，只输出标题本身；"
            "标题必须是**完整短语**，宁可更短也不要写半句话。"
            "6) 若对话只是打招呼/闲聊、没有具体任务或对象（如“hi”“你好”“在吗”），"
            "输出 2 到 6 个字的场景主题即可，如：日常问候、闲聊。"
            "禁止把问候过程复述成摘要。"
        )
        payload = [{"role": "user", "content": f"对话内容：\n{context}"}]
        output = ""
        try:
            with anyio.fail_after(5):
                async for chunk in provider_manager.chat_stream(
                    config=config,
                    messages=payload,
                    system_prompt=system_prompt,
                    temperature=0,
                    max_tokens=60,
                    tools=None,
                    deep_thinking=False,
                ):
                    if chunk.type == "text":
                        output += chunk.content
                    if chunk.type in {"done", "error"}:
                        break
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"生成会话标题失败: {exc}")
        cleaned = self._clean_session_title(output)
        if cleaned and not self._is_topic_title(cleaned):
            # 模型没遵守提示、把对话复述成了摘要句：弃用，让调用方走 fallback
            logger.info(f"会话标题形似摘要，弃用 LLM 产出: {cleaned!r}")
            return ""
        return cleaned

    # --- 会话管理 ---

    async def create_session(
        self,
        user_id: str,
        model_id: uuid.UUID,
        title: str = "新对话",
        assistant_id: str | None = None,
        agent_id: str | None = None,
        *,
        mode: str = "chat",
        workspace_id: str | None = None,
        sandbox_meta: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> ChatSessionDTO:
        session = await self._sessions.create(
            user_id=user_id,
            model_id=model_id,
            title=title,
            assistant_id=assistant_id,
            agent_id=agent_id,
            mode=mode,
            workspace_id=workspace_id,
            sandbox_meta=sandbox_meta,
            project_id=project_id,
        )
        return self._to_session_dto(session)

    async def get_session(self, session_id: str, user_id: str) -> ChatSessionModel | None:
        return await self._sessions.get(session_id, user_id)

    async def list_sessions(
        self,
        user_id: str,
        mode: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatSessionDTO]:
        sessions = await self._sessions.list(user_id, mode, limit=limit, offset=offset)
        return [self._to_session_dto(session) for session in sessions]

    async def update_session_title(
        self, session_id: str, user_id: str, title: str, *, locked: bool = False
    ) -> ChatSessionDTO:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise NotFoundError("会话不存在或无权访问")
        session.title = self._clean_session_title(title) or self._fallback_session_title()
        if locked:
            session.title_locked = True
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return self._to_session_dto(session)

    async def search_sessions(self, user_id: str, keyword: str) -> ChatSessionSearchDTO:
        normalized = keyword.strip()
        if not normalized:
            return ChatSessionSearchDTO()
        pattern = f"%{self._escape_like(normalized)}%"

        title_result = await self._db.execute(
            select(ChatSessionModel)
            .where(
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.status == "active",
                ChatSessionModel.title.ilike(pattern, escape="\\"),
            )
            .order_by(desc(ChatSessionModel.updated_at))
            .limit(30)
        )
        title_matches = list(title_result.scalars().all())
        title_session_ids = {s.session_id for s in title_matches}

        content_result = await self._db.execute(
            select(ChatSessionModel, ChatMessageModel)
            .join(ChatMessageModel, ChatMessageModel.session_id == ChatSessionModel.session_id)
            .where(
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.status == "active",
                ChatMessageModel.content.ilike(pattern, escape="\\"),
                ChatSessionModel.session_id.not_in(title_session_ids or {"__none__"}),
            )
            .order_by(desc(ChatSessionModel.updated_at), ChatMessageModel.created_at)
            .limit(40)
        )

        seen_content_sessions: set[str] = set()
        content_matches: list[ChatSearchContentMatchDTO] = []
        for session, message in content_result.all():
            if session.session_id in seen_content_sessions:
                continue
            seen_content_sessions.add(session.session_id)
            content_matches.append(
                ChatSearchContentMatchDTO(
                    session_id=session.session_id,
                    title=session.title,
                    title_locked=session.title_locked,
                    agent_id=session.agent_id,
                    model_id=session.model_id,
                    mode=session.mode or "chat",
                    message_id=message.message_id,
                    snippet=self._build_search_snippet(message.content, normalized),
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                )
            )

        return ChatSessionSearchDTO(
            title_matches=[self._to_session_dto(s) for s in title_matches],
            content_matches=content_matches,
        )

    async def generate_session_title(self, session_id: str, user_id: str) -> str:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise NotFoundError("会话不存在或无权访问")
        if session.title_locked:
            return session.title

        result = await self._db.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        messages = self._order_messages(result.scalars().all())
        first_user = next((m for m in messages if m.role == "user"), None)
        fallback = self._fallback_session_title(first_user.content if first_user else "")
        if not first_user or not first_user.content.strip():
            session.title = fallback
            session.updated_at = datetime.now(UTC)
            await self._db.flush()
            return session.title

        title = await self._generate_title_with_llm(session, messages)
        cleaned = self._clean_session_title(title)
        if cleaned:
            session.title = cleaned
        elif self._is_default_session_title(session.title):
            # 仅在尚无真实标题（首轮/默认占位）时降级到 fallback；
            # 刷新轮 LLM 失败则保留已有标题，避免越改越差、丢失已抓住的细节。
            session.title = fallback
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return session.title

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise NotFoundError("会话不存在或无权访问")
        if session.mode == "studio":
            from omichub.infrastructure.studio.manager import studio_sandbox_manager

            try:
                await studio_sandbox_manager.stop(session.session_id)
            except Exception as exc:  # noqa: BLE001 - DB deletion must remain available
                logger.warning("删除 Studio 会话时释放沙盒失败，会由后台回收兜底: {}", exc)
        session.status = "deleted"
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        await self._enqueue_memory_summary(session)
        return True

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        content_type: str = "text",
        status: str = "complete",
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessageModel:
        return await self._sessions.add_message(
            session_id=session_id,
            role=role,
            content=content,
            content_type=content_type,
            status=status,
            metadata=metadata,
        )

    async def update_message_content(
        self,
        message_id: str,
        content: str,
        status: str = "complete",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._sessions.update_message_content(
            message_id=message_id,
            content=content,
            status=status,
            metadata=metadata,
        )

    async def get_messages(
        self, session_id: str, user_id: str | None = None
    ) -> list[ChatMessageDTO]:
        # 纵深防御：即便路由层已校验归属，service 层仍复核会话属于该用户，
        # 避免任何调用方绕过路由直接拿到他人会话消息。
        if user_id is not None:
            session = await self.get_session(session_id, user_id)
            if not session:
                raise NotFoundError("会话不存在或无权访问")
        messages = self._order_messages(await self._sessions.get_messages(session_id))
        return [self._to_msg_dto(m) for m in messages]
