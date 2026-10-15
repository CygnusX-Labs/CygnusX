"""平台身份边界内的科研寻宝鼠适配服务。"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.research_agent import DiscoveryProposal
from cygnusx.application.services.chat.session_service import SessionService
from cygnusx.application.services.chat_service import ChatService
from cygnusx.core.config import Settings, get_settings
from cygnusx.core.exceptions import AuthorizationError, DependencyUnavailableError, NotFoundError
from cygnusx.infrastructure.database.models.ai_provider import AIProviderConfigModel
from cygnusx.infrastructure.database.models.chat import ChatSessionModel
from cygnusx.infrastructure.database.models.project import ProjectModel

RESEARCH_AGENT_MARKER = "research-treasure-mouse"
ACCESSION_RE = re.compile(
    r"^(?:GSE|GSM|GPL|SRP|SRA|SRR|ERR|DRR|PRJ(?:NA|EB|DB|CA)|PMID)\d+[A-Z0-9.-]*$",
    re.I,
)


def _source_link(accession: str | None) -> str | None:
    """Only create links for known accession families; never trust an upstream URL."""
    if not accession or not ACCESSION_RE.fullmatch(accession.strip()):
        return None
    value = accession.strip().upper()
    if value.startswith(("GSE", "GSM", "GPL", "SRP", "SRA", "SRR", "ERR", "DRR", "PRJ")):
        return f"https://www.ncbi.nlm.nih.gov/bioproject/?term={value}"
    if value.startswith("PMID"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{value[4:]}"
    return None


def card_to_proposal(
    card: dict[str, Any], *, session_id: str, project_id: str | None
) -> DiscoveryProposal:
    """Map the legacy DatasetCard without upgrading it into a platform asset."""
    accession = str(card.get("accession") or "").strip() or None
    meta = card.get("meta") if isinstance(card.get("meta"), dict) else {}
    link = _source_link(accession)
    proposal_id = f"{session_id}:{accession or uuid.uuid4().hex}"
    return DiscoveryProposal(
        proposal_id=proposal_id,
        source=str(card.get("tool") or "unknown")[:64],
        accession=accession,
        title=str(card.get("title") or "")[:1000],
        summary=str(card.get("summary") or "")[:5000],
        organism=str(meta.get("organism"))[:256] if meta.get("organism") else None,
        assay_type=str(meta.get("assay"))[:256] if meta.get("assay") else None,
        sample_count=(
            int(meta["sample_count"])
            if str(meta.get("sample_count", "")).isdigit()
            else None
        ),
        metadata_status="unverified",
        source_links=[link] if link else [],
        evidence_refs=[accession] if accession else [],
        retrieved_at=datetime.now(UTC),
        project_id=project_id,
        conversation_id=session_id,
        provenance={
            "agent": RESEARCH_AGENT_MARKER,
            "tool_name": str(card.get("tool") or "")[:128] or None,
            "verification_level": "source_not_verified",
        },
    )


class TreasureAgentAdapter:
    """Server-to-server bridge to the existing Node/TS agent runtime."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def stream(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        lang: str,
        cancel_event: asyncio.Event,
        principal_id: str,
        project_id: str | None,
        session_id: str,
        platform_tools: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        url = self._settings.treasure_agent_url.rstrip("/") + "/cygnusx/discovery"
        if (
            not self._settings.treasure_agent_url
            or not self._settings.treasure_agent_internal_token
        ):
            raise DependencyUnavailableError("科研寻宝鼠受信 Agent 未配置")
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "X-CygnusX-Internal-Token": self._settings.treasure_agent_internal_token,
            "X-CygnusX-Principal": principal_id,
            "X-CygnusX-Project": project_id or "",
            "X-CygnusX-Session": session_id,
        }
        payload = {"messages": messages[-16:], "model": model, "stream": True, "lang": lang}
        if platform_tools:
            payload["platform_tools"] = platform_tools
        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(self._settings.treasure_agent_timeout_seconds)
                ) as client,
                client.stream("POST", url, headers=headers, json=payload) as response,
            ):
                    if response.status_code >= 400:
                        raise DependencyUnavailableError(
                            f"科研寻宝鼠 Agent 返回 HTTP {response.status_code}"
                        )
                    async for line in response.aiter_lines():
                        if cancel_event.is_set():
                            return
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(parsed, dict):
                            yield parsed
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError("科研寻宝鼠 Agent 连接失败") from exc


