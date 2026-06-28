"""Cherry Studio 架构聊天业务服务

核心职责：
1. 会话 CRUD（创建、查询、更新、软删除）
2. 消息持久化（用户消息 + AI 消息）
3. SSE 流式聊天编排（调用 LLM + 实时更新数据库）
4. 内置助手管理（初始化预设助手）
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.chat import (
    ChatAssistantDTO,
    ChatMessageDTO,
    ChatSessionDTO,
)
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.infrastructure.ai_provider.openai_compatible import ChatChunk, provider_manager
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel
from omichub.infrastructure.database.models.chat import (
    ChatAssistantModel,
    ChatMessageModel,
    ChatSessionModel,
)

DEFAULT_SYSTEM_PROMPT = (
    "你是 OmicHub AI 助手，一个专业的多组学数据分析助手。"
    "你精通 RNA-seq、单细胞转录组、蛋白质组学、代谢组学等领域的数据分析。"
    "请使用中文回答，保持专业性和准确性。"
)

BUILTIN_ASSISTANTS: list[dict[str, Any]] = [
    {
        "assistant_id": "general",
        "name": "通用助手",
        "description": "OmicHub 通用 AI 助手，回答各类问题",
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "default_temperature": 0.7,
        "default_max_tokens": 2048,
        "icon": "\U0001F916",
        "color": "#4f8ef7",
        "category": "general",
    },
    {
        "assistant_id": "rna_seq_analyst",
        "name": "RNA-seq 分析师",
        "description": "专注于 RNA-seq 差异表达分析、通路富集、可视化",
        "system_prompt": (
            "你是 OmicHub 的 RNA-seq 分析专家，精通差异表达分析全流程。\n"
            "你可以帮助用户设计 RNA-seq 分析流程（DESeq2 / edgeR / limma）、"
            "解读差异表达结果、进行 GO / KEGG / GSEA 富集分析、"
            "生成高质量可视化图表。请提供具体的代码示例和参数解释。"
        ),
        "default_temperature": 0.3,
        "default_max_tokens": 4096,
        "icon": "\U0001F9EC",
        "color": "#4f8ef7",
        "category": "analysis",
    },
    {
        "assistant_id": "scrna_analyst",
        "name": "单细胞分析师",
        "description": "专注于单细胞转录组分析、降维聚类、细胞注释",
        "system_prompt": (
            "你是 OmicHub 的单细胞转录组分析专家，精通 Scanpy 和 Seurat 分析流程。\n"
            "你可以帮助用户质控过滤、降维聚类、细胞类型注释、"
            "绘制 UMAP / t-SNE 图、伪时间分析、细胞通讯分析。"
            "推荐使用 Scanpy 进行交互式分析。"
        ),
        "default_temperature": 0.3,
        "default_max_tokens": 4096,
        "icon": "\U0001F52C",
        "color": "#e74c3c",
        "category": "analysis",
    },
    {
        "assistant_id": "code_helper",
        "name": "代码助手",
        "description": "帮助编写和调试生信分析代码（Python / R）",
        "system_prompt": (
            "你是 OmicHub 的编程助手，精通生物信息学相关的 Python 和 R 代码。\n"
            "请提供完整可运行的代码，并添加详细的中文注释。"
        ),
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "icon": "\U0001F4BB",
        "color": "#f39c12",
        "category": "code",
    },
    {
        "assistant_id": "visualization",
        "name": "可视化助手",
        "description": "帮助创建和优化科研图表",
        "system_prompt": (
            "你是 OmicHub 的数据可视化专家，精通科研图表的制作和优化。\n"
            "你可以帮助用户推荐图表类型、优化配色布局、"
            "使用 matplotlib / seaborn / plotly / ggplot2 绘制图表。"
        ),
        "default_temperature": 0.3,
        "default_max_tokens": 4096,
        "icon": "\U0001F4CA",
        "color": "#27ae60",
        "category": "visualization",
    },
]


class ChatService:
    """聊天业务服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # --- 会话管理 ---

    async def create_session(
        self, user_id: str, model_id: uuid.UUID, title: str = "新对话",
        assistant_id: str | None = None,
    ) -> ChatSessionDTO:
        session = ChatSessionModel(
            id=uuid.uuid4(), session_id=str(uuid.uuid4()), user_id=user_id,
            model_id=model_id, title=title, assistant_id=assistant_id, status="active",
        )
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

    async def list_sessions(self, user_id: str) -> list[ChatSessionDTO]:
        result = await self._db.execute(
            select(ChatSessionModel)
            .where(ChatSessionModel.user_id == user_id, ChatSessionModel.status == "active")
            .order_by(desc(ChatSessionModel.updated_at))
        )
        return [self._to_session_dto(s) for s in result.scalars().all()]

    async def update_session_title(self, session_id: str, user_id: str, title: str) -> ChatSessionDTO:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise NotFoundError("会话不存在或无权访问")
        session.title = title
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return self._to_session_dto(session)

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
        self, session_id: str, role: str, content: str = "",
        content_type: str = "text", status: str = "complete",
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessageModel:
        message = ChatMessageModel(
            id=uuid.uuid4(), message_id=str(uuid.uuid4()), session_id=session_id,
            role=role, content=content, content_type=content_type,
            status=status, metadata_json=metadata or {},
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
        self, message_id: str, content: str, status: str = "complete",
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
                existing = msg.metadata_json or {}
                existing.update(metadata)
                msg.metadata_json = existing
            await self._db.flush()

    async def get_messages(self, session_id: str) -> list[ChatMessageDTO]:
        result = await self._db.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        return [self._to_msg_dto(m) for m in result.scalars().all()]

    # --- SSE 流式聊天 ---

    async def stream_chat(
        self, user_id: str, messages: list[dict[str, str]], model_id: uuid.UUID,
        session_id: str | None = None, assistant_id: str | None = None,
        system_prompt: str | None = None, temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
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

        # 3. 确定系统提示词
        final_system_prompt = system_prompt
        if not final_system_prompt and assistant_id:
            ast = await self.get_assistant(assistant_id)
            if ast:
                final_system_prompt = ast.system_prompt
        if not final_system_prompt:
            final_system_prompt = DEFAULT_SYSTEM_PROMPT

        # 技能 prompt 注入
        try:
            from omichub.application.services.skill_service import SkillService

            skills = await SkillService(self._db).get_active_skills()
            if skills:
                final_system_prompt += SkillService.build_skills_prompt(skills)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"技能注入失败: {e}")

        # 4. 保存用户消息
        user_content = messages[-1].get("content", "") if messages else ""
        await self.add_message(current_session_id, "user", user_content)

        # 5. 创建 AI 消息记录
        ai_message = await self.add_message(
            current_session_id, "assistant", "", status="streaming",
            metadata={"model": model_config.name, "model_id": str(model_id)},
        )

        # 6. 调用 LLM 流式输出
        full_content = ""
        update_counter = 0

        try:
            final_temp = temperature if temperature is not None else model_config.temperature
            final_max = max_tokens if max_tokens is not None else model_config.max_tokens

            async for chunk in provider_manager.chat_stream(
                config=model_config, messages=messages,
                system_prompt=final_system_prompt,
                temperature=final_temp, max_tokens=final_max,
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
                        "error", {"error": chunk.content},
                    )
                    yield chunk
                    return

                elif chunk.type == "done":
                    await self.update_message_content(
                        ai_message.message_id, full_content, "complete"
                    )
                    chunk.metadata["session_id"] = current_session_id
                    chunk.metadata["message_id"] = ai_message.message_id
                    yield chunk
                    return

                yield chunk

        except Exception as e:  # noqa: BLE001
            await self.update_message_content(
                ai_message.message_id, full_content or f"生成失败: {e}",
                "error", {"error": str(e)},
            )
            yield ChatChunk(
                type="error", content=f"生成失败: {e}",
                metadata={"session_id": current_session_id, "message_id": ai_message.message_id},
            )

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
        self, user_id: str, assistant_id: str, name: str, description: str,
        system_prompt: str, default_model_id: uuid.UUID | None = None,
        default_temperature: float = 0.3, default_max_tokens: int = 4096,
        icon: str = "\U0001F916", color: str = "#4f8ef7", category: str = "general",
    ) -> ChatAssistantDTO:
        existing = await self.get_assistant(assistant_id)
        if existing:
            raise BusinessError(f"助手 ID '{assistant_id}' 已存在")
        ast = ChatAssistantModel(
            assistant_id=assistant_id, name=name, description=description,
            system_prompt=system_prompt, default_model_id=default_model_id,
            default_temperature=default_temperature, default_max_tokens=default_max_tokens,
            icon=icon, color=color, category=category,
            is_builtin=False, is_active=True, created_by=user_id,
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

    async def update_assistant(self, assistant_id: str, req) -> ChatAssistantDTO:
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
            session_id=s.session_id, title=s.title, assistant_id=s.assistant_id,
            model_id=s.model_id, message_count=s.message_count, status=s.status,
            created_at=s.created_at, updated_at=s.updated_at, last_message_at=s.last_message_at,
        )

    @staticmethod
    def _to_msg_dto(m: ChatMessageModel) -> ChatMessageDTO:
        return ChatMessageDTO(
            message_id=m.message_id, role=m.role, content=m.content,
            content_type=m.content_type, status=m.status,
            metadata_json=m.metadata_json or {}, created_at=m.created_at,
        )

    @staticmethod
    def _to_ast_dto(a: ChatAssistantModel) -> ChatAssistantDTO:
        return ChatAssistantDTO(
            assistant_id=a.assistant_id, name=a.name, description=a.description,
            system_prompt=a.system_prompt, default_model_id=a.default_model_id,
            default_temperature=a.default_temperature, default_max_tokens=a.default_max_tokens,
            icon=a.icon, color=a.color, category=a.category,
            is_builtin=a.is_builtin, is_active=a.is_active, is_default=a.is_default,
        )
