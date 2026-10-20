"""用户管理路由"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from cygnusx.api.deps import CurrentUserId, DbSession
from cygnusx.application.schemas.agent_memory import (
    AgentMemoryClearResponse,
    AgentMemoryDTO,
    MemoryBlockDTO,
    MemoryBlockUpdateRequest,
    MemoryForgetResponse,
    MemoryOverviewDTO,
    MemoryResidualActionRequest,
)
from cygnusx.application.schemas.user import (
    ChangePasswordRequest,
    UserListItem,
    UserResponse,
    UserUpdateRequest,
)
from cygnusx.application.services import UserService
from cygnusx.application.services.agent_memory_service import AgentMemoryService
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import AuthorizationError, BusinessError, NotFoundError
from cygnusx.infrastructure.database.models.audit_log import AuditLogModel
from cygnusx.infrastructure.database.models.chat import ChatSessionModel
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.infrastructure.database.repositories import SqlAlchemyUserRepository
from cygnusx.infrastructure.task_queue.dispatcher import enqueue_task
from cygnusx.middleware.rbac import require_roles

router = APIRouter()


@router.get("/lookup", summary="协作室邀请用最小用户目录")
async def lookup_users(
    current_user_id: CurrentUserId,
    db: DbSession,
    q: str = Query(min_length=1, max_length=64),
) -> list[dict[str, str | None]]:
    """Only expose the minimum identity fields needed by the room invitation picker."""
    term = q.strip()
    if not term:
        return []
    rows = await db.scalars(
        select(UserModel)
        .where(UserModel.status == "active")
        .where((UserModel.username.ilike(f"{term}%")) | (UserModel.nickname.ilike(f"{term}%")))
        .order_by(UserModel.username.asc())
        .limit(20)
    )
    return [
        {"id": str(user.id), "nickname": user.nickname or user.username, "avatar": user.avatar_url}
        for user in rows
        if str(user.id) != current_user_id
    ]


def get_user_service(db: DbSession) -> UserService:
    """获取用户服务实例"""
    return UserService(SqlAlchemyUserRepository(db))


@router.get("/me/memories", response_model=list[AgentMemoryDTO])
async def list_my_memories(
    current_user_id: CurrentUserId,
    db: DbSession,
    agent_id: str | None = Query(None, max_length=50),
    scope: str | None = Query(None, pattern="^(profile|project|preference|summary|episode)$"),
    project_id: str | None = Query(None, max_length=64),
) -> list[AgentMemoryDTO]:
    """列出当前用户可管理的跨会话 Agent 记忆。"""
    memories = await AgentMemoryService(db).list_memories(
        current_user_id, agent_id=agent_id, scope=scope, project_id=project_id
    )
    return [AgentMemoryDTO(**AgentMemoryService._serialize(memory)) for memory in memories]


@router.get("/me/memory-overview", response_model=MemoryOverviewDTO)
async def get_my_memory_overview(
    current_user_id: CurrentUserId,
    db: DbSession,
    agent_id: str | None = Query(None, max_length=50),
    project_id: str | None = Query(None, max_length=50),
    scope: str | None = Query(None, pattern="^(profile|project|preference|summary|episode)$"),
    include_archived: bool = Query(False),
) -> MemoryOverviewDTO:
    overview = await AgentMemoryService(db).get_memory_overview(
        current_user_id,
        agent_id=agent_id,
        project_id=project_id,
        scope=scope,
        include_archived=include_archived,
    )
    return MemoryOverviewDTO(**overview)


@router.patch("/me/memory-blocks/{block_name}", response_model=MemoryBlockDTO)
async def update_my_memory_block(
    block_name: str,
    req: MemoryBlockUpdateRequest,
    current_user_id: CurrentUserId,
    db: DbSession,
    agent_id: str = Query("", max_length=50),
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> MemoryBlockDTO:
    if project_id is not None:
        if block_name != "current_focus" or not get_settings().memory_focus_per_project_enabled:
            raise BusinessError("项目焦点编辑当前不可用")
        from cygnusx.infrastructure.database.models.project import ProjectModel

        owned = await db.scalar(select(ProjectModel.id).where(
            ProjectModel.id == project_id, ProjectModel.user_id == uuid.UUID(current_user_id),
        ))
        if owned is None:
            raise NotFoundError("项目不存在")
    block = await AgentMemoryService(db).update_memory_block(
        current_user_id,
        agent_id,
        block_name,
        req.content,
        req.expected_version,
        project_id=str(project_id) if project_id is not None else None,
    )
    return MemoryBlockDTO(**block)


@router.post("/me/memories/rebuild")
async def rebuild_my_memories(
    current_user_id: CurrentUserId,
    db: DbSession,
) -> dict[str, int | str]:
    """为历史上尚未触发沉淀的长会话补投记忆任务。"""
    settings = get_settings()
    if not settings.memory_v2_enabled:
        return {"status": "disabled", "queued": 0}

    minimum_messages = max(
        2,
        settings.memory_settle_min_new_messages,
    )
    sessions = list(
        (
            await db.scalars(
                select(ChatSessionModel).where(
                    ChatSessionModel.user_id == current_user_id,
                    ChatSessionModel.status != "deleted",
                    ChatSessionModel.message_count >= minimum_messages,
                )
            )
        ).all()
    )
    from cygnusx.infrastructure.celery_app.tasks.memory import settle_session_memory

    for session in sessions:
        enqueue_task(settle_session_memory, session.session_id, countdown=5)
    return {"status": "queued", "queued": len(sessions)}


@router.post("/me/memories/{memory_id}/forget", response_model=MemoryForgetResponse)
async def forget_my_memory(
    memory_id: str, current_user_id: CurrentUserId, db: DbSession,
    agent_id: Annotated[str | None, Query(max_length=50)] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> MemoryForgetResponse:
    """归档指定记忆，返回可见范围内的词面残留提示。"""
    result = await AgentMemoryService(db).forget_memory(
        user_id=current_user_id, memory_id=memory_id, agent_id=agent_id,
        project_id=str(project_id) if project_id else None,
    )
    return MemoryForgetResponse(**result)


@router.post("/me/memory-residual-actions", status_code=204)
async def record_memory_residual_action(
    req: MemoryResidualActionRequest, current_user_id: CurrentUserId, db: DbSession,
) -> None:
    """记录本人报告的处理点击；不授予权限、不修改记忆。"""
    from cygnusx.application.services.memory_residual_service import MemoryResidualService

    await MemoryResidualService(db).record_action(current_user_id, **req.model_dump())


@router.delete("/me/memories/{memory_id}", status_code=204)
async def delete_my_memory(
    memory_id: str,
    current_user_id: CurrentUserId,
    db: DbSession,
) -> None:
    """兼容删除入口：v2 归档；需要残留提示时使用 forget 入口。"""
    await AgentMemoryService(db).delete_memory(current_user_id, memory_id)


@router.delete("/me/memories", response_model=AgentMemoryClearResponse)
async def clear_my_memories(
    current_user_id: CurrentUserId,
    db: DbSession,
    agent_id: str | None = Query(None, max_length=50),
) -> AgentMemoryClearResponse:
    """归档清空当前用户全部或指定 Agent 的记忆。"""
    cleared_count = await AgentMemoryService(db).clear_memories(
        current_user_id, agent_id=agent_id
    )
    return AgentMemoryClearResponse(cleared_count=cleared_count)


@router.get("/me/audit-logs")
async def get_my_audit_logs(
    current_user_id: CurrentUserId,
    db: DbSession,
    limit: int = Query(5, ge=1, le=50),
) -> list[dict[str, str]]:
    """返回当前用户最近的真实写操作审计记录。"""
    rows = await db.scalars(
        select(AuditLogModel)
        .where(AuditLogModel.user_id == uuid.UUID(current_user_id))
        .order_by(AuditLogModel.created_at.desc())
        .limit(limit)
    )

    def category(path: str) -> tuple[str, str]:
        if "/password" in path:
            return "password", "密码"
        if "/2fa" in path:
            return "security", "安全"
        if "delete" in path or path.endswith("/account"):
            return "delete", "删除"
        if "/users" in path:
            return "email", "资料"
        return "security", "操作"

    return [
        {
            "type": category(row.path)[0],
            "type_label": category(row.path)[1],
            "description": f"{row.method} {row.path}",
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get(
    "/",
    dependencies=[Depends(require_roles("admin"))],
    response_model=list[UserListItem],
)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    q: str | None = Query(None, description="搜索关键词（用户名/邮箱）"),
    role: str | None = Query(None),
    status: str | None = Query(None),
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """获取用户列表（仅管理员）"""
    users, _total = await user_service.get_user_list(page, page_size, q, role, status)
    return [UserListItem.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user_id: CurrentUserId,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """获取用户详情（普通用户只能查看自己，管理员可查看所有）"""
    # 普通用户只能查看自己
    if user_id != current_user_id:
        # 检查是否为管理员 - 通过 require_roles 依赖已校验
        # 此处简化处理：非自己的请求需要管理员权限
        # TODO: 完整 RBAC 检查需要查询用户角色
        raise AuthorizationError("无权查看其他用户信息")

    user = await user_service.get_user_by_id(user_id)
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    req: UserUpdateRequest,
    current_user_id: CurrentUserId,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """更新用户信息（普通用户只能更新自己）"""
    if user_id != current_user_id:
        raise AuthorizationError("无权修改其他用户信息")

    user = await user_service.update_user(user_id, req)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", dependencies=[Depends(require_roles("admin"))])
async def delete_user(
    user_id: str,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """删除用户（仅管理员）"""
    await user_service.delete_user(user_id)
    return {"message": "用户删除成功"}


@router.put("/{user_id}/password")
async def change_password(
    user_id: str,
    req: ChangePasswordRequest,
    current_user_id: CurrentUserId,
    user_service: Annotated[UserService, Depends(get_user_service)] = None,
):
    """修改密码（只能修改自己的密码）"""
    if user_id != current_user_id:
        raise AuthorizationError("无权修改其他用户密码")

    await user_service.change_password(user_id, req.old_password, req.new_password)
    return {"message": "密码修改成功"}
