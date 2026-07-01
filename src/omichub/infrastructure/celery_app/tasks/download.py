"""数据下载任务 — 调用外部二进制（EBIDownload）下载测序数据。

复用与 `run_snakemake` 一致的任务状态/日志/进度回写模式：
- `TaskDomainService` 推进状态 PENDING→RUNNING→SUCCESS/FAILED；
- `add_log` + `publish_task_log` 双写日志（DB + Redis Pub/Sub → WebSocket）；
- `BinaryExecutor` 经 `on_log`/`on_progress` 回调把 JSON 行实时推送、回写 progress。
"""

from __future__ import annotations

import asyncio
import glob
import os
from datetime import datetime
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


def _count_metadata_records(work_dir: str) -> int:
    """从 ENA 元数据 TSV 统计数据记录数（= 应下载文件数）。

    TSV 第一行为 `# Project Accession: ...` 注释，第二行为列头，其后为数据行。
    EBIDownload 在下载开始前即写好该文件，故可在采样时读出"总文件数"。
    文件名由二进制决定，glob 匹配 `*_metadata/ena_metadata*.tsv`，不硬编码。
    """
    candidates = glob.glob(os.path.join(work_dir, "*_metadata", "ena_metadata*.tsv"))
    if not candidates:
        return 0
    non_comment = 0
    try:
        with open(candidates[0], encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                non_comment += 1
    except OSError:
        return 0
    # 减去列头行
    return max(0, non_comment - 1)


def _scan_sra_files(work_dir: str) -> tuple[dict[str, int], int]:
    """扫描 work_dir 下 *.sra 文件，返回 {run_id: 字节数} 与总字节数。"""
    sizes: dict[str, int] = {}
    total_bytes = 0
    for path in glob.glob(os.path.join(work_dir, "*.sra")):
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        run_id = os.path.splitext(os.path.basename(path))[0]
        sizes[run_id] = size
        total_bytes += size
    return sizes, total_bytes


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
        # BinaryExecutor 用 asyncio.gather 并发排空 stdout/stderr，_on_log/_on_progress 会并发触发；
        # 二者共用同一 session，并发写库会触发 asyncpg "another operation is in progress"。
        # 用锁序列化回调里的 DB 操作（主流程写库在 await execute() 前后、不与之并发，无需加锁）。
        db_lock = asyncio.Lock()

        async def _on_log(level: str, message: str, source: str = "binary") -> None:
            try:
                lvl = LogLevel(level)
            except ValueError:
                lvl = LogLevel.INFO
            async with db_lock:
                await _add_and_publish_log(lvl, message, source=source)
                # 提交以释放行锁：进度采样器用独立 session 写 progress，
                # 需主事务不长期持锁，否则采样器的 UPDATE 会被阻塞至下载结束
                await session.commit()

        async def _on_progress(progress: float) -> None:
            nonlocal last_progress, task
            # 节流：进度变化 >=5% 才回写，避免高频 DB 写入
            if progress - last_progress < 0.05 and progress < 1.0:
                return
            last_progress = progress
            async with db_lock:
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

        async def _progress_loop() -> None:
            """后台采样：按已下载完成文件数估算进度。

            EBIDownload 下载阶段不输出进度日志，on_progress 不触发，故独立定时扫描磁盘：
            - 总数 = ENA 元数据记录数（_count_metadata_records）；
            - 完成 = *.sra 文件大小连续两次扫描不变且 >0（需 2 次采样确认稳定）；
            - progress = done / total（≤0.99，绝不置 1.0，主流程 SUCCESS 时才设）。

            用独立 session 写进度，与 binary 回调（_on_log/_on_progress）解耦：不共用 db_lock，
            避免某个 binary 回调卡在锁内时采样被饿死（曾导致进度只写一次后冻结 25 分钟）。
            """
            total = _count_metadata_records(work_dir)
            prev_sizes: dict[str, int] = {}
            last_done = -1
            while True:
                try:
                    sizes, total_bytes = _scan_sra_files(work_dir)
                    done = sum(
                        1
                        for rid, sz in sizes.items()
                        if sz > 0 and prev_sizes.get(rid) == sz
                    )
                    if total > 0 and done != last_done:
                        progress = min(0.99, done / total)
                        msg = f"已下载 {done}/{total} 文件，共 {total_bytes / (1024**3):.1f} GB"
                        # 独立 session：短事务写 progress + 日志，不与 binary 回调争用 db_lock/行锁
                        async with session_factory() as s:
                            r = TaskRepositoryImpl(s)
                            t = await r.get_by_id(task_uuid)
                            if t is not None:
                                t.progress = progress
                                await r.save(t)
                                await r.append_log(
                                    task_uuid,
                                    {
                                        "timestamp": datetime.now().isoformat(),
                                        "level": LogLevel.INFO.value,
                                        "message": msg,
                                        "source": "sampler",
                                    },
                                )
                                await s.commit()
                        await publish_task_log(
                            task_id=task_id,
                            level=LogLevel.INFO.value,
                            message=msg,
                            source="sampler",
                        )
                        last_done = done
                    prev_sizes = sizes
                except Exception:  # noqa: BLE001 — 采样绝不能拖垮主任务
                    pass
                await asyncio.sleep(5)

        # 持有强引用防 GC；execute() 返回/抛错后必须取消采样并 await 抑制 CancelledError
        sampler = asyncio.create_task(_progress_loop())
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
        finally:
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
