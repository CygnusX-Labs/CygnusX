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
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import anyio
import httpx
from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.chat import (
    ChatAssistantDTO,
    ChatMessageDTO,
    ChatSessionDTO,
    UpdateAssistantRequest,
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
        "icon": "\U0001f916",
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
        "icon": "\U0001f9ec",
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
        "icon": "\U0001f52c",
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
        "icon": "\U0001f4bb",
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
        "icon": "\U0001f4ca",
        "color": "#27ae60",
        "category": "visualization",
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

    # --- 会话管理 ---

    async def create_session(
        self,
        user_id: str,
        model_id: uuid.UUID,
        title: str = "新对话",
        assistant_id: str | None = None,
        agent_id: str | None = None,
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

    async def update_session_title(
        self, session_id: str, user_id: str, title: str
    ) -> ChatSessionDTO:
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
                existing = msg.metadata_json or {}
                existing.update(metadata)
                msg.metadata_json = existing
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
        # [极简测试] 临时禁用所有系统提示词，直接和裸模型对话
        final_system_prompt = None
        # final_system_prompt = system_prompt
        # if not final_system_prompt and assistant_id:
        #     ast = await self.get_assistant(assistant_id)
        #     if ast:
        #         final_system_prompt = ast.system_prompt
        # if not final_system_prompt:
        #     final_system_prompt = DEFAULT_SYSTEM_PROMPT

        # [极简测试] 临时禁用技能 prompt 注入
        # try:
        #     from omichub.application.services.skill_service import SkillService
        #
        #     skills = await SkillService(self._db).get_active_skills()
        #     if skills:
        #         final_system_prompt += SkillService.build_skills_prompt(skills)
        # except Exception as e:  # noqa: BLE001
        #     logger.warning(f"技能注入失败: {e}")

        # 4. 保存用户消息
        # 敏感信息脱敏：落库前清洗用户消息，DB 不留存原始品种名等敏感词；
        # 同时构建送 LLM 的脱敏副本（不可逆，不还原）
        from omichub.core.config import get_settings
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
    ) -> AsyncIterator[ChatChunk]:
        """Agent 编排闭环：查 Agent → 组装模型/系统词/工具 → 打 LLM → 执行 tool_call 回灌 → 流式返回"""
        from omichub.application.services.agent_service import AgentService
        from omichub.core.config import get_settings
        from omichub.core.sanitizer import sanitize_messages, sanitize_text
        from omichub.infrastructure.mcp.client import MCPClient

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
        if session_id:
            session = await self.get_session(session_id, user_id)
            if not session:
                yield ChatChunk(type="error", content="会话不存在或已被删除")
                return
            # 若用户切换了模型，同步更新会话记录的 model_id
            if model_id is not None and session.model_id != model_id:
                session.model_id = model_id
                session.updated_at = datetime.now(UTC)
            current_session_id = session_id
        else:
            title = f"与 {ctx.agent.name} 的对话"
            dto = await self.create_session(
                user_id,
                model_config.id,
                title,
                agent_id=agent_id,
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

        # 4. 送 LLM 的 messages（脱敏 + 附件多模态注入）
        llm_messages: list[dict[str, Any]] = sanitize_messages(messages, sensitive_keywords)
        if attachments:
            llm_messages = await self._build_multimodal_messages(llm_messages, attachments)

        # 动态追加联网搜索工具
        tools = list(ctx.tools or [])
        effective_web_search = enable_web_search or bool(ctx.features.get("enable_web_search"))
        if effective_web_search:
            tools.append(WEB_SEARCH_TOOL)

        full_content = ""
        update_counter = 0
        first_chunk_sent = False
        max_rounds = 8
        last_usage: dict[str, Any] | None = None

        mcp_client = MCPClient()

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
                    system_prompt=ctx.system_prompt or None,
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
                        # done 仅作为单轮结束信号，是否继续由 round_tool_calls 决定
                        last_usage = chunk.metadata.get("usage")

                # 本轮无工具调用 → 正常结束
                if not round_tool_calls:
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

                for tc in round_tool_calls:
                    fn = tc.get("function", {}) or {}
                    tool_name = fn.get("name", "")
                    raw_args = fn.get("arguments", "")
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    # 在绑定的 MCP server 中找到拥有该工具的 server
                    server = next(
                        (
                            s
                            for s in ctx.mcp_servers
                            if any(t.tool_name == tool_name for t in s.tools)
                        ),
                        None,
                    )

                    yield ChatChunk(
                        type="tool_call",
                        metadata={
                            "tool_call_id": tc.get("id", ""),
                            "tool_name": tool_name,
                            "arguments": args,
                            "mcp_server": server.name if server else None,
                        },
                    )

                    if server is None:
                        if tool_name == "web_search":
                            result = await self._web_search(args)
                        else:
                            result = {
                                "success": False,
                                "error": f"工具 {tool_name} 未挂载到该 Agent",
                            }
                    else:
                        result = await mcp_client.call_tool(
                            server, tool_name, args, user_id=user_id
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
                            "mcp_server": server.name if server else None,
                            "success": bool(result.get("success")),
                            "result": llm_result,
                            "ui_payload": ui_payload,
                        },
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
                snippets.append(
                    f"[文件: {att.get('name', '')} 已上传，file_id: {file_id}，"
                    f"可在工具参数中通过 upload://{file_id} 或直接作为 file_id 引用]"
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
                or (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0))
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
        except Exception as e:  # noqa: BLE001
            logger.warning(f"累加 token 用量失败: {e}")

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
            assistant_id=s.assistant_id,
            agent_id=s.agent_id,
            model_id=s.model_id,
            message_count=s.message_count,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            last_message_at=s.last_message_at,
        )

    @staticmethod
    def _to_msg_dto(m: ChatMessageModel) -> ChatMessageDTO:
        usage = (m.metadata_json or {}).get("usage") or {}
        return ChatMessageDTO(
            message_id=m.message_id,
            role=m.role,
            content=m.content,
            content_type=m.content_type,
            status=m.status,
            metadata_json=m.metadata_json or {},
            created_at=m.created_at,
            tokens={
                "input": usage.get("prompt_tokens", 0) or usage.get("input", 0),
                "output": usage.get("completion_tokens", 0) or usage.get("output", 0),
                "total": usage.get("total_tokens", 0) or usage.get("total", 0),
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
