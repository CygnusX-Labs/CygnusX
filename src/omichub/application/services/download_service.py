"""数据下载应用服务 — 编排公共数据库与云存储下载任务。

复用通用 Task 聚合根承载下载任务（历史 flow_id="ebi_download"），不引入新领域表。
下载产物落到 `storage_path/users/<user_id>/raw_data/...`，完成后登记为 FileRecord，
自动出现在「数据管理」中。
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.download import DownloadRequest
from omichub.application.schemas.task import TaskListResponse, TaskResponse, task_to_response
from omichub.core.config import get_settings
from omichub.core.exceptions import NotFoundError, ValidationError
from omichub.domain.task.services import TaskDomainService
from omichub.domain.task.value_objects import TaskStatus
from omichub.infrastructure.celery_app.tasks.download import run_download
from omichub.infrastructure.database.repositories.task_repository import (
    TaskRepositoryImpl,
)

DOWNLOAD_FLOW_ID = "ebi_download"  # 兼容既有任务筛选；语义已扩展为数据下载聚合

_CLOUD_PROVIDER_LABELS = {
    "aliyun": "阿里云 OSS",
    "volc": "火山引擎 TOS",
    "volcengine": "火山引擎 TOS",
    "huawei": "华为云 OBS",
    "huaweicloud": "华为云 OBS",
}


class DownloadService:
    """数据下载服务"""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = TaskRepositoryImpl(db)
        self._domain = TaskDomainService(self._repo)
        self._settings = get_settings()

    async def submit(self, user_id: str, req: DownloadRequest) -> TaskResponse:
        """提交一个数据下载任务。"""
        directory = self._normalize_directory(req.target_directory)

        if req.source == "cloud_storage":
            provider = self._normalize_cloud_provider(req.cloud_provider or "")
            object_uri = req.object_uri.strip()
            safe_label = self._safe_path_label(f"{provider}_{object_uri}", fallback="cloud_storage")
            work_dir = self._make_work_dir(user_id, safe_label, directory)
            source_label = _CLOUD_PROVIDER_LABELS.get(provider, provider)
            task_name = f"云存储下载 {source_label} {object_uri}"
            parameters = {
                "source": "cloud_storage",
                "cloud_provider": provider,
                "object_uri": object_uri,
                "recursive": req.recursive,
                "target_directory": directory,
            }
        elif req.source == "direct_link":
            links = req.links
            safe_label = self._safe_path_label(links[0].split("/")[-1], fallback="direct_link")
            work_dir = self._make_work_dir(user_id, safe_label, directory)
            task_name = f"直链下载 {len(links)} 个文件"
            parameters = {
                "source": "direct_link",
                "links": links,
                "download_threads": req.download_threads,
                "overwrite_policy": req.overwrite_policy,
                "recursive": req.recursive,
                "target_directory": directory,
            }
        else:
            accession = req.accession.strip()
            safe_accession = self._safe_path_label(accession, fallback="sra")
            work_dir = self._make_work_dir(user_id, safe_accession, directory)
            task_name = f"EBI 下载 {accession}"
            parameters = {
                "source": "sra",
                "accession": accession,
                "download_method": req.download_method,
                "multithreads": req.multithreads,
                "aws_threads": req.aws_threads,
                "target_directory": directory,
                "dry_run": req.dry_run,
            }

        # 若指定了目标目录且尚未登记，自动创建 Directory 记录（物理目录已由 _make_work_dir 创建）
        if directory:
            from omichub.application.schemas.file import DirectoryCreateRequest
            from omichub.application.services.file_service import FileService

            file_svc = FileService(self._db)
            # 目录已存在则忽略（ConflictError），其他异常不阻断下载提交
            with contextlib.suppress(Exception):
                await file_svc.create_directory(
                    UUID(user_id), DirectoryCreateRequest(path=directory)
                )

        # 创建任务聚合根（复用通用 Task，flow_id 标记为数据下载）
        task = await self._domain.submit(
            flow_id=DOWNLOAD_FLOW_ID,
            user_id=UUID(user_id),
            name=task_name,
            parameters=parameters,
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

    async def get_task_for_user(self, task_id: UUID, user_id: str) -> TaskResponse:
        """获取任务详情并校验归属权。"""
        task = await self._repo.get_by_id(task_id)
        if task is None or str(task.user_id) != user_id:
            raise NotFoundError("任务不存在")
        if task.flow_id != DOWNLOAD_FLOW_ID:
            raise ValidationError("非下载任务")
        return task_to_response(task)

    @staticmethod
    def _normalize_directory(directory: str | None) -> str:
        if not directory:
            return ""
        d = directory.strip().strip("/")
        parts = [p for p in d.split("/") if p not in ("", ".", "..")]
        return "/".join(parts)

    @staticmethod
    def _normalize_cloud_provider(provider: str) -> str:
        normalized = {
            "volcengine": "volc",
            "huaweicloud": "huawei",
        }.get(provider, provider)
        if normalized not in {"aliyun", "volc", "huawei"}:
            raise ValidationError("不支持的云存储提供商")
        return normalized

    @staticmethod
    def _safe_path_label(value: str, fallback: str) -> str:
        label = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
        return (label or fallback)[:120]

    def _make_work_dir(self, user_id: str, label: str, directory: str = "") -> str:
        """下载产物目录 — 统一收拢到 users/{uid}/raw_data/{directory}/{label}/

        directory 为空时落到 raw_data 根目录。
        """
        base = Path(self._settings.storage_path) / "users" / user_id / "raw_data"
        if directory:
            base = base / directory
        work_dir = base / label
        work_dir.mkdir(parents=True, exist_ok=True)
        return str(work_dir)
