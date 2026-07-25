"""Cherry Studio 架构聊天业务服务

核心职责：
1. 会话 CRUD（创建、查询、更新、软删除）
2. 消息持久化（用户消息 + AI 消息）
3. SSE 流式聊天编排（调用 LLM + 实时更新数据库）
4. 内置助手管理（初始化预设助手）
"""

from __future__ import annotations

import ipaddress
import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import anyio
import httpx
from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.chat import (
    ChatAssistantDTO,
    ChatMessageDTO,
    ChatSearchContentMatchDTO,
    ChatSessionDTO,
    ChatSessionSearchDTO,
    UpdateAssistantRequest,
)
from omichub.application.services.mas_plan_adapter import (
    MAS_PLAN_PREVIEW_PROMPT_SUFFIX,
    MAS_PLAN_PREVIEW_TOOL_NAME,
    MAS_PLAN_PREVIEW_TOOL_SCHEMA,
    MASPlanPreviewAdapter,
)
from omichub.application.services.studio_approval_service import (
    APPROVAL_REQUIRED_TOOLS,
    APPROVAL_TTL_SECONDS,
    get_studio_approval_service,
)
from omichub.application.services.studio_capabilities import (
    CAPABILITY_LIST_TOOL,
    CAPABILITY_LOAD_TOOL,
    CAPABILITY_TOOL_NAMES,
    CAPABILITY_TOOL_SCHEMAS,
    CapabilityState,
    audit_event,
    load_capability,
)
from omichub.application.services.studio_capabilities import (
    catalog as capability_catalog,
)
from omichub.application.services.studio_capabilities import (
    loaded_servers as loaded_capability_servers,
)
from omichub.application.services.studio_capabilities import (
    mcp_tools as capability_mcp_tools,
)
from omichub.application.services.studio_capabilities import (
    normalize_state as normalize_capability_state,
)
from omichub.application.services.studio_capabilities import (
    render_prompt as render_capability_prompt,
)
from omichub.application.services.studio_tools import (
    STUDIO_SYSTEM_PROMPT_SUFFIX,
    STUDIO_TOOL_NAMES,
    STUDIO_TOOL_SCHEMAS,
    normalize_plan_steps,
    stream_studio_tool,
)
from omichub.core.config import get_settings
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.infrastructure.ai_provider.openai_compatible import (
    ChatChunk,
    merge_token_usage,
    provider_manager,
)
from omichub.infrastructure.config.prompt_loader import get_prompt
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel
from omichub.infrastructure.database.models.chat import (
    ChatAssistantModel,
    ChatMessageModel,
    ChatSessionModel,
)

if TYPE_CHECKING:
    from omichub.application.services.agent_service import AgentContext

DEFAULT_SYSTEM_PROMPT = get_prompt("agents.general")

# 智能路由器 system prompt：让 router LLM 从候选专家清单中选一个最合适的
ROUTER_SYSTEM_PROMPT = """你是一个意图路由器。根据用户消息，从下面的候选专家清单中选择一个最合适的专家来回答。

候选专家（JSON 数组）：
{catalog}

规则：
1. 直接输出一行 JSON：{{"agent_id": "...", "reason": "..."}}。
2. 禁止输出思考过程、复述用户消息或列候选清单，第一个字符必须是 {{。
3. agent_id 必须来自候选清单；reason 用一句中文简述分派理由。
4. 无法判断意图时，选择通用（general）专家对应的 agent_id。"""


def _extract_route_json(text: str) -> dict[str, Any] | None:
    """从 router LLM 输出中容错提取路由 JSON。

    模型可能在 JSON 前后输出思考过程，甚至多次输出 JSON（先错后对）。
    逐个尝试所有 {...} 片段，取最后一个可解析且含 agent_id 的对象。
    """
    found: dict[str, Any] | None = None
    for match in re.finditer(r"\{[^{}]*\}", text, re.DOTALL):
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("agent_id"):
            found = data
    return found


def _studio_risk_hint(tool_name: str, args: dict[str, Any]) -> str:
    """审批卡片上的单行风险提示（supervised 模式，§3.1）。"""
    if tool_name == "sandbox_execute":
        language = str(args.get("language") or "python")
        return f"将在沙盒中执行 {language} 代码"
    if tool_name == "workspace_write":
        return f"将写入工作区文件 {args.get('path') or ''}".strip()
    if tool_name == "workspace_edit":
        return f"将修改工作区文件 {args.get('path') or ''}".strip()
    if tool_name == "artifact_register":
        return f"将把产物 {args.get('path') or ''} 登记到结果报告中心".strip()
    return "该操作需要用户批准"

BUILTIN_ASSISTANTS: list[dict[str, Any]] = [
    {
        "assistant_id": "general", "name": "通用助手", "description": "OmicHub 通用 AI 助手，回答各类问题",
        "system_prompt": get_prompt("agents.general"), "default_temperature": 0.7, "default_max_tokens": 2048,
        "icon": "🤖", "color": "#4f8ef7", "category": "general",
    },
    {
        "assistant_id": "rna_seq_analyst", "name": "RNA-seq 分析师", "description": "专注于 RNA-seq 差异表达分析、通路富集、可视化",
        "system_prompt": get_prompt("agents.rnaseq"), "default_temperature": 0.3, "default_max_tokens": 4096,
        "icon": "🧬", "color": "#4f8ef7", "category": "analysis",
    },
    {
        "assistant_id": "scrna_analyst", "name": "单细胞分析师", "description": "专注于单细胞转录组分析、降维聚类、细胞注释",
        "system_prompt": get_prompt("agents.scrna"), "default_temperature": 0.3, "default_max_tokens": 4096,
        "icon": "🔬", "color": "#e74c3c", "category": "analysis",
    },
    {
        "assistant_id": "code_helper", "name": "代码助手", "description": "帮助编写和调试生信分析代码（Python / R）",
        "system_prompt": get_prompt("agents.code"), "default_temperature": 0.2, "default_max_tokens": 4096,
        "icon": "💻", "color": "#f39c12", "category": "code",
    },
    {
        "assistant_id": "visualization", "name": "可视化助手", "description": "帮助创建和优化科研图表",
        "system_prompt": get_prompt("agents.visualization"), "default_temperature": 0.3, "default_max_tokens": 4096,
        "icon": "📊", "color": "#27ae60", "category": "visualization",
    },
]


WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "联网搜索，获取与用户问题相关的实时信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "top_n": {"type": "integer", "default": 5, "description": "返回结果数量"},
            },
            "required": ["query"],
        },
    },
}


