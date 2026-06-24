"""任务路由"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_tasks():
    """获取任务列表"""
    return {"message": "list tasks"}


@router.post("/")
async def submit_task():
    """提交分析任务"""
    return {"message": "submit task"}


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务详情"""
    return {"task_id": task_id}


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: str):
    """获取任务执行日志"""
    return {"task_id": task_id, "logs": []}
