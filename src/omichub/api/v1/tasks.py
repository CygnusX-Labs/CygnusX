"""任务路由"""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from omichub.api.deps import CurrentUserId, DbSession
from omichub.application.schemas.task import (
    TaskListResponse,
    TaskResponse,
    TaskSubmitRequest,
)
from omichub.application.services.task_service import TaskService
from omichub.core.security import decode_token
from omichub.infrastructure.cache.pubsub import subscribe_task_logs
from omichub.infrastructure.database.repositories.task_repository import (
    TaskRepositoryImpl,
)
from omichub.infrastructure.database.session import get_session_factory

router = APIRouter()


def get_task_service(db: DbSession) -> TaskService:
    """获取任务服务实例"""
    return TaskService(db)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


@router.get("", response_model=TaskListResponse, summary="获取任务列表")
async def list_tasks(
    current_user_id: CurrentUserId,
    service: TaskServiceDep,
    status: Annotated[str | None, Query(description="按状态过滤")] = None,
) -> TaskListResponse:
    """获取当前用户的任务列表"""
    return await service.list_tasks(current_user_id, status=status)


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="提交分析任务",
)
async def submit_task(
    req: TaskSubmitRequest,
    current_user_id: CurrentUserId,
    service: TaskServiceDep,
) -> TaskResponse:
    """提交新的分析任务"""
    return await service.submit(current_user_id, req)


@router.get("/{task_id}", response_model=TaskResponse, summary="获取任务详情")
async def get_task(
    task_id: UUID,
    current_user_id: CurrentUserId,
    service: TaskServiceDep,
) -> TaskResponse:
    """获取指定任务详情"""
    return await service.get_task(task_id, current_user_id)


@router.get("/{task_id}/logs", summary="获取任务日志")
async def get_task_logs(
    task_id: UUID,
    current_user_id: CurrentUserId,
    service: TaskServiceDep,
) -> dict:
    """获取任务执行日志"""
    task = await service.get_task(task_id, current_user_id)
    return {
        "task_id": str(task_id),
        "logs": [log.model_dump() for log in task.logs],
    }


@router.post("/{task_id}/cancel", response_model=TaskResponse, summary="取消任务")
async def cancel_task(
    task_id: UUID,
    current_user_id: CurrentUserId,
    service: TaskServiceDep,
) -> TaskResponse:
    """取消未结束的任务"""
    return await service.cancel_task(task_id, current_user_id)


@router.get("/{task_id}/dag", summary="获取任务 DAG 可视化")
async def get_task_dag(
    task_id: UUID,
    current_user_id: CurrentUserId,
    service: TaskServiceDep,
) -> dict:
    """生成并返回 Snakemake DAG（SVG 或 DOT 文本）"""
    result = await service.get_task_dag(task_id, current_user_id)
    return result


@router.websocket("/{task_id}/ws", name="task_logs_websocket")
async def task_logs_websocket(websocket: WebSocket, task_id: str):
    """任务日志 WebSocket 实时推送。

    连接示例：wss://host/api/v1/tasks/{task_id}/ws?token=<JWT>
    """
    token = websocket.query_params.get("token")
    payload = decode_token(token) if token else None
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=1008, reason="Invalid token")
        return

    user_id = payload.get("sub")

    # 校验任务归属
    async with get_session_factory()() as session:
        repo = TaskRepositoryImpl(session)
        task = await repo.get_by_id(UUID(task_id))
        if task is None or str(task.user_id) != user_id:
            await websocket.close(code=1008, reason="Task not found")
            return

    await websocket.accept()
    pubsub = await subscribe_task_logs(task_id)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe()
        await pubsub.close()
