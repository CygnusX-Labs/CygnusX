"""Cherry Studio 架构聊天 API 路由

SSE 流式聊天 + 会话管理 + 助手管理
API 前缀：/api/v1/chat
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.chat import (
    ChatAssistantDTO,
    ChatHandoffEventDTO,
    ChatMessageDTO,
    ChatSessionDTO,
    ChatSessionSearchDTO,
    ChatStreamRequest,
    CreateAssistantRequest,
    CreateSessionRequest,
    UpdateSessionRequest,
)
from omichub.application.schemas.skill import SkillDTO
from omichub.application.services.chat_service import ChatService

router = APIRouter()


def get_chat_service(db: DbSession) -> ChatService:
    return ChatService(db)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


# ============================================================
# SSE 流式聊天（核心接口）
# ============================================================


@router.post("/stream", summary="SSE 流式聊天")
async def chat_stream(
    request: ChatStreamRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> StreamingResponse:
    """SSE 流式聊天接口

    - 传 ``agent_id``：走 Agent 调度中枢（组装模型/系统词/MCP 工具，含 tool_call 闭环）
    - 否则按 ``model_id`` 直连模型
    - Studio 会话（session_id 对应会话行 mode="studio"，或新建时显式传 mode="studio"）
      额外挂载工作台内置工具，sandbox_execute 的 stdout/stderr 以 tool_output 事件实时推送

    响应: data: {"type":"text","content":"你"}\\n\\n ...
    事件类型: text / tool_call / tool_output / tool_result / error / done
    """

    async def generate_sse():
        service = ChatService(db)
        if request.agent_id:
            gen = service.stream_agent_chat(
                user_id=current_user_id,
                agent_id=request.agent_id,
                messages=request.messages,
                session_id=request.session_id,
                model_id=request.model_id,
                attachments=request.attachments,
                enable_web_search=request.enable_web_search,
                enable_code_execution=request.enable_code_execution,
                deep_thinking=request.deep_thinking,
                mode=request.mode,
                mcp_mode=request.mcp_mode,
                extra_mcp_servers=request.extra_mcp_servers,
                multi_agent=request.multi_agent,
                extend_max_rounds=request.extend_max_rounds,
            )
        else:
            if not request.model_id:
                yield f"data: {json.dumps({'type': 'error', 'content': 'agent_id 与 model_id 至少传一个'}, ensure_ascii=False)}\n\n"
                return
            gen = service.stream_chat(
                user_id=current_user_id,
                messages=request.messages,
                model_id=request.model_id,
                session_id=request.session_id,
                assistant_id=request.assistant_id,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                enable_web_search=request.enable_web_search,
            )
        async for chunk in gen:
            data: dict = {"type": chunk.type, "content": chunk.content}
            if chunk.metadata:
                data.update(chunk.metadata)
            yield f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
            if chunk.type == "done":
                break
        await db.commit()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/web-search/availability", summary="联网搜索是否已配置")
async def web_search_availability(current_user_id: CurrentUserId, db: DbSession) -> dict[str, object]:
    from omichub.application.services.search_provider_service import SearchProviderService

    availability = await SearchProviderService(db).availability()
    return availability.model_dump()


@router.get(
    "/sessions/{session_id}/agentteams-events",
    summary="订阅聊天会话的 AgentTeams Case 状态事件",
)
async def agentteams_case_events(
    session_id: str,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> StreamingResponse:
    """为当前用户已打开的聊天会话提供后台 Case 状态 SSE。"""
    session = await ChatService(db).get_session(session_id, current_user_id)
    if session is None:
        async def missing_session():
            yield f"data: {json.dumps({'type': 'error', 'content': '会话不存在或无权访问'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(missing_session(), media_type="text/event-stream", status_code=404)

    async def generate_sse():
        from omichub.infrastructure.cache.chat_case_pubsub import subscribe_chat_case_events

        pubsub = await subscribe_chat_case_events(session_id)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        finally:
            await pubsub.unsubscribe()
            await pubsub.close()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# 可用模型列表（供前端选择模型下拉框）
# ============================================================


@router.get("/models", summary="可用模型列表")
async def list_models(db: DbSession) -> list[dict]:

    from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel

    result = await db.execute(
        select(AIProviderConfigModel)
        .where(AIProviderConfigModel.is_active == True)  # noqa: E712
        .order_by(AIProviderConfigModel.is_default.desc(), AIProviderConfigModel.name)
    )
    configs = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "model": c.model,
            "provider_type": c.provider_type,
            "is_default": c.is_default,
            "temperature": c.temperature,
            "max_tokens": c.max_tokens,
        }
        for c in configs
    ]


# ============================================================
# 会话管理
# ============================================================


@router.post("/sessions", response_model=ChatSessionDTO, summary="创建会话")
async def create_session(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    req: CreateSessionRequest,
) -> ChatSessionDTO:
    return await service.create_session(
        current_user_id, req.model_id, req.title or "新对话", req.assistant_id
    )


@router.get("/sessions", response_model=list[ChatSessionDTO], summary="会话列表")
async def list_sessions(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ChatSessionDTO]:
    return await service.list_sessions(current_user_id, limit=limit, offset=offset)


@router.get("/sessions/search", response_model=ChatSessionSearchDTO, summary="搜索会话")
async def search_sessions(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    keyword: str = Query(..., min_length=1, max_length=80),
) -> ChatSessionSearchDTO:
    return await service.search_sessions(current_user_id, keyword)


@router.get(
    "/sessions/{session_id}/messages", response_model=list[ChatMessageDTO], summary="会话消息"
)
async def get_messages(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    session_id: str,
) -> list[ChatMessageDTO]:
    session = await service.get_session(session_id, current_user_id)
    if not session:
        from omichub.core.exceptions import NotFoundError

        raise NotFoundError("会话不存在或无权访问")
    return await service.get_messages(session_id, current_user_id)


@router.get(
    "/sessions/{session_id}/handoffs",
    response_model=list[ChatHandoffEventDTO],
    summary="会话 Agent 转交审计",
)
async def get_session_handoffs(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    session_id: str,
) -> list[ChatHandoffEventDTO]:
    return await service.get_handoff_events(session_id, current_user_id)


@router.put("/sessions/{session_id}/title", summary="更新标题")
async def update_title(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    session_id: str,
    title: str = Query(..., min_length=1, max_length=200),
) -> dict[str, bool]:
    await service.update_session_title(session_id, current_user_id, title)
    return {"success": True}


@router.patch("/sessions/{session_id}", response_model=ChatSessionDTO, summary="重命名会话")
async def patch_session(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    session_id: str,
    req: UpdateSessionRequest,
) -> ChatSessionDTO:
    return await service.update_session_title(session_id, current_user_id, req.title, locked=True)


@router.post("/sessions/{session_id}/generate-title", response_model=dict, summary="生成会话标题")
async def generate_title(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    session_id: str,
) -> dict[str, str]:
    title = await service.generate_session_title(session_id, current_user_id)
    return {"title": title}


@router.delete("/sessions/{session_id}", summary="删除会话")
async def delete_session(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    session_id: str,
) -> dict[str, bool]:
    await service.delete_session(session_id, current_user_id)
    return {"success": True}


# ============================================================
# 助手管理
# ============================================================


@router.get("/assistants", response_model=list[ChatAssistantDTO], summary="助手列表")
async def list_assistants(
    service: ChatServiceDep,
    category: str | None = Query(None),
) -> list[ChatAssistantDTO]:
    return await service.list_assistants(category)


@router.get("/assistants/{assistant_id}", response_model=ChatAssistantDTO, summary="助手详情")
async def get_assistant(service: ChatServiceDep, assistant_id: str) -> ChatAssistantDTO:
    return await service.get_assistant_dto(assistant_id)


@router.post("/assistants", response_model=ChatAssistantDTO, summary="创建自定义助手")
async def create_assistant(
    current_user_id: CurrentUserId,
    service: ChatServiceDep,
    req: CreateAssistantRequest,
) -> ChatAssistantDTO:
    return await service.create_custom_assistant(
        user_id=current_user_id,
        assistant_id=req.assistant_id,
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
        default_temperature=req.default_temperature,
        default_max_tokens=req.default_max_tokens,
        icon=req.icon,
        color=req.color,
        category=req.category,
    )


# ============================================================
# 公开技能列表（供前端插件下拉，仅返回启用的）
# ============================================================


@router.get("/skills", response_model=list[SkillDTO], summary="技能列表（启用）")
async def list_active_skills(db: DbSession) -> list[SkillDTO]:
    from omichub.application.services.skill_service import SkillService

    service = SkillService(db)
    return await service.list_skills(active_only=True)
