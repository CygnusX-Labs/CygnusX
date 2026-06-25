"""任务域服务 - 状态机管理"""

from datetime import datetime
from uuid import UUID

from omichub.core.exceptions import ValidationError
from omichub.domain.task.entities import Task
from omichub.domain.task.repositories import ITaskRepository
from omichub.domain.task.value_objects import ExecutionMode, LogLevel, TaskStatus


class TaskDomainService:
    """任务域服务 - 状态转换、调度策略"""

    def __init__(self, repo: ITaskRepository):
        self._repo = repo

    async def submit(
        self,
        flow_id: str,
        user_id: UUID,
        name: str,
        parameters: dict,
        execution_mode: ExecutionMode = ExecutionMode.LOCAL,
    ) -> Task:
        """提交新任务：创建聚合根并持久化"""
        from uuid import uuid4

        task = Task(
            id=uuid4(),
            flow_id=flow_id,
            user_id=user_id,
            name=name,
            status=TaskStatus.PENDING,
            execution_mode=execution_mode,
            parameters=parameters,
        )
        return await self._repo.save(task)

    async def transition_status(self, task: Task, new_status: TaskStatus) -> Task:
        """执行状态转换（含合法性校验）"""
        if not task.can_transition_to(new_status):
            raise ValidationError(
                f"非法状态转换: {task.status} → {new_status}"
            )
        task.status = new_status
        if new_status == TaskStatus.RUNNING and task.started_at is None:
            task.started_at = datetime.now()
        elif new_status in {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            task.finished_at = datetime.now()
        return await self._repo.save(task)

    async def add_log(
        self, task_id: UUID, level: LogLevel, message: str, source: str = ""
    ) -> None:
        """追加任务日志"""
        from datetime import datetime

        await self._repo.append_log(task_id, {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "message": message,
            "source": source,
        })