class ChatService:
    """聊天业务服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _clean_session_title(value: str) -> str:
        cleaned = re.sub(r"[\"'《》「」\n\r]", "", value or "").strip()
        return cleaned[:30]

    @staticmethod
    def _fallback_session_title(message: str = "") -> str:
        text = re.sub(r"\s+", " ", message or "").strip()
        if text:
            return text[:20] + ("…" if len(text) > 20 else "")
        return f"新会话 {datetime.now().strftime('%m-%d')}"

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

    async def _generate_title_with_llm(
        self,
        session: ChatSessionModel,
        first_user: ChatMessageModel,
        first_assistant: ChatMessageModel | None,
    ) -> str:
        result = await self._db.execute(
            select(AIProviderConfigModel).where(AIProviderConfigModel.id == session.model_id)
        )
        config = result.scalar_one_or_none()
        if not config or not config.api_key:
            return ""
        system_prompt = (
            "你是会话标题生成器。根据用户的首条消息和助手的回复，用 8 到 15 个汉字概括这段对话的主题。"
            "只输出标题本身，不要标点结尾，不要引号，不要解释。"
        )
        messages = [{"role": "user", "content": (
            f"用户首条消息：{first_user.content[:1000]}\n"
            f"助手回复摘要：{(first_assistant.content if first_assistant else '')[:500]}"
        )}]
        output = ""
        try:
            with anyio.fail_after(5):
                async for chunk in provider_manager.chat_stream(
                    config=config,
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=0,
                    max_tokens=40,
                    tools=None,
                    deep_thinking=False,
                ):
                    if chunk.type == "text":
                        output += chunk.content
                    if chunk.type in {"done", "error"}:
                        break
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"生成会话标题失败: {exc}")
        return output

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
    ) -> ChatSessionDTO:
        session = ChatSessionModel(
            id=uuid.uuid4(),
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            model_id=model_id,
            title=title,
            assistant_id=assistant_id,
            agent_id=agent_id,
            status="active",
            mode=mode,
            sandbox_meta=sandbox_meta,
        )
        # Studio 会话工作区与沙盒容器均按会话 ID 命名（manager.workspace_dir / container_name）
        if mode == "studio" and not workspace_id:
            workspace_id = session.session_id
        session.workspace_id = workspace_id
        self._db.add(session)
        await self._db.flush()
        return self._to_session_dto(session)

    async def get_session(self, session_id: str, user_id: str) -> ChatSessionModel | None:
        result = await self._db.execute(
            select(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        user_id: str,
        mode: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatSessionDTO]:
        query = select(ChatSessionModel).where(
            ChatSessionModel.user_id == user_id, ChatSessionModel.status == "active"
        )
        if mode is not None:
            query = query.where(ChatSessionModel.mode == mode)
        result = await self._db.execute(
            query.order_by(desc(ChatSessionModel.updated_at)).limit(limit).offset(offset)
        )
        return [self._to_session_dto(s) for s in result.scalars().all()]

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
        messages = list(result.scalars().all())
        first_user = next((m for m in messages if m.role == "user"), None)
        first_assistant = next((m for m in messages if m.role == "assistant"), None)
        fallback = self._fallback_session_title(first_user.content if first_user else "")
        if not first_user or not first_user.content.strip():
            session.title = fallback
            session.updated_at = datetime.now(UTC)
            await self._db.flush()
            return session.title

        title = await self._generate_title_with_llm(session, first_user, first_assistant)
        session.title = self._clean_session_title(title) or fallback
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return session.title

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise NotFoundError("会话不存在或无权访问")
        session.status = "deleted"
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return True

    # --- 消息管理 ---

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        content_type: str = "text",
        status: str = "complete",
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessageModel:
        message = ChatMessageModel(
            id=uuid.uuid4(),
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            content_type=content_type,
            status=status,
            metadata_json=metadata or {},
        )
        self._db.add(message)
        result = await self._db.execute(
            select(ChatSessionModel).where(ChatSessionModel.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.message_count += 1
            session.last_message_at = datetime.now(UTC)
            session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return message

    async def update_message_content(
        self,
        message_id: str,
        content: str,
        status: str = "complete",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        result = await self._db.execute(
            select(ChatMessageModel).where(ChatMessageModel.message_id == message_id)
        )
        msg = result.scalar_one_or_none()
        if msg:
            msg.content = content
            msg.status = status
            if metadata:
                # 必须构造新 dict：原地 update 后赋回同一对象，SQLAlchemy 判等不变，
                # JSONB 列不会进 UPDATE（路由徽标 routed_agent 等元数据会丢）
                msg.metadata_json = {**(msg.metadata_json or {}), **metadata}
            await self._db.flush()

    async def get_messages(
        self, session_id: str, user_id: str | None = None
    ) -> list[ChatMessageDTO]:
        # 纵深防御：即便路由层已校验归属，service 层仍复核会话属于该用户，
        # 避免任何调用方绕过路由直接拿到他人会话消息。
        if user_id is not None:
            session = await self.get_session(session_id, user_id)
            if not session:
                raise NotFoundError("会话不存在或无权访问")
        result = await self._db.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        return [self._to_msg_dto(m) for m in result.scalars().all()]

    # --- SSE 流式聊天 ---

    async def stream_chat(
        self,
        user_id: str,
        messages: list[dict[str, str]],
        model_id: uuid.UUID,
        session_id: str | None = None,
        assistant_id: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        cookie_error = await self._ensure_cookie_balance(user_id)
        if cookie_error:
            yield ChatChunk(type="error", content=cookie_error)
            return

        # 1. 获取并验证模型配置
        result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.id == model_id,
                AIProviderConfigModel.is_active == True,  # noqa: E712
            )
        )
        model_config = result.scalar_one_or_none()
        if not model_config:
            yield ChatChunk(type="error", content="指定的模型不存在或未启用")
            return
        if not model_config.api_key:
            yield ChatChunk(
                type="error",
                content=f"模型 '{model_config.name}' 的 API Key 未配置，请联系管理员设置",
            )
            return

        # 2. 获取或创建会话
        if session_id:
            session = await self.get_session(session_id, user_id)
            if not session:
                yield ChatChunk(type="error", content="会话不存在或已被删除")
                return
            current_session_id = session_id
        else:
            title = "新对话"
            if assistant_id:
                ast = await self.get_assistant(assistant_id)
                if ast:
                    title = f"与 {ast.name} 的对话"
            dto = await self.create_session(user_id, model_id, title, assistant_id)
            current_session_id = dto.session_id

        # 3. 确定系统提示词：参数 > 助手配置 > 默认
        final_system_prompt = system_prompt
        if not final_system_prompt and assistant_id:
            ast = await self.get_assistant(assistant_id)
            if ast:
                final_system_prompt = ast.system_prompt
        if not final_system_prompt:
            final_system_prompt = DEFAULT_SYSTEM_PROMPT

        # 4. 保存用户消息
        # 敏感信息脱敏：落库前清洗用户消息，DB 不留存原始品种名等敏感词；
        # 同时构建送 LLM 的脱敏副本（不可逆，不还原）
        from omichub.core.sanitizer import sanitize_messages, sanitize_text

        sensitive_keywords = get_settings().sensitive_keywords
        user_content_raw = messages[-1].get("content", "") if messages else ""
        user_content = sanitize_text(user_content_raw, sensitive_keywords)
        await self.add_message(current_session_id, "user", user_content)

        # 5. 创建 AI 消息记录
        ai_message = await self.add_message(
            current_session_id,
            "assistant",
            "",
            status="streaming",
            metadata={"model": model_config.name, "model_id": str(model_id)},
        )

        # 6. 调用 LLM 流式输出
        # 送外部 LLM 的 messages 用脱敏副本，避免敏感词外泄到第三方模型
        llm_messages = sanitize_messages(messages, sensitive_keywords)
        full_content = ""
        update_counter = 0
        last_usage: dict[str, Any] | None = None

        try:
            final_temp = temperature if temperature is not None else model_config.temperature
            final_max = max_tokens if max_tokens is not None else model_config.max_tokens

            async for chunk in provider_manager.chat_stream(
                config=model_config,
                messages=llm_messages,
                system_prompt=final_system_prompt,
                temperature=final_temp,
                max_tokens=final_max,
            ):
                if chunk.type == "text":
                    full_content += chunk.content
                    update_counter += 1
                    if update_counter % 5 == 0:
                        await self.update_message_content(
                            ai_message.message_id, full_content, "streaming"
                        )
                    if update_counter == 1:
                        chunk.metadata["session_id"] = current_session_id
                        chunk.metadata["message_id"] = ai_message.message_id

                elif chunk.type == "error":
                    await self.update_message_content(
                        ai_message.message_id,
                        full_content or f"生成失败: {chunk.content}",
                        "error",
                        {"error": chunk.content},
                    )
                    yield chunk
                    return

                elif chunk.type == "done":
                    last_usage = chunk.metadata.get("usage")
                    await self.update_message_content(
                        ai_message.message_id,
                        full_content,
                        "complete",
                        {"usage": last_usage} if last_usage else None,
                    )
                    await self._apply_usage_to_session(ai_message.message_id, last_usage)
                    chunk.metadata["session_id"] = current_session_id
                    chunk.metadata["message_id"] = ai_message.message_id
                    yield chunk
                    return

                yield chunk

        except Exception as e:  # noqa: BLE001
            await self.update_message_content(
                ai_message.message_id,
                full_content or f"生成失败: {e}",
                "error",
                {"error": str(e)},
            )
            yield ChatChunk(
                type="error",
                content=f"生成失败: {e}",
                metadata={"session_id": current_session_id, "message_id": ai_message.message_id},
            )

    # --- Agent 调度中枢：SSE 流式聊天（含 MCP 工具调用闭环） ---

    async def _route_to_agent(
        self, router_ctx: AgentContext, user_text: str
    ) -> tuple[AgentContext | None, dict[str, Any] | None]:
        """智能路由：用路由器 Agent 的模型做意图分派，返回目标 Agent 上下文与路由信息。

        任何失败（模型报错、解析失败、目标不存在）都静默回落 general 候选，绝不抛出。
        """
        from omichub.application.services.agent_service import AgentService

        try:
            agent_service = AgentService(self._db)
            agents = await agent_service.list_agents(active_only=True)
            candidates = [
                a for a in agents if not (a.features or {}).get("router")
            ]
            if not candidates or router_ctx.model_config is None:
                return None, None

            def _general_fallback() -> Any:
                for c in candidates:
                    if c.category == "general" or "general" in c.agent_id:
                        return c
                return candidates[0]

            catalog = json.dumps(
                [
                    {
                        "agent_id": c.agent_id,
                        "name": c.name,
                        "description": c.description,
                        "category": c.category,
                    }
                    for c in candidates
                ],
                ensure_ascii=False,
            )
            system_prompt = ROUTER_SYSTEM_PROMPT.replace("{catalog}", catalog)

            # 路由过程 chunk 全部消费，仅累加 text，不向外 yield
            route_text = ""
            async for chunk in provider_manager.chat_stream(
                config=router_ctx.model_config,
                messages=[{"role": "user", "content": user_text}],
                system_prompt=system_prompt,
                temperature=0,
                max_tokens=200,
                tools=None,
                deep_thinking=False,
            ):
                if chunk.type == "text":
                    route_text += chunk.content

            valid_ids = {c.agent_id for c in candidates}
            target_id = ""
            reason = ""
            decision = _extract_route_json(route_text)
            if decision:
                target_id = str(decision.get("agent_id") or "")
                reason = str(decision.get("reason") or "")
            if target_id not in valid_ids:
                fallback = _general_fallback()
                target_id = fallback.agent_id
                if not reason:
                    reason = "未识别出明确领域，转接通用助手"

            target_ctx = await agent_service.assemble_context(target_id)
            if target_ctx is None or target_ctx.model_config is None:
                fallback = _general_fallback()
                target_id = fallback.agent_id
                target_ctx = await agent_service.assemble_context(target_id)
                if target_ctx is None:
                    return None, None

            target_dto = next(
                (c for c in candidates if c.agent_id == target_id),
                _general_fallback(),
            )
            route_info = {
                "agent_id": target_dto.agent_id,
                "name": target_dto.name,
                "avatar": target_dto.avatar,
                "color": target_dto.color,
                "reason": reason,
            }
            return target_ctx, route_info
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Agent路由] 意图分派失败，按原 Agent 继续: {e}")
            return None, None

    async def stream_agent_chat(
        self,
        user_id: str,
        agent_id: str,
        messages: list[dict[str, str]],
        session_id: str | None = None,
        model_id: uuid.UUID | None = None,
        attachments: list[dict[str, Any]] | None = None,
        enable_web_search: bool = False,
        enable_code_execution: bool = False,
        deep_thinking: bool = False,
        mode: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Agent 编排闭环：查 Agent → 组装模型/系统词/工具 → 打 LLM → 执行 tool_call 回灌 → 流式返回

        Studio 模式（mode="studio" 或会话行 mode="studio"）：追加 5 个工作台内置工具与
        Studio 系统提示词后缀，工具调用路由到沙盒执行（sandbox_execute 流式回传 stdout/stderr）。
        """
        from omichub.application.schemas.tool_invocation import ToolInvocationContext
        from omichub.application.services.agent_service import AgentService
        from omichub.core.sanitizer import sanitize_messages, sanitize_text
        from omichub.infrastructure.mcp.client import MCPClient

        cookie_error = await self._ensure_cookie_balance(user_id)
        if cookie_error:
            yield ChatChunk(type="error", content=cookie_error)
            return

        ctx = await AgentService(self._db).assemble_context(agent_id)
        if ctx is None:
            yield ChatChunk(type="error", content="Agent 不存在或已停用")
            return

        # 若请求指定了 model_id，校验并覆盖 Agent 默认模型
        if model_id is not None:
            override = await self._resolve_model(model_id)
            if override is None:
                yield ChatChunk(
                    type="error",
                    content="指定的模型不存在或未启用",
                )
                return
            if not override.api_key:
                yield ChatChunk(
                    type="error",
                    content=f"模型 '{override.name}' 的 API Key 未配置，请联系管理员设置",
                )
                return
            ctx.model_config = override

        if ctx.model_config is None:
            yield ChatChunk(
                type="error",
                content=f"Agent '{ctx.agent.name}' 未绑定可用模型，请联系管理员在 AI 资源中心配置",
            )
            return
        if not ctx.model_config.api_key:
            yield ChatChunk(
                type="error",
                content=f"模型 '{ctx.model_config.name}' 的 API Key 未配置，请联系管理员设置",
            )
            return

        model_config = ctx.model_config
        sensitive_keywords = get_settings().sensitive_keywords

        # 1. 取/建会话
        # Studio 模式判定：已有会话以会话行 mode 为准；新建会话取请求显式 mode。
        # 沙盒镜像优先取会话 sandbox_meta.image（创建时由 Agent studio 配置解析），
        # 其次取 Agent features.studio.image，均未配置时由 manager 回落默认镜像。
        # context_pack（报告一键优化场景，§7.2）只在已有会话上存在，随系统提示词注入。
        studio_mode = False
        studio_image: str | None = None
        studio_context_pack: dict[str, Any] | None = None
        # 会话级权限模式（§2）：supervised（默认，写/执行类工具需用户批准）| auto
        studio_permission_mode = "supervised"
        studio_capability_state = CapabilityState()
        bound_skills = list(getattr(ctx, "skills", []) or [])
        bound_mcp_servers = list(ctx.mcp_servers or [])
        if session_id:
            session = await self.get_session(session_id, user_id)
            if not session:
                yield ChatChunk(type="error", content="会话不存在或已被删除")
                return
            if session.agent_id and session.agent_id != agent_id:
                yield ChatChunk(type="error", content="会话绑定的 Agent 与当前请求不一致")
                return
            # 若用户切换了模型，同步更新会话记录的 model_id
            if model_id is not None and session.model_id != model_id:
                session.model_id = model_id
                session.updated_at = datetime.now(UTC)
            studio_mode = session.mode == "studio"
            if studio_mode:
                sandbox_meta = session.sandbox_meta or {}
                studio_image = sandbox_meta.get("image")
                studio_context_pack = sandbox_meta.get("context_pack")
                studio_permission_mode = (sandbox_meta.get("permissions") or {}).get(
                    "mode", "supervised"
                )
                studio_capability_state = normalize_capability_state(
                    sandbox_meta.get("capabilities"), bound_skills, bound_mcp_servers
                )
            current_session_id = session_id
        else:
            studio_mode = mode == "studio"
            if studio_mode:
                studio_image = (ctx.features.get("studio") or {}).get("image")
            title = f"与 {ctx.agent.name} 的对话"
            dto = await self.create_session(
                user_id,
                model_config.id,
                title,
                agent_id=agent_id,
                mode="studio" if studio_mode else "chat",
                sandbox_meta={"image": studio_image} if studio_image else None,
            )
            current_session_id = dto.session_id

        # 2. 落库用户消息（脱敏）
        user_content_raw = messages[-1].get("content", "") if messages else ""
        user_content = sanitize_text(user_content_raw, sensitive_keywords)
        attachment_dicts = [
            att.model_dump() if hasattr(att, "model_dump") else dict(att)
            for att in (attachments or [])
        ]
        await self.add_message(
            current_session_id,
            "user",
            user_content,
            metadata={"attachments": attachment_dicts},
        )

        # 3. AI 占位消息
        ai_message = await self.add_message(
            current_session_id,
            "assistant",
            "",
            status="streaming",
            metadata={"model": model_config.name, "agent_id": agent_id},
        )

        # 3.5 智能路由：路由器 Agent 先做意图分派，再以目标 Agent 的上下文继续后续流程。
        # 会话绑定校验与落库的 agent_id 始终保持路由器不变；同一会话的每条消息都重新路由。
        if ctx.features.get("router"):
            target_ctx, route_info = await self._route_to_agent(ctx, user_content)
            if target_ctx is not None and route_info is not None:
                ctx = target_ctx
                if ctx.model_config is not None:
                    model_config = ctx.model_config
                bound_skills = list(getattr(ctx, "skills", []) or [])
                bound_mcp_servers = list(ctx.mcp_servers or [])
                await self.update_message_content(
                    ai_message.message_id,
                    "",
                    "streaming",
                    {"model": model_config.name, "routed_agent": route_info},
                )
                yield ChatChunk(
                    type="route",
                    metadata={
                        **route_info,
                        "session_id": current_session_id,
                        "message_id": ai_message.message_id,
                    },
                )

        # 4. 送 LLM 的 messages（脱敏 + 附件多模态注入）
        llm_messages: list[dict[str, Any]] = sanitize_messages(messages, sensitive_keywords)
        if attachments:
            llm_messages = await self._build_multimodal_messages(llm_messages, attachments)

        # 动态追加联网搜索工具。普通聊天保持 Agent 全量 MCP/Skill 行为；
        # Studio 使用元数据目录 + 会话级按需加载，未加载能力不进入 prompt/tools。
        effective_web_search = enable_web_search or bool(ctx.features.get("enable_web_search"))
        base_tools: list[dict[str, Any]] = []
        if effective_web_search:
            base_tools.append(WEB_SEARCH_TOOL)

        active_mcp_servers = list(bound_mcp_servers)
        tools = list(ctx.tools or []) + base_tools
        system_prompt = ctx.system_prompt or None
        mas_plan_tool_enabled = get_settings().mas_enabled and (
            studio_mode or bool(ctx.features.get("mas_orchestrator"))
        )

        def _attach_mas_plan_tool(
            runtime_tools: list[dict[str, Any]], runtime_prompt: str | None
        ) -> tuple[list[dict[str, Any]], str]:
            if not mas_plan_tool_enabled:
                return runtime_tools, runtime_prompt or ""
            if not any(
                item.get("function", {}).get("name") == MAS_PLAN_PREVIEW_TOOL_NAME
                for item in runtime_tools
            ):
                runtime_tools.append(MAS_PLAN_PREVIEW_TOOL_SCHEMA)
            prompt = runtime_prompt or ""
            return runtime_tools, f"{prompt}\n\n{MAS_PLAN_PREVIEW_PROMPT_SUFFIX}".strip()

        def _studio_runtime(state: CapabilityState) -> tuple[list[dict[str, Any]], str, list[Any]]:
            runtime_tools = list(base_tools)
            runtime_tools.extend(STUDIO_TOOL_SCHEMAS)
            runtime_tools.extend(CAPABILITY_TOOL_SCHEMAS)
            reserved_names = {
                item.get("function", {}).get("name", "") for item in runtime_tools
            }
            safe_servers = []
            for server in loaded_capability_servers(bound_mcp_servers, state):
                server_names = {tool.tool_name for tool in server.tools}
                if server_names & reserved_names:
                    continue
                safe_servers.append(server)
                reserved_names.update(server_names)
            runtime_tools.extend(capability_mcp_tools(safe_servers))

            base_prompt = getattr(ctx.agent, "system_prompt", "") or ""
            if not base_prompt and not bound_skills:
                base_prompt = ctx.system_prompt or ""
            runtime_prompt = render_capability_prompt(
                base_prompt, bound_skills, bound_mcp_servers, state
            )
            runtime_prompt = (
                f"{runtime_prompt}\n\n{STUDIO_SYSTEM_PROMPT_SUFFIX}"
                if runtime_prompt
                else STUDIO_SYSTEM_PROMPT_SUFFIX
            )
            if studio_context_pack:
                from omichub.application.services.studio_context_service import (
                    render_context_pack_hint,
                )

                runtime_prompt += f"\n\n{render_context_pack_hint(studio_context_pack)}"
            return runtime_tools, runtime_prompt, safe_servers

        if studio_mode:
            tools, system_prompt, active_mcp_servers = _studio_runtime(
                studio_capability_state
            )
        tools, system_prompt = _attach_mas_plan_tool(tools, system_prompt)

        full_content = ""
        update_counter = 0
        first_chunk_sent = False
        max_rounds = 8
        last_usage: dict[str, Any] | None = None
        last_finish_reason: str | None = None
        # Studio 工具调用落库累积（代码卡片 / 产物 / diff，供历史重载渲染）
        studio_invocations: list[dict[str, Any]] = []

        mcp_client = MCPClient()

        tool_context = ToolInvocationContext(
            user_id=user_id,
            agent_id=agent_id,
            session_id=current_session_id,
            db=self._db,
        )

        async def _persist_capability_state(
            state: CapabilityState, event: dict[str, Any]
        ) -> CapabilityState:
            audited = CapabilityState(
                state.loaded_skill_ids,
                state.loaded_mcp_ids,
                tuple((*state.audit, event)[-100:]),
            )
            capability_session = await self.get_session(current_session_id, user_id)
            if capability_session is not None:
                meta = dict(capability_session.sandbox_meta or {})
                meta["capabilities"] = audited.as_dict()
                capability_session.sandbox_meta = meta
                capability_session.updated_at = datetime.now(UTC)
                await self._db.flush()
            return audited

        # LangGraph 引擎分流：features.engine == "langgraph" 且非 Studio 模式时
        # 走状态图运行时；其余（含 Studio 沙盒、未标记 engine）保持手写循环不变。
        if ctx.features.get("engine") == "langgraph" and not studio_mode:
            async for chunk in self._stream_agent_chat_langgraph(
                user_id=user_id,
                session_id=current_session_id,
                ai_message_id=ai_message.message_id,
                model_config=model_config,
                llm_messages=llm_messages,
                system_prompt=system_prompt,
                tools=tools,
                temperature=ctx.temperature,
                max_tokens=ctx.max_tokens,
                deep_thinking=deep_thinking,
                active_mcp_servers=active_mcp_servers,
                mcp_client=mcp_client,
                tool_context=tool_context,
            ):
                yield chunk
            return

        try:
            logger.info(
                f"[Agent聊天] 开始调用模型 provider={model_config.name} model={model_config.model} "
                f"messages={len(llm_messages)} tools={len(tools)} attachments={len(attachments or [])}"
            )
            for _round in range(max_rounds):
                round_text = ""
                round_tool_calls: list[dict[str, Any]] = []

                async for chunk in provider_manager.chat_stream(
                    config=model_config,
                    messages=llm_messages,
                    system_prompt=system_prompt,
                    temperature=ctx.temperature,
                    max_tokens=ctx.max_tokens,
                    tools=tools or None,
                    deep_thinking=deep_thinking,
                ):
                    if chunk.type == "text":
                        if chunk.metadata.get("is_reasoning"):
                            # 推理过程不并入最终正文，但仍透传给前端
                            yield chunk
                            continue
                        round_text += chunk.content
                        full_content += chunk.content
                        update_counter += 1
                        if update_counter % 5 == 0:
                            await self.update_message_content(
                                ai_message.message_id, full_content, "streaming"
                            )
                        if not first_chunk_sent:
                            chunk.metadata["session_id"] = current_session_id
                            chunk.metadata["message_id"] = ai_message.message_id
                            first_chunk_sent = True
                        yield chunk

                    elif chunk.type == "tool_calls":
                        round_tool_calls = chunk.metadata.get("tool_calls", [])

                    elif chunk.type == "error":
                        await self.update_message_content(
                            ai_message.message_id,
                            full_content or f"生成失败: {chunk.content}",
                            "error",
                            {"error": chunk.content},
                        )
                        yield chunk
                        return

                    elif chunk.type == "done":
                        # Studio 工具循环会产生多次模型请求，逐轮累计实际计费用量。
                        last_usage = merge_token_usage(
                            last_usage, chunk.metadata.get("usage")
                        )
                        last_finish_reason = chunk.metadata.get("finish_reason") or last_finish_reason

                # 本轮无工具调用 → 正常结束
                if not round_tool_calls:
                    await self.update_message_content(
                        ai_message.message_id,
                        full_content,
                        "complete",
                        {"usage": last_usage} if last_usage else None,
                    )
                    await self._apply_usage_to_session(ai_message.message_id, last_usage)
                    done_meta: dict[str, Any] = {
                            "session_id": current_session_id,
                            "message_id": ai_message.message_id,
                            "usage": last_usage,
                        }
                    if last_finish_reason:
                        done_meta["finish_reason"] = last_finish_reason
                    yield ChatChunk(type="done", metadata=done_meta)
                    return

                # 有工具调用 → 执行并回灌，进入下一轮
                # 先把 assistant 的 tool_calls 消息加入上下文
                llm_messages.append(
                    {
                        "role": "assistant",
                        "content": round_text or "",
                        "tool_calls": round_tool_calls,
                    }
                )
                if round_text:
                    full_content += "\n\n" if full_content else ""
                    # 工具调用阶段的正文并入落库内容
                    await self.update_message_content(
                        ai_message.message_id, full_content, "streaming"
                    )

                # ask_user 拦截时置 True：回灌工具结果后收尾跳出大循环，等待用户下条消息
                stop_after_tools = False
                for tc in round_tool_calls:
                    fn = tc.get("function", {}) or {}
                    tool_name = fn.get("name", "")
                    raw_args = fn.get("arguments", "")
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    # Studio 内置工具优先路由到沙盒，其余仍按 MCP server 匹配
                    is_capability_tool = studio_mode and tool_name in CAPABILITY_TOOL_NAMES
                    is_studio_tool = studio_mode and (
                        tool_name in STUDIO_TOOL_NAMES or is_capability_tool
                    )
                    is_mas_plan_tool = (
                        mas_plan_tool_enabled and tool_name == MAS_PLAN_PREVIEW_TOOL_NAME
                    )

                    # 在绑定的 MCP server 中找到拥有该工具的 server
                    server = None
                    if not is_studio_tool and not is_mas_plan_tool:
                        server = next(
                            (
                                s
                                for s in active_mcp_servers
                                if any(t.tool_name == tool_name for t in s.tools)
                            ),
                            None,
                        )
                    tool_channel = (
                        "studio-capabilities"
                        if is_capability_tool
                        else "mas-plan"
                        if is_mas_plan_tool
                        else "studio"
                        if is_studio_tool
                        else (server.name if server else None)
                    )

                    yield ChatChunk(
                        type="tool_call",
                        metadata={
                            "tool_call_id": tc.get("id", ""),
                            "tool_name": tool_name,
                            "arguments": args,
                            "mcp_server": tool_channel,
                        },
                    )

                    if is_mas_plan_tool:
                        result = MASPlanPreviewAdapter().adapt(args)
                    elif is_capability_tool and tool_name == CAPABILITY_LIST_TOOL:
                        event = audit_event("list", None, None, True)
                        studio_capability_state = await _persist_capability_state(
                            studio_capability_state, event
                        )
                        visible_catalog = capability_catalog(
                            bound_skills, bound_mcp_servers, studio_capability_state
                        )
                        result = {
                            "success": True,
                            "result": {
                                "llm_payload": visible_catalog,
                                "ui_payload": {
                                    "capabilities": visible_catalog,
                                    "audit_event": event,
                                },
                            },
                        }
                    elif is_capability_tool and tool_name == CAPABILITY_LOAD_TOOL:
                        kind = str(args.get("kind", "")).strip().lower()
                        capability_id = str(args.get("id", "")).strip()
                        if kind not in {"skill", "mcp"} or not capability_id:
                            next_state = None
                            load_result = {
                                "success": False,
                                "error": "kind 必须为 skill/mcp，且 id 不能为空",
                            }
                        else:
                            reserved_names = {
                                item.get("function", {}).get("name", "") for item in tools
                            }
                            next_state, load_result = load_capability(
                                kind,
                                capability_id,
                                bound_skills,
                                bound_mcp_servers,
                                studio_capability_state,
                                reserved_names,
                            )
                        success = bool(load_result.get("success"))
                        event = audit_event("load", kind or None, capability_id or None, success)
                        if next_state is not None:
                            studio_capability_state = next_state
                        studio_capability_state = await _persist_capability_state(
                            studio_capability_state, event
                        )
                        if success:
                            tools, system_prompt, active_mcp_servers = _studio_runtime(
                                studio_capability_state
                            )
                            tools, system_prompt = _attach_mas_plan_tool(tools, system_prompt)
                        result = {
                            "success": success,
                            "result": {
                                "llm_payload": load_result,
                                "ui_payload": {
                                    "capability": load_result,
                                    "audit_event": event,
                                },
                            },
                        }
                    elif is_studio_tool and tool_name == "update_plan":
                        # 待办计划（§5.3 agent.plan）：不打沙盒，直接产出 plan 事件
                        # 驱动右栏待办面板，并把最新计划落库到会话 sandbox_meta.plan；
                        # 结果信封照常走 tool_result/落库流程（tool_invocations 记录）。
                        steps, plan_error = normalize_plan_steps(args)
                        if steps is None:
                            result = {
                                "success": False,
                                "result": {
                                    "llm_payload": {"error": plan_error},
                                    "ui_payload": {"error": plan_error},
                                },
                            }
                        else:
                            plan_session = await self.get_session(current_session_id, user_id)
                            if plan_session is not None:
                                meta = dict(plan_session.sandbox_meta or {})
                                meta["plan"] = {"steps": steps}
                                # 整体重赋值触发 JSONB 变更检测
                                plan_session.sandbox_meta = meta
                                plan_session.updated_at = datetime.now(UTC)
                                await self._db.flush()
                            yield ChatChunk(
                                type="plan",
                                metadata={"tool_call_id": tc.get("id", ""), "steps": steps},
                            )
                            result = {
                                "success": True,
                                "result": {
                                    "llm_payload": {
                                        "steps": steps,
                                        "message": "计划已更新，右栏待办面板已同步",
                                    },
                                    "ui_payload": {"steps": steps},
                                },
                            }
                    elif is_studio_tool and tool_name == "ask_user":
                        # 澄清交互（§3.4）：不进沙盒，产出 ask_request 事件并以"本轮结束"收尾，
                        # 用户在下一条聊天消息中回答，对话自然继续。
                        question = str(args.get("question") or "").strip()
                        options_raw = args.get("options")
                        options = (
                            [str(o) for o in options_raw if str(o).strip()]
                            if isinstance(options_raw, list)
                            else []
                        )
                        yield ChatChunk(
                            type="ask_request",
                            metadata={
                                "tool_call_id": tc.get("id", ""),
                                "question": question,
                                "options": options,
                            },
                        )
                        ask_payload: dict[str, Any] = {
                            "question": question,
                            "options": options,
                            "message": "问题已展示给用户，用户将在下一条消息中回答。本轮回复到此结束，请等待用户答复。",
                        }
                        result = {
                            "success": True,
                            "result": {"llm_payload": ask_payload, "ui_payload": dict(ask_payload)},
                        }
                        stop_after_tools = True
                    elif is_studio_tool:
                        # 审批闸（§3）：supervised 模式下写/执行类工具先经用户批准
                        approval_passed = True
                        if (
                            studio_permission_mode == "supervised"
                            and tool_name in APPROVAL_REQUIRED_TOOLS
                        ):
                            approval_service = get_studio_approval_service()
                            approval = await approval_service.create(
                                user_id=user_id,
                                session_id=current_session_id,
                                tool_call_id=tc.get("id", ""),
                                tool_name=tool_name,
                                arguments=args,
                                risk_hint=_studio_risk_hint(tool_name, args),
                            )
                            yield ChatChunk(
                                type="approval_request",
                                metadata={
                                    "approval_id": approval["approval_id"],
                                    "tool_call_id": tc.get("id", ""),
                                    "tool_name": tool_name,
                                    "arguments": args,
                                    "risk_hint": approval["risk_hint"],
                                    "timeout_seconds": APPROVAL_TTL_SECONDS,
                                },
                            )
                            resolution = await approval_service.wait_resolution(
                                approval["approval_id"]
                            )
                            action = str(resolution.get("action") or "timeout")
                            yield ChatChunk(
                                type="approval_resolved",
                                metadata={
                                    "approval_id": approval["approval_id"],
                                    "tool_call_id": tc.get("id", ""),
                                    "action": action,
                                },
                            )
                            if action == "edited" and isinstance(
                                resolution.get("modified_args"), dict
                            ):
                                args = resolution["modified_args"]
                                action = "approved"
                            if action != "approved":
                                approval_passed = False
                                reason = resolution.get("reason") or (
                                    "用户未响应（超时）"
                                    if action == "timeout"
                                    else "用户拒绝了该操作"
                                )
                                reject_payload = {"rejected": True, "error": reason}
                                result = {
                                    "success": False,
                                    "rejected": True,
                                    "result": {
                                        "llm_payload": reject_payload,
                                        "ui_payload": dict(reject_payload),
                                    },
                                }
                        # 沙盒执行：sandbox_execute 的 stdout/stderr 以 tool_output 事件边跑边推
                        if approval_passed:
                            result = {}
                            async for item in stream_studio_tool(
                                tool_name,
                                args,
                                current_session_id,
                                image=studio_image,
                                tool_call_id=tc.get("id", ""),
                                user_id=user_id,
                                db=self._db,
                            ):
                                if isinstance(item, ChatChunk):
                                    yield item
                                else:
                                    result = item
                    elif server is None:
                        if tool_name == "web_search":
                            result = await self._web_search(args)
                        else:
                            result = {
                                "success": False,
                                "error": f"工具 {tool_name} 未挂载到该 Agent",
                            }
                    else:
                        result = await mcp_client.call_tool(
                            server,
                            tool_name,
                            args,
                            user_id=user_id,
                            context=tool_context,
                        )

                    # 双通道：llm_payload 给 LLM，ui_payload 给前端
                    tool_output = result.get("result") if isinstance(result, dict) else result
                    if isinstance(tool_output, dict) and ("llm_payload" in tool_output or "ui_payload" in tool_output):
                        ui_payload = tool_output.get("ui_payload")
                        llm_result = tool_output.get("llm_payload", tool_output)
                    else:
                        ui_payload = None
                        llm_result = tool_output if tool_output is not None else result
                    if not isinstance(llm_result, dict):
                        llm_result = {"result": llm_result}

                    yield ChatChunk(
                        type="tool_result",
                        metadata={
                            "tool_call_id": tc.get("id", ""),
                            "tool_name": tool_name,
                            "mcp_server": tool_channel,
                            "success": bool(result.get("success")),
                            "result": llm_result,
                            "ui_payload": ui_payload,
                        },
                    )
                    # Studio 工具调用随消息落库：历史重载时凭 ui_payload 渲染代码卡片/产物/diff
                    if is_studio_tool or is_mas_plan_tool:
                        studio_invocations.append(
                            {
                                "tool_call_id": tc.get("id", ""),
                                "tool_name": tool_name,
                                "arguments": args,
                                "success": bool(result.get("success")),
                                "result": llm_result,
                                "ui_payload": ui_payload,
                            }
                        )
                        await self.update_message_content(
                            ai_message.message_id,
                            full_content,
                            "streaming",
                            {"tool_invocations": studio_invocations},
                        )
                    llm_content = json.dumps(llm_result, ensure_ascii=False, default=str)
                    if len(llm_content) > 4000:
                        llm_content = llm_content[:4000]
                    llm_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": llm_content,
                        }
                    )

                # ask_user：问题已展示，收尾跳出工具大循环，等用户下一条消息
                if stop_after_tools:
                    await self.update_message_content(
                        ai_message.message_id,
                        full_content,
                        "complete",
                        {"usage": last_usage} if last_usage else None,
                    )
                    await self._apply_usage_to_session(ai_message.message_id, last_usage)
                    yield ChatChunk(
                        type="done",
                        metadata={
                            "session_id": current_session_id,
                            "message_id": ai_message.message_id,
                            "usage": last_usage,
                        },
                    )
                    return

            # 超过最大轮次仍未结束
            await self.update_message_content(
                ai_message.message_id,
                full_content,
                "complete",
                {"warning": "工具调用轮次达上限，已提前结束"},
            )
            yield ChatChunk(
                type="done",
                metadata={
                    "session_id": current_session_id,
                    "message_id": ai_message.message_id,
                },
            )

        except Exception as e:  # noqa: BLE001
            await self.update_message_content(
                ai_message.message_id,
                full_content or f"生成失败: {e}",
                "error",
                {"error": str(e)},
            )
            yield ChatChunk(
                type="error",
                content=f"生成失败: {e}",
                metadata={"session_id": current_session_id, "message_id": ai_message.message_id},
            )

    async def _stream_agent_chat_langgraph(
        self,
        *,
        user_id: str,
        session_id: str,
        ai_message_id: str,
        model_config: Any,
        llm_messages: list[dict[str, Any]],
        system_prompt: str | None,
        tools: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        deep_thinking: bool,
        active_mcp_servers: list[Any],
        mcp_client: Any,
        tool_context: Any,
    ) -> AsyncIterator[ChatChunk]:
        """LangGraph 引擎路径：状态图驱动 ReAct 循环，事件协议与手写循环一致

        tool_executor 复刻 legacy 非 Studio 工具路由：MCP server 匹配 →
        MCPClient.call_tool；web_search → self._web_search；未挂载 → 报错信封。
        """
        from omichub.infrastructure.execution.langgraph_nodes import NodeDeps
        from omichub.infrastructure.execution.langgraph_runtime import (
            LangGraphRuntimeService,
        )

        def _find_server(tool_name: str) -> Any:
            return next(
                (
                    s
                    for s in active_mcp_servers
                    if any(t.tool_name == tool_name for t in s.tools)
                ),
                None,
            )

        def _resolve_channel(tool_name: str) -> str | None:
            server = _find_server(tool_name)
            return server.name if server else None

        async def _tool_executor(
            tool_name: str, args: dict[str, Any], tool_call_id: str
        ) -> dict[str, Any]:
            if tool_name == "web_search":
                return await self._web_search(args)
            server = _find_server(tool_name)
            if server is None:
                return {"success": False, "error": f"工具 {tool_name} 未挂载到该 Agent"}
            return await mcp_client.call_tool(
                server,
                tool_name,
                args,
                user_id=user_id,
                context=tool_context,
            )

        deps = NodeDeps(
            model_config=model_config,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or None,
            deep_thinking=deep_thinking,
            tool_executor=_tool_executor,
            channel_resolver=_resolve_channel,
            chat_stream=provider_manager.chat_stream,
        )
        runtime = LangGraphRuntimeService(deps)

        full_content = ""
        update_counter = 0
        first_chunk_sent = False
        try:
            async for chunk in runtime.stream(llm_messages):
                if chunk.type == "text":
                    if chunk.metadata.get("is_reasoning"):
                        # 推理过程不并入最终正文，但仍透传给前端
                        yield chunk
                        continue
                    full_content += chunk.content
                    update_counter += 1
                    if update_counter % 5 == 0:
                        await self.update_message_content(
                            ai_message_id, full_content, "streaming"
                        )
                    if not first_chunk_sent:
                        chunk.metadata["session_id"] = session_id
                        chunk.metadata["message_id"] = ai_message_id
                        first_chunk_sent = True
                    yield chunk
                elif chunk.type == "error":
                    await self.update_message_content(
                        ai_message_id,
                        full_content or f"生成失败: {chunk.content}",
                        "error",
                        {"error": chunk.content},
                    )
                    yield chunk
                    return
                else:
                    # tool_call / tool_result 直接透传（metadata 已对齐 legacy）
                    yield chunk
        except Exception as e:  # noqa: BLE001
            await self.update_message_content(
                ai_message_id,
                full_content or f"生成失败: {e}",
                "error",
                {"error": str(e)},
            )
            yield ChatChunk(
                type="error",
                content=f"生成失败: {e}",
                metadata={"session_id": session_id, "message_id": ai_message_id},
            )
            return

        # 收尾：complete + usage + 会话用量累计 + done（与 legacy 一致）
        last_usage = runtime.last_usage
        await self.update_message_content(
            ai_message_id,
            full_content,
            "complete",
            {"usage": last_usage} if last_usage else None,
        )
        await self._apply_usage_to_session(ai_message_id, last_usage)
        yield ChatChunk(
            type="done",
            metadata={
                "session_id": session_id,
                "message_id": ai_message_id,
                "usage": last_usage,
            },
        )

    # --- 多模态与联网搜索辅助 ---

    @staticmethod
    async def _build_multimodal_messages(
        messages: list[dict[str, Any]], attachments: list[Any]
    ) -> list[dict[str, Any]]:
        """把附件注入到最后一条用户消息中。

        兼容策略：
        - 只有文本/文件附件时，保持 content 为字符串（对 Qwen 等国产模型兼容性最好）。
        - 包含图片附件时，使用 OpenAI 多模态 list 格式。
        """
        if not messages:
            return messages
        target_index = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=-1,
        )
        if target_index == -1:
            return messages

        target = messages[target_index]
        base_text = str(target.get("content", ""))

        # attachments 可能是 Pydantic ChatAttachment 对象列表，统一转成 dict
        attachment_dicts: list[dict[str, Any]] = [
            att.model_dump() if hasattr(att, "model_dump") else dict(att)
            for att in (attachments or [])
        ]

        has_image = any(
            att.get("type") == "image"
            or (att.get("mime_type", "").startswith("image/"))
            for att in attachment_dicts
        )

        async def _build_snippets(att: dict[str, Any]) -> list[str]:
            """为单个附件生成文本提示片段。"""
            text = await ChatService._read_attachment_text(att)
            file_id = att.get("file_id", "")
            max_len = 8000
            snippets: list[str] = []
            if file_id:
                # file_id 可能已带 scheme（file://uuid 或 upload://hex）；无 scheme 时按上传文件处理
                ref = file_id if "://" in file_id else f"upload://{file_id}"
                snippets.append(
                    f"[文件: {att.get('name', '')}，file_id: {ref}，"
                    f"可用 workspace_read_file(file_id=\"{ref}\") 读取内容，"
                    f"或在其它工具参数中直接引用该 file_id]"
                )
            if text:
                snippet = text[:max_len] + ("\n...（已截断）" if len(text) > max_len else "")
                snippets.append(f"[文件内容预览: {att.get('name', '')}]\n{snippet}")
            if not snippets:
                snippets.append(f"[文件 {att.get('name', '')} 读取失败或为空]")
            return snippets

        new_messages = list(messages)

        if not has_image:
            # 纯文本附件：拼成字符串，兼容性最好
            parts = [base_text]
            for att in attachment_dicts:
                snippets = await _build_snippets(att)
                parts.append("\n\n".join(snippets))
            new_messages[target_index] = {**target, "content": "\n\n".join(parts)}
            return new_messages

        # 含图片：使用 OpenAI 多模态 list 格式
        content: list[dict[str, Any]] = [{"type": "text", "text": base_text}]
        for att in attachment_dicts:
            att_type = att.get("type", "file")
            mime = att.get("mime_type", "")
            if att_type == "image" or (mime and mime.startswith("image/")):
                data_url = await ChatService._read_attachment_data_url(att)
                if data_url:
                    content.append({"type": "image_url", "image_url": {"url": data_url}})
                else:
                    content.append(
                        {
                            "type": "text",
                            "text": f"\n\n[图片 {att.get('name', '')} 读取失败]",
                        }
                    )
            else:
                snippets = await _build_snippets(att)
                content.append({"type": "text", "text": "\n\n" + "\n\n".join(snippets)})

        new_messages[target_index] = {**target, "content": content}
        return new_messages

    @staticmethod
    def _resolve_attachment_path(att_url: str) -> str | None:
        """把聊天附件 URL 解析为本地路径，非本地上传或越权则返回 None。"""
        prefix = "/api/v1/files/chat-upload/"
        if not att_url.startswith(prefix):
            return None
        rest = att_url[len(prefix) :]
        parts = rest.split("/", 1)
        if len(parts) != 2:
            return None
        user_id, filename = parts
        filename = Path(filename).name
        from omichub.infrastructure.config.storage_config import get_user_chat_upload_dir

        path = get_user_chat_upload_dir(user_id) / filename
        if path.is_file():
            return str(path)
        return None

    @staticmethod
    def _is_internal_url(url: str) -> bool:
        """禁止访问内网、回环、链路本地、metadata 等地址，防止 SSRF。"""
        if not url:
            return True
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return True
        host = parsed.hostname
        if not host:
            return True
        if host == "169.254.169.254":
            return True
        try:
            addr = ipaddress.ip_address(host)
            return (
                addr.is_loopback
                or addr.is_private
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
            )
        except ValueError:
            # 域名：放行；如需更严格可再校验是否解析到内网
            return False

    @staticmethod
    async def _read_attachment_data_url(att: dict[str, Any]) -> str:
        """读取附件并返回 base64 data URL（主要用于图片）。"""
        import base64

        att_url = att.get("url", "")
        mime = att.get("mime_type") or "application/octet-stream"
        local_path = ChatService._resolve_attachment_path(att_url)
        try:
            if local_path:
                async with await anyio.open_file(local_path, "rb") as f:
                    data = await f.read()
            else:
                if ChatService._is_internal_url(att_url):
                    logger.warning(f"拒绝读取内网/非法附件 URL: {att_url}")
                    return ""
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                    resp = await client.get(att_url)
                    resp.raise_for_status()
                    data = resp.content
            encoded = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{encoded}"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取附件失败 {att.get('name')}: {e}")
            return ""

    @staticmethod
    async def _read_attachment_text(att: dict[str, Any]) -> str:
        """读取文本类附件内容。"""
        att_url = att.get("url", "")
        local_path = ChatService._resolve_attachment_path(att_url)
        try:
            if local_path:
                async with await anyio.open_file(
                    local_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    return await f.read()
            if ChatService._is_internal_url(att_url):
                logger.warning(f"拒绝读取内网/非法附件 URL: {att_url}")
                return ""
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(att_url)
                resp.raise_for_status()
                return resp.text
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取文本附件失败 {att.get('name')}: {e}")
            return ""

    async def _resolve_model(self, model_id: uuid.UUID) -> AIProviderConfigModel | None:
        """按 ID 解析已启用的模型配置。"""
        result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.id == model_id,
                AIProviderConfigModel.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def _apply_usage_to_session(
        self,
        message_id: str,
        usage: dict[str, Any] | None,
    ) -> None:
        """把 LLM 返回的 usage 累加到会话 total_tokens，并写入消息 metadata。"""
        if not usage:
            return
        try:
            total = int(
                usage.get("total_tokens")
                or usage.get("total")
                or (
                    int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                    + int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                )
                or 0
            )
            if total <= 0:
                return
            msg_result = await self._db.execute(
                select(ChatMessageModel).where(ChatMessageModel.message_id == message_id)
            )
            msg = msg_result.scalar_one_or_none()
            if not msg:
                return
            session_result = await self._db.execute(
                select(ChatSessionModel).where(ChatSessionModel.session_id == msg.session_id)
            )
            session = session_result.scalar_one_or_none()
            if session:
                session.total_tokens += total
                await self._deduct_ai_cookies(session, total, message_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"累加 token 用量失败: {e}")

    async def _ensure_cookie_balance(self, user_id: str) -> str | None:
        """AI 对话准入闸门：饼干余额不足时返回错误文案，放行返回 None。"""
        settings = get_settings()
        if not settings.enable_cookie_system:
            return None
        try:
            from omichub.application.services.cookie_service import CookieService

            balance = await CookieService(self._db).check_balance(uuid.UUID(user_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"AI 对话饼干余额检查失败，放行: {e}")
            return None
        if balance > 0:
            return None
        rate = settings.ai_token_cookie_rate
        return (
            f"饼干余额不足，无法使用 AI 助手（每 1K tokens 消耗 {rate} 🥫）。"
            "请先通过提交分析任务赚取饼干后再试。"
        )

    async def _deduct_ai_cookies(
        self, session: ChatSessionModel, tokens: int, message_id: str
    ) -> None:
        """按 ai_token_cookie_rate 🥫/1K tokens 从会话属主账户扣减饼干。"""
        settings = get_settings()
        if not settings.enable_cookie_system or tokens <= 0:
            return
        try:
            from omichub.application.services.cookie_service import CookieService

            await CookieService(self._db).spend_ai_tokens(
                user_id=uuid.UUID(str(session.user_id)),
                tokens=tokens,
                source_id=message_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"AI 对话饼干扣减失败: {e}")

    async def _web_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """联网搜索占位实现：返回模拟结果，后续可替换为真实搜索引擎。"""
        query = arguments.get("query", "")
        top_n = int(arguments.get("top_n", 5))
        results = [
            {
                "title": f"与「{query}」相关的搜索结果示例 1",
                "url": "https://example.com/1",
                "snippet": "这是联网搜索返回的示例摘要，真实实现可接入 DuckDuckGo / Bing / 自建搜索。",
            },
            {
                "title": f"与「{query}」相关的搜索结果示例 2",
                "url": "https://example.com/2",
                "snippet": "示例摘要 2：OmicHub 后续可在此接入生物医学文献或通用网页搜索。",
            },
        ]
        return {"success": True, "result": {"query": query, "results": results[:top_n]}}

    # --- 助手管理 ---

    async def init_builtin_assistants(self) -> None:
        result = await self._db.execute(
            select(ChatAssistantModel).where(ChatAssistantModel.is_builtin == True)  # noqa: E712
        )
        if result.scalars().first():
            return
        for cfg in BUILTIN_ASSISTANTS:
            self._db.add(ChatAssistantModel(is_builtin=True, is_active=True, **cfg))
        await self._db.flush()

    async def list_assistants(self, category: str | None = None) -> list[ChatAssistantDTO]:
        await self.init_builtin_assistants()
        query = select(ChatAssistantModel).where(ChatAssistantModel.is_active == True)  # noqa: E712
        if category:
            query = query.where(ChatAssistantModel.category == category)
        query = query.order_by(ChatAssistantModel.created_at)
        result = await self._db.execute(query)
        return [self._to_ast_dto(a) for a in result.scalars().all()]

    async def get_assistant(self, assistant_id: str) -> ChatAssistantModel | None:
        result = await self._db.execute(
            select(ChatAssistantModel).where(ChatAssistantModel.assistant_id == assistant_id)
        )
        return result.scalar_one_or_none()

    async def get_assistant_dto(self, assistant_id: str) -> ChatAssistantDTO:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        return self._to_ast_dto(ast)

    async def create_custom_assistant(
        self,
        user_id: str,
        assistant_id: str,
        name: str,
        description: str,
        system_prompt: str,
        default_model_id: uuid.UUID | None = None,
        default_temperature: float = 0.3,
        default_max_tokens: int = 4096,
        icon: str = "\U0001f916",
        color: str = "#4f8ef7",
        category: str = "general",
    ) -> ChatAssistantDTO:
        existing = await self.get_assistant(assistant_id)
        if existing:
            raise BusinessError(f"助手 ID '{assistant_id}' 已存在")
        ast = ChatAssistantModel(
            assistant_id=assistant_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            default_model_id=default_model_id,
            default_temperature=default_temperature,
            default_max_tokens=default_max_tokens,
            icon=icon,
            color=color,
            category=category,
            is_builtin=False,
            is_active=True,
            created_by=user_id,
        )
        self._db.add(ast)
        await self._db.flush()
        return self._to_ast_dto(ast)

    async def list_all_assistants(self) -> list[ChatAssistantDTO]:
        """列出所有助手（含停用，供管理员）"""
        await self.init_builtin_assistants()
        result = await self._db.execute(
            select(ChatAssistantModel).order_by(
                ChatAssistantModel.is_default.desc(), ChatAssistantModel.created_at
            )
        )
        return [self._to_ast_dto(a) for a in result.scalars().all()]

    async def update_assistant(self, assistant_id: str, req: UpdateAssistantRequest) -> ChatAssistantDTO:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        data = req.model_dump(exclude_unset=True)
        # is_default=True 时需先清除其他助手默认标记
        if data.get("is_default"):
            result = await self._db.execute(
                select(ChatAssistantModel).where(ChatAssistantModel.is_default == True)  # noqa: E712
            )
            for existing in result.scalars().all():
                existing.is_default = False
        for key, value in data.items():
            setattr(ast, key, value)
        await self._db.flush()
        return self._to_ast_dto(ast)

    async def delete_assistant(self, assistant_id: str) -> bool:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        if ast.is_builtin:
            ast.is_active = False
            await self._db.flush()
            return True
        await self._db.delete(ast)
        await self._db.flush()
        return True

    async def toggle_assistant(self, assistant_id: str) -> ChatAssistantDTO:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        ast.is_active = not ast.is_active
        await self._db.flush()
        return self._to_ast_dto(ast)

    async def set_default_assistant(self, assistant_id: str) -> None:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        result = await self._db.execute(
            select(ChatAssistantModel).where(ChatAssistantModel.is_default == True)  # noqa: E712
        )
        for existing in result.scalars().all():
            existing.is_default = False
        ast.is_default = True
        await self._db.flush()

    # --- DTO 转换 ---

    @staticmethod
    def _to_session_dto(s: ChatSessionModel) -> ChatSessionDTO:
        return ChatSessionDTO(
            session_id=s.session_id,
            title=s.title,
            title_locked=s.title_locked,
            assistant_id=s.assistant_id,
            agent_id=s.agent_id,
            model_id=s.model_id,
            message_count=s.message_count,
            status=s.status,
            mode=s.mode or "chat",
            created_at=s.created_at,
            updated_at=s.updated_at,
            last_message_at=s.last_message_at,
        )

    @staticmethod
    def _to_msg_dto(m: ChatMessageModel) -> ChatMessageDTO:
        # Token usage belongs to the model response only; never expose it on user rows.
        usage = (
            (m.metadata_json or {}).get("usage") or {}
            if m.role == "assistant"
            else {}
        )
        input_tokens = (
            usage.get("prompt_tokens", 0)
            or usage.get("input_tokens", 0)
            or usage.get("input", 0)
        )
        output_tokens = (
            usage.get("completion_tokens", 0)
            or usage.get("output_tokens", 0)
            or usage.get("output", 0)
        )
        total_tokens = (
            usage.get("total_tokens", 0)
            or usage.get("total", 0)
            or input_tokens + output_tokens
        )
        return ChatMessageDTO(
            message_id=m.message_id,
            role=m.role,
            content=m.content,
            content_type=m.content_type,
            status=m.status,
            metadata_json=m.metadata_json or {},
            created_at=m.created_at,
            tokens={
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            },
        )

    @staticmethod
    def _to_ast_dto(a: ChatAssistantModel) -> ChatAssistantDTO:
        return ChatAssistantDTO(
            assistant_id=a.assistant_id,
            name=a.name,
            description=a.description,
            system_prompt=a.system_prompt,
            default_model_id=a.default_model_id,
            default_temperature=a.default_temperature,
            default_max_tokens=a.default_max_tokens,
            icon=a.icon,
            color=a.color,
            category=a.category,
            is_builtin=a.is_builtin,
            is_active=a.is_active,
            is_default=a.is_default,
        )
