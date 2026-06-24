"""任务域仓储接口"""

from typing import Protocol
from uuid import UUID

from omichub.domain.task.entities import Task


class ITaskRepository(Protocol):
    """任务仓储接口"""

    async def get_by_id(self, task_id: UUID) -> Task | None: ...

    async def list_by_user(
        self, user_id: UUID, status: str | None = None
    ) -> list[Task]: ...

    async def save(self, task: Task) -> Task: ...

    async def delete(self, task_id: UUID) -> bool: ...

    async def append_log(self, task_id: UUID, log_entry: dict) -> None: ...
