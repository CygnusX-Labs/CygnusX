"""数据下载任务 — 调用外部二进制（EBIDownload）下载测序数据。

复用与 `run_snakemake` 一致的任务状态/日志/进度回写模式：
- `TaskDomainService` 推进状态 PENDING→RUNNING→SUCCESS/FAILED；
- `add_log` + `publish_task_log` 双写日志（DB + Redis Pub/Sub → WebSocket）；
- `BinaryExecutor` 经 `on_log`/`on_progress` 回调把 JSON 行实时推送、回写 progress。
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from celery import shared_task

from omichub.core.config import get_settings
from omichub.domain.task.value_objects import LogLevel, TaskStatus
from omichub.infrastructure.cache.pubsub import publish_task_log
from omichub.infrastructure.execution.base import ExecutionContext
from omichub.infrastructure.execution.registry import get_executor


@shared_task(name="omichub.infrastructure.celery_app.tasks.download.run_download")
def run_download(task_id: str) -> dict:
    """执行数据下载（外部二进制）。"""
    return asyncio.run(_execute_download(task_id))


async def _execute_download(task_id: str) -> dict:
    from omichub.domain.task.services import TaskDomainService
    from omichub.infrastructure.database.repositories.task_repository import (
        TaskRepositoryImpl,
    )
    from omichub.infrastructure.database.session import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = TaskRepositoryImpl(session)
        domain = TaskDomainService(repo)

        task_uuid = UUID(task_id)
        task = await repo.get_by_id(task_uuid)
        if task is None:
            return {"status": "failed", "message": f"任务 {task_id} 不存在"}

        params = task.parameters or {}

        async def _add_and_publish_log(level: LogLevel, message: str, source: str = "") -> None:
            await domain.add_log(task_uuid, level, message, source=source)
            await publish_task_log(
                task_id=task_id,
                level=level.value,
                message=message,
                source=source,
            )

        last_progress = -1.0

        async def _on_log(level: str, message: str, source: str = "binary") -> None:
            try:
                lvl = LogLevel(level)
            except ValueError:
                lvl = LogLevel.INFO
            await _add_and_publish_log(lvl, message, source=source)

        async def _on_progress(progress: float) -> None:
            nonlocal last_progress, task
            # 节流：进度变化 >=5% 才回写，避免高频 DB 写入
            if progress - last_progress < 0.05 and progress < 1.0:
                return
            last_progress = progress
            task.progress = progress
            await repo.save(task)
            await session.commit()
            await _add_and_publish_log(
                LogLevel.INFO, f"下载进度 {progress * 100:.0f}%", source="binary"
            )

        await _add_and_publish_log(LogLevel.INFO, "开始执行数据下载任务", source="celery")
        task = await domain.transition_status(task, TaskStatus.RUNNING)
        await session.commit()

        settings = get_settings()
        accession = str(params.get("accession", ""))
        method = str(params.get("download_method", "aws"))
        multithreads = int(params.get("multithreads", 4))
        aws_threads = int(params.get("aws_threads", 8))
        work_dir = task.work_dir or ""

        ctx = ExecutionContext(
            engine="binary",
            work_dir=work_dir,
            binary=settings.ebi_download_binary,
            binary_args=[
                "--yaml",
                settings.ebi_download_yaml,
                "--log-format",
                "json",
                "download",
                "-A",
                accession,
                "-o",
                work_dir,
                "-d",
                method,
                "-p",
                str(multithreads),
                "-t",
                str(aws_threads),
            ],
            on_log=_on_log,
            on_progress=_on_progress,
        )

        await _add_and_publish_log(
            LogLevel.INFO,
            f"调用 EBIDownload: accession={accession}, work_dir={work_dir}, method={method}",
            source="binary",
        )

        try:
            executor = get_executor("binary")
            result = await executor.execute(ctx)

            if result.status == "success":
                task.progress = 1.0
                task.result_path = work_dir
                await repo.save(task)
                task = await domain.transition_status(task, TaskStatus.SUCCESS)
                await _add_and_publish_log(LogLevel.INFO, "数据下载完成", source="binary")
                return_status = "success"
            else:
                task = await domain.transition_status(task, TaskStatus.FAILED)
                task.error_message = (result.stderr or result.stdout)[:2000]
                await repo.save(task)
                await _add_and_publish_log(
                    LogLevel.ERROR,
                    f"数据下载失败 (returncode={result.returncode})",
                    source="binary",
                )
                return_status = "failed"

            await session.commit()
            return {
                "status": return_status,
                "task_id": task_id,
                "returncode": result.returncode,
            }

        except Exception as exc:  # noqa: BLE001
            await _add_and_publish_log(LogLevel.ERROR, f"执行异常: {exc}", source="celery")
            task = await domain.transition_status(task, TaskStatus.FAILED)
            task.error_message = str(exc)[:2000]
            await repo.save(task)
            await session.commit()
            return {"status": "failed", "task_id": task_id, "error": str(exc)}
