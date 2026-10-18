"""数据下载应用服务 — 编排公共数据库与云存储下载任务。

复用通用 Task 聚合根承载下载任务（历史 flow_id="ebi_download"），不引入新领域表。
下载产物落到 ``{data_root}/users/<user_id>/downloads/...``（顶层 downloads/），
完成后登记为 FileRecord，自动出现在「数据管理」中。
"""

from __future__ import annotations

import json
import os
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError as RequestValidationError
from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.schemas.task import TaskListResponse, TaskResponse, task_to_response
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import ConflictError, NotFoundError, ValidationError
from cygnusx.domain.download_contract import validate_transport
from cygnusx.domain.task.services import TaskDomainService
from cygnusx.domain.task.value_objects import TaskStatus
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.infrastructure.database.repositories.task_repository import (
    TaskRepositoryImpl,
)
from cygnusx.infrastructure.download.reliability import intent_digest, notify_after_commit
from cygnusx.infrastructure.storage import get_path_factory, get_storage_backend
from cygnusx.infrastructure.storage.backend import StorageBackend
from cygnusx.tools.download.config import ensure_download_available, get_download_config

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

    def __init__(self, db: AsyncSession, backend: StorageBackend | None = None) -> None:
        self._db = db
        self._repo = TaskRepositoryImpl(db)
        self._domain = TaskDomainService(self._repo)
        self._backend = backend or get_storage_backend()

    async def submit(
        self, user_id: str, req: DownloadRequest, *, project_id: UUID | None = None
    ) -> TaskResponse:
        """提交一个数据下载任务。

        下载产物默认落到顶层 ``downloads/``，与 ``inbox/``（用户上传暂存）解耦。
        target_directory 仅指定用户根内相对父目录；每个新 Task 分配独立子目录。
        """
        # Internal callers can mutate a Pydantic instance or construct one without validation.
        # Rebuild a copy to run all current validators before any filesystem/Task/queue side effect.
        try:
            req = DownloadRequest.model_validate(req.model_dump())
        except RequestValidationError:
            raise ValidationError(
                "下载参数不符合安全或协议约束", code="DOWNLOAD_ARGUMENTS_INVALID"
            ) from None
        config = get_download_config()
        validate_transport(
            req.source,
            method=req.download_method,
            accession=req.accession,
            links=req.links,
            cloud_provider=req.cloud_provider or "",
            object_uri=req.object_uri,
            allowed_schemes=config.validation.allowed_schemes,
        )
        ensure_download_available(req.source, len(req.links), config, get_settings())
        from cygnusx.infrastructure.download.policy import require_download_runtime

        require_download_runtime(req.source)
        directory = self._normalize_directory(req.target_directory)
        if not directory:
            directory = "downloads"

        if req.source == "cloud_storage":
            provider = self._normalize_cloud_provider(req.cloud_provider or "")
            object_uri = req.object_uri.strip()
            safe_label = self._safe_path_label(f"{provider}_{object_uri}", fallback="cloud_storage")
            label = safe_label
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
            label = safe_label
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
            label = safe_accession
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

        owner = (await self._db.execute(
            select(UserModel).where(UserModel.id == UUID(user_id)).with_for_update()
        )).scalar_one_or_none()
        if owner is None or owner.status != "active":
            raise NotFoundError("用户不可用")
        if project_id:
            project = (await self._db.execute(
                select(ProjectModel).where(
                    ProjectModel.id == project_id, ProjectModel.user_id == UUID(user_id)
                )
            )).scalar_one_or_none()
            if project is None:
                raise NotFoundError("项目不存在")
            parameters["project_id"] = str(project_id)
        digest = intent_digest(user_id, str(project_id or ""), parameters)
        key = (
            intent_digest(user_id, str(project_id or ""), {"download_request_key": req.request_key})
            if req.request_key else digest
        )
        existing = await self._repo.get_by_idempotency_key(key)
        if existing is None and not req.request_key:
            # A keyless retry also reuses an intent first submitted with an explicit key.
            row = (await self._db.execute(select(TaskModel).where(
                TaskModel.user_id == UUID(user_id), TaskModel.flow_id == DOWNLOAD_FLOW_ID,
                TaskModel.parameters["_download_reliability"]["version"].as_integer() == 1,
                TaskModel.parameters["_download_intent"].as_string() == digest,
            ).order_by(TaskModel.created_at.desc(), TaskModel.id).limit(1))).scalar_one_or_none()
            if row is not None:
                existing = await self._repo.get_by_id(row.id)
        if existing is None and req.request_key:
            # Keys used to join an active intent remain bound after it terminates.
            aliases = (await self._db.execute(select(TaskModel).where(
                TaskModel.user_id == UUID(user_id), TaskModel.flow_id == DOWNLOAD_FLOW_ID,
                TaskModel.parameters["_download_reliability"]["version"].as_integer() == 1,
                cast(TaskModel.parameters["_download_request_keys"], String).contains(key),
            ))).scalars().all()
            for row in aliases:
                if key in (row.parameters or {}).get("_download_request_keys", []):
                    existing = await self._repo.get_by_id(row.id)
                    break
        if existing is not None:
            if (existing.flow_id != DOWNLOAD_FLOW_ID or str(existing.user_id) != user_id
                or existing.parameters.get("_download_intent") != digest):
                raise ConflictError("同一请求键不能修改下载参数", code="DOWNLOAD_REQUEST_CONFLICT")
            return task_to_response(existing)
        active = (await self._db.execute(select(TaskModel).where(
            TaskModel.user_id == UUID(user_id), TaskModel.flow_id == DOWNLOAD_FLOW_ID,
            TaskModel.status.in_(["pending", "queued", "running"]),
        ))).scalars().all()
        for row in active:
            if (row.parameters or {}).get("_download_intent") == digest:
                if req.request_key:
                    keys = (row.parameters or {}).get("_download_request_keys", [])
                    if len(keys) >= config.reliability.max_request_keys:
                        raise ConflictError("下载请求键数量达到上限，请使用已有请求键",
                                            code="DOWNLOAD_REQUEST_KEYS_LIMIT")
                    row.parameters = {**row.parameters, "_download_request_keys": [*keys, key]}
                    await self._db.flush()
                existing = await self._repo.get_by_id(row.id)
                assert existing is not None
                return task_to_response(existing)
        parameters["_download_intent"] = digest
        parameters["_download_request_keys"] = [key] if req.request_key else []
        parameters["_download_reliability"] = {"version": 1, "dispatch": "QUEUED_DURABLE"}
        task_id = uuid4()
        work_dir = await self._make_work_dir(user_id, label, directory)
        # Survives SQL rollback as an attribution hint, never as execution approval.
        marker = Path(work_dir) / ".download-task.json"
        with marker.open("x", encoding="utf-8") as stream:
            json.dump({"version": 1, "task_id": str(task_id), "owner_id": user_id,
                       "intent_digest": digest}, stream)

        from cygnusx.application.services.file_service import ensure_directory_chain

        relative_work_dir = (
            Path(work_dir).relative_to(get_path_factory().user_root(user_id)).as_posix()
        )
        await ensure_directory_chain(self._db, UUID(user_id), relative_work_dir)

        # 创建任务聚合根（复用通用 Task，flow_id 标记为数据下载）
        task = await self._domain.submit(
            flow_id=DOWNLOAD_FLOW_ID,
            user_id=UUID(user_id),
            name=task_name,
            parameters=parameters,
            sample_count=0,
            idempotency_key=key,
            task_id=task_id,
        )
        task.work_dir = work_dir
        task = await self._repo.save(task)

        # The API transaction owns the commit. Publish only after that commit;
        # a queued row remains recoverable when the broker is unavailable.
        notify_after_commit(self._db.sync_session, task.id)

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
        d = directory.strip()
        if d.startswith("/") or ".." in d.split("/") or "\\" in d:
            raise ValidationError("下载目录必须位于当前用户根目录内")
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

    async def _make_work_dir(self, user_id: str, label: str, directory: str = "") -> str:
        """下载产物落在可读标签、UTC 时间与原子序号组成的独立子目录。

        默认 directory="downloads"，即顶层 downloads/；用户显式指定其它目录时按原样使用。
        """
        if self._backend.name != "local":
            raise ValidationError("下载工作目录需要受管本地存储")
        user_root = get_path_factory().user_root(user_id)
        if user_root.absolute() != user_root.resolve():
            raise ValidationError("下载用户目录含链接")
        user_root.mkdir(parents=True, exist_ok=True)
        fd = os.open(user_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in Path(directory).parts:
                with suppress(FileExistsError):
                    os.mkdir(part, dir_fd=fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            for sequence in range(1, 10000):
                name = f"{label}-{stamp}-{sequence}"
                try:
                    os.mkdir(name, dir_fd=fd)
                    return str(user_root / directory / name)
                except FileExistsError:
                    continue
            raise ValidationError("无法分配下载工作目录")
        finally:
            os.close(fd)
