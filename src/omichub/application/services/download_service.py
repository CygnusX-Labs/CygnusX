"""数据下载应用服务 — 编排 EBI 数据下载任务。

复用通用 Task 聚合根承载下载任务（flow_id="ebi_download"），不引入新领域表。
下载产物落到 `storage_path/upload_dir/<user_id>/ebi_download/<accession>/`，
借 FileService 的文件系统扫描自动出现在 /files。
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.download import DownloadRequest
from omichub.application.schemas.task import TaskListResponse, TaskResponse, task_to_response
from omichub.core.config import get_settings
from omichub.core.exceptions import ValidationError
from omichub.domain.task.services import TaskDomainService
from omichub.domain.task.value_objects import TaskStatus
from omichub.infrastructure.celery_app.tasks.download import run_download
from omichub.infrastructure.database.repositories.task_repository import (
    TaskRepositoryImpl,
)

DOWNLOAD_FLOW_ID = "ebi_download"


class DownloadService:
    """数据下载服务"""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = TaskRepositoryImpl(db)
        self._domain = TaskDomainService(self._repo)
        self._settings = get_settings()

    async def submit(self, user_id: str, req: DownloadRequest) -> TaskResponse:
        """提交一个数据下载任务。"""
        if not req.accession or not req.accession.strip():
            raise ValidationError("登录号 (accession) 不能为空")

        accession = req.accession.strip()
        work_dir = self._make_work_dir(user_id, accession)

        # 创建任务聚合根（复用通用 Task，flow_id 标记为数据下载）
        task = await self._domain.submit(
            flow_id=DOWNLOAD_FLOW_ID,
            user_id=UUID(user_id),
            name=f"EBI 下载 {accession}",
            parameters={
                "accession": accession,
                "download_method": req.download_method,
                "multithreads": req.multithreads,
                "aws_threads": req.aws_threads,
            },
            sample_count=0,
        )
        task.work_dir = work_dir
        task = await self._repo.save(task)

        # 投递 Celery 下载任务
        run_download.delay(task_id=str(task.id))

        # 状态推进为已入队
        task = await self._domain.transition_status(task, TaskStatus.QUEUED)
        return task_to_response(task)

    async def list_downloads(self, user_id: str) -> TaskListResponse:
        """列出当前用户的数据下载任务。"""
        tasks = await self._repo.list_by_user(UUID(user_id))
        downloads = [t for t in tasks if t.flow_id == DOWNLOAD_FLOW_ID]
        return TaskListResponse(
            items=[task_to_response(t) for t in downloads],
            total=len(downloads),
        )

    def _make_work_dir(self, user_id: str, accession: str) -> str:
        """下载产物目录 — 落在 upload_dir 下以触发 Files 自动入库。

        storage_path/upload_dir/<user_id>/ebi_download/<accession>/
        建目录（同步，仿 task_service._make_work_dir），返回路径字符串。
        """
        # accession 仅用作目录名，去除可能的路径分隔符以防越权
        safe_acc = accession.replace("/", "_").replace("\\", "_").strip()
        work_dir = (
            Path(self._settings.storage_path)
            / self._settings.upload_dir
            / user_id
            / "ebi_download"
            / safe_acc
        )
        work_dir.mkdir(parents=True, exist_ok=True)
        return str(work_dir)
