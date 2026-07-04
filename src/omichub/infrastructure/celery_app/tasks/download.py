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
        dry_run = bool(params.get("dry_run", False))
        work_dir = task.work_dir or ""

        # 为 progress API 分配动态端口
        from omichub.infrastructure.download.port_allocator import allocate_free_port

        progress_port = allocate_free_port()

        binary_args = [
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
            "--progress-port",
            str(progress_port),
            "--write-progress-key",
        ]
        if dry_run:
            binary_args.append("--dry-run")

        ctx = ExecutionContext(
            engine="binary",
            work_dir=work_dir,
            binary=settings.ebi_download_binary,
            binary_args=binary_args,
            on_log=_on_log,
            on_progress=_on_progress,
        )

        await _add_and_publish_log(
            LogLevel.INFO,
            f"调用 EBIDownload: accession={accession}, work_dir={work_dir}, method={method}",
            source="binary",
        )

        poller_active = False

        async def _progress_loop() -> None:
            """后台采样：按已下载完成文件数估算进度（仅作为 progress API 不可用时的回退）。

            当 ProgressPoller 正常工作时（poller_active=True），磁盘采样器不再写 task.progress，
            避免粗糙的文件完成计数覆盖精确的 per-run 百分比。仅保留日志输出用于调试。
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
                        msg = f"已下载 {done}/{total} 文件，共 {total_bytes / (1024**3):.1f} GB"
                        if not poller_active:
                            progress = min(0.99, done / total)
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

        # Progress API 轮询器：从 EBIDownload HTTP 端点拉取解密后的逐 run 进度写入 Redis
        poll_cancel = asyncio.Event()

        async def _progress_poll() -> None:
            """轮询 EBIDownload progress API → 解密 → 写 Redis。"""
            from omichub.infrastructure.download.progress_crypto import (
                ProgressKeyTimeout,
                load_progress_key,
            )
            from omichub.infrastructure.download.progress_poller import ProgressPoller

            try:
                key = await asyncio.to_thread(load_progress_key, work_dir)
            except ProgressKeyTimeout:
                await _add_and_publish_log(
                    LogLevel.WARNING,
                    "progress.key 超时未出现，progress API 不可用，回退到磁盘采样",
                    source="poller",
                )
                return
            except Exception:
                return

            last_poller_progress = -1.0

            async def _on_overall_progress(overall: float) -> None:
                nonlocal last_poller_progress, poller_active
                poller_active = True
                if overall - last_poller_progress < 0.05 and overall < 1.0:
                    return
                last_poller_progress = overall
                async with session_factory() as s:
                    r = TaskRepositoryImpl(s)
                    t = await r.get_by_id(task_uuid)
                    if t is not None:
                        t.progress = overall
                        await r.save(t)
                        await s.commit()

            poller = ProgressPoller(
                task_id=task_id,
                port=progress_port,
                key=key,
                on_overall_progress=_on_overall_progress,
            )
            await poller.run(cancel_event=poll_cancel)

        poller_task = asyncio.create_task(_progress_poll())

        try:
            executor = get_executor("binary")
            result = await executor.execute(ctx)

            if result.status == "success":
                task.progress = 1.0
                task.result_path = work_dir
                await repo.save(task)
                # 下载产物入库为 FileRecord，directory=target_directory，使文件出现在数据管理
                directory = str(params.get("target_directory", "") or "")
                await _register_downloaded_files(
                    session=session,
                    user_id=task.user_id,
                    work_dir=work_dir,
                    directory=directory,
                    storage_root=settings.storage_path,
                )
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
            poll_cancel.set()
            poller_task.cancel()
            sampler.cancel()
            await asyncio.gather(sampler, poller_task, return_exceptions=True)
            # 清理 Redis 进度缓存
            try:
                from omichub.infrastructure.cache.redis_client import get_redis
                r = get_redis()
                await r.delete(f"download_progress:{task_id}")
            except Exception:
                pass


async def _register_downloaded_files(
    *,
    session,
    user_id,
    work_dir: str,
    directory: str,
    storage_root: str,
) -> None:
    """下载产物入库为 FileRecord，并在 user_directories 登记 accession 子文件夹。

    扫描 work_dir 下的 .sra/.fastq.gz 等文件，每个 FileRecord 的 storage_path 为相对
    storage_root 的路径。directory 字段（数据管理页的逻辑归属）按以下规则：
      - target_directory 为空 → ``raw_data/{accession}``（与物理落盘 raw_data/{accession}/ 一致）
      - target_directory 非空 → ``{target_directory}/{accession}``
    并自动创建缺失的 Directory 记录（含父级），使文件以 accession 文件夹形式出现在数据管理页。
    幂等：同 storage_path 的 FileRecord 已存在则跳过（且不计配额）；Directory 已存在则跳过。
    新增文件累加进用户 used_storage。
    """
    import uuid as _uuid
    from pathlib import Path

    from sqlalchemy import select

    from omichub.application.services.file_service import ensure_directory_chain
    from omichub.domain.file.entities import DataFile
    from omichub.domain.file.value_objects import FileType
    from omichub.infrastructure.database.models.file import FileRecordModel
    from omichub.infrastructure.database.repositories.file_repository import (
        FileRepositoryImpl,
    )
    from omichub.infrastructure.database.repositories.user_repository import (
        SqlAlchemyUserRepository,
    )

    work_path = Path(work_dir)
    root_path = Path(storage_root)
    if not work_path.exists():
        return

    # 规整 target_directory
    d = (directory or "").strip().strip("/")
    parts = [p for p in d.split("/") if p not in ("", ".", "..")]
    directory_norm = "/".join(parts)

    # accession = work_dir 末段（_make_work_dir 以 safe_acc 命名该目录）
    accession = work_path.name
    logical_dir = (
        f"{directory_norm}/{accession}" if directory_norm else f"raw_data/{accession}"
    )

    # 确保 Directory 记录链存在（含父级），使数据管理页目录树能展示该 accession 文件夹
    await ensure_directory_chain(session, user_id, logical_dir)

    # 下载产物类型识别
    def _ftype(name: str) -> FileType:
        n = name.lower()
        if n.endswith((".fastq", ".fastq.gz", ".fq", ".fq.gz")):
            return FileType.FASTQ
        if n.endswith(".sra"):
            return FileType.OTHER  # SRA 原始格式，转 fastq 后才是 FASTQ
        if n.endswith(".bam"):
            return FileType.BAM
        return FileType.OTHER

    new_size = 0
    for f in work_path.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = str(f.relative_to(root_path))
        except ValueError:
            continue
        # 幂等：同 storage_path 已存在则跳过（不重复计配额）
        exists = await session.scalar(
            select(FileRecordModel.id).where(FileRecordModel.storage_path == rel)
        )
        if exists:
            continue
        size = f.stat().st_size
        record = DataFile(
            id=_uuid.uuid4(),
            user_id=user_id,
            path=rel,
            original_name=f.name,
            size=size,
            checksum="",
            file_type=_ftype(f.name),
            status="active",
            directory=logical_dir,
        )
        await FileRepositoryImpl(session).save(record)
        new_size += size

    # 新增产物累加进配额（与上传 merge 一致：原子累加并提交）
    if new_size > 0:
        await SqlAlchemyUserRepository(session).add_used_storage(user_id, new_size)