class ResearchTreasureService:
    def __init__(self, db: AsyncSession, *, adapter: TreasureAgentAdapter | None = None) -> None:
        self._db = db
        self._sessions = SessionService(db)
        self._adapter = adapter or TreasureAgentAdapter()
        self._active_cancels: dict[str, asyncio.Event] = {}

    @staticmethod
    def ensure_enabled() -> None:
        if not get_settings().treasure_native_ui_enabled:
            raise AuthorizationError("科研寻宝鼠原生入口尚未在当前环境启用", code="FEATURE_DISABLED")

    async def _owned_project(self, user_id: str, project_id: str | None) -> None:
        if not project_id:
            return
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError as exc:
            raise NotFoundError("项目不存在") from exc
        result = await self._db.execute(
            select(ProjectModel.id).where(
                ProjectModel.id == project_uuid,
                ProjectModel.user_id == uuid.UUID(user_id),
            )
        )
        if result.scalar_one_or_none() is None:
            raise AuthorizationError("无权访问该项目")

    async def _provider(self, model_id: uuid.UUID | None) -> AIProviderConfigModel:
        query = select(AIProviderConfigModel).where(AIProviderConfigModel.is_active.is_(True))
        if model_id:
            query = query.where(AIProviderConfigModel.id == model_id)
        else:
            query = query.order_by(
                desc(AIProviderConfigModel.is_default),
                desc(AIProviderConfigModel.updated_at),
            )
        result = await self._db.execute(query.limit(1))
        provider = result.scalar_one_or_none()
        if provider is None:
            raise DependencyUnavailableError("平台没有可用的 AI 模型配置")
        return provider

    async def create_session(
        self, user_id: str, project_id: str | None, title: str, model_id: uuid.UUID | None
    ) -> Any:
        await self._owned_project(user_id, project_id)
        provider = await self._provider(model_id)
        # Research discovery explicitly permits a global read-only session. Do not
        # inherit Chat's convenience default-project behavior for this surface.
        session = ChatSessionModel(
            id=uuid.uuid4(),
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            model_id=provider.id,
            title=title.strip() or "科研发现",
            status="active",
            mode="chat",
            sandbox_meta={
                "research_agent": RESEARCH_AGENT_MARKER,
                "legacy_history": "not_migrated",
            },
            project_id=project_id,
        )
        # Unlike normal Chat, a global discovery session must never create or
        # inherit a default project as a side effect.
        self._db.add(session)
        await self._db.flush()
        return ChatService._to_session_dto(session)

    async def list_sessions(self, user_id: str, project_id: str | None) -> list[Any]:
        await self._owned_project(user_id, project_id)
        query = select(ChatSessionModel).where(
            ChatSessionModel.user_id == user_id,
            ChatSessionModel.status == "active",
            ChatSessionModel.sandbox_meta["research_agent"].as_string() == RESEARCH_AGENT_MARKER,
        ).order_by(desc(ChatSessionModel.updated_at)).limit(200)
        if project_id:
            query = query.where(ChatSessionModel.project_id == project_id)
        else:
            query = query.where(ChatSessionModel.project_id.is_(None))
        result = await self._db.execute(query)
        return [ChatService._to_session_dto(session) for session in result.scalars().all()]

    async def _owned_session(self, user_id: str, session_id: str) -> ChatSessionModel:
        result = await self._db.execute(select(ChatSessionModel).where(
            ChatSessionModel.session_id == session_id,
            ChatSessionModel.user_id == user_id,
            ChatSessionModel.status == "active",
            ChatSessionModel.sandbox_meta["research_agent"].as_string() == RESEARCH_AGENT_MARKER,
        ))
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError("科研发现会话不存在或无权访问")
        await self._owned_project(user_id, session.project_id)
        return session

    async def messages(self, user_id: str, session_id: str) -> list[Any]:
        await self._owned_session(user_id, session_id)
        rows = await self._sessions.get_messages(session_id)
        return [ChatService._to_msg_dto(row) for row in rows]

    async def cancel(self, user_id: str, session_id: str) -> bool:
        await self._owned_session(user_id, session_id)
        event = self._active_cancels.get(session_id)
        if event is None:
            return False
        event.set()
        return True

    async def stream_message(
        self,
        user_id: str,
        session_id: str,
        content: str,
        model_id: uuid.UUID | None,
        lang: str,
    ) -> AsyncIterator[dict[str, Any]]:
        session = await self._owned_session(user_id, session_id)
        provider = await self._provider(model_id or session.model_id)
        user_message = await self._sessions.add_message(
            session_id=session_id,
            role="user",
            content=content,
            status="complete",
            metadata={"source": RESEARCH_AGENT_MARKER},
        )
        del user_message
        history = await self._sessions.get_messages(session_id)
        messages = [{"role": row.role, "content": row.content} for row in history if row.role in {"user", "assistant"}]
        cancel_event = asyncio.Event()
        self._active_cancels[session_id] = cancel_event
        assistant_text = ""
        cards: list[dict[str, Any]] = []
        tools: list[dict[str, Any]] = []
        grounding: dict[str, Any] | None = None
        terminal = "end"
        try:
            platform_tools = None
            if get_settings().tool_gateway_read_enabled:
                from cygnusx.application.services.agent_tool_delegation import issue_delegation
                from cygnusx.application.services.agent_tool_gateway import AgentToolGateway

                gateway = AgentToolGateway(self._db)
                context = await gateway.context(user_id, session_id,
                                                expected_agent="research_treasure_mouse")
                platform_tools = {"catalog": gateway.catalog(context),
                                  "delegation": await issue_delegation(context)}
            async for event in self._adapter.stream(
                messages=messages,
                model=provider.model,
                lang=lang,
                cancel_event=cancel_event,
                principal_id=user_id,
                project_id=session.project_id,
                session_id=session_id,
                platform_tools=platform_tools,
            ):
                if event.get("event"):
                    event_name = str(event["event"])
                elif "delta" in event:
                    event_name = "delta"
                else:
                    event_name = str(event.get("type") or "")
                if isinstance(event.get("delta"), str):
                    assistant_text += event["delta"]
                if event_name == "cards" and isinstance(event.get("cards"), list):
                    cards.extend(item for item in event["cards"] if isinstance(item, dict))
                if event_name == "tool":
                    tools.append(dict(event))
                if event_name == "grounding":
                    grounding = dict(event)
                if cancel_event.is_set():
                    terminal = "cancel"
                    yield {"event": "cancel"}
                    break
                yield event
                if event_name == "end":
                    terminal = "end"
                    break
                if event.get("error"):
                    terminal = "error"
                    break
        except asyncio.CancelledError:
            terminal = "cancel"
            raise
        except Exception as exc:
            terminal = "error"
            yield {"event": "error", "error": str(exc)}
        finally:
            self._active_cancels.pop(session_id, None)
            metadata: dict[str, Any] = {
                "source": RESEARCH_AGENT_MARKER,
                "events": {"cards": cards, "tools": tools, "grounding": grounding},
                "proposals": [
                    card_to_proposal(
                        card, session_id=session_id, project_id=session.project_id
                    ).model_dump(mode="json")
                    for card in cards
                ],
            }
            await self._sessions.add_message(
                session_id=session_id,
                role="assistant",
                content=assistant_text,
                status=terminal,
                metadata=metadata,
            )
