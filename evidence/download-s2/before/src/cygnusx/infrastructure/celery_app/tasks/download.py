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
import re
from collections.abc import Awaitable
from datetime import datetime
from ftplib import FTP
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from uuid import UUID

from celery import shared_task
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.core.config import Settings, get_settings
from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.task.entities import Task
from cygnusx.domain.task.services import TaskDomainService
from cygnusx.domain.task.value_objects import LogLevel, TaskStatus
from cygnusx.infrastructure.cache.pubsub import publish_task_log
from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl
from cygnusx.infrastructure.execution.base import ExecutionContext
from cygnusx.infrastructure.execution.registry import get_executor
from cygnusx.tools.download.config import get_download_config


class DownloadLog(Protocol):
    def __call__(self, level: LogLevel, message: str, source: str = "") -> Awaitable[None]: ...


@shared_task(name="cygnusx.infrastructure.celery_app.tasks.download.run_download")  # type: ignore[untyped-decorator]
def run_download(task_id: str) -> dict[str, Any]:
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


_CLOUD_PROVIDER_LABELS = {
    "aliyun": "阿里云 OSS",
    "volc": "火山引擎 TOS",
    "huawei": "华为云 OBS",
}


def _cloud_binary_path(settings: Settings, provider: str) -> str:
    config = get_download_config()
    return {
        "aliyun": config.binaries.ossutil or settings.cloud_ossutil_binary,
        "volc": config.binaries.tosutil or settings.cloud_tosutil_binary,
        "huawei": config.binaries.obsutil or settings.cloud_obsutil_binary,
    }[provider]


def _build_cloud_storage_args(
    provider: str, object_uri: str, work_dir: str, recursive: bool
) -> list[str]:
    """构造云存储 CLI 参数，二进制路径由 ExecutionContext.binary 承载。"""
    if provider == "aliyun":
        args = ["cp", object_uri, work_dir, "--update", "--force", "--jobs", "5"]
        if recursive:
            args.append("--recursive")
        return args
    if provider == "volc":
        args = [
            "cp",
            object_uri,
            work_dir,
            "-u",
            "-j",
            "5",
            "--checkpoint",
            os.path.join(work_dir, ".checkpoint"),
        ]
        if recursive:
            args.append("-r")
        return args
    if provider == "huawei":
        args = [
            "cp",
            object_uri,
            work_dir,
            "-f",
            "-u",
            "-j",
            "5",
            "-parallel",
            "5",
            "-partSize",
            "5",
        ]
        if recursive:
            args.append("-r")
        return args
    raise ValueError(f"不支持的云存储提供商: {provider}")


def _parse_cloud_storage_progress(message: str) -> float | None:
    """从 ossutil/tosutil/obsutil 输出中提取通用百分比进度。"""
    match = re.search(r"(?<!\d)(100(?:\.0+)?|[1-9]?\d(?:\.\d+)?)\s*%", message)
    if not match:
        return None
    try:
        return max(0.0, min(1.0, float(match.group(1)) / 100.0))
    except ValueError:
        return None


async def _execute_download(task_id: str) -> dict[str, Any]:
    from cygnusx.domain.task.services import TaskDomainService
    from cygnusx.infrastructure.database.repositories.task_repository import (
        TaskRepositoryImpl,
    )
    from cygnusx.infrastructure.database.session import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = TaskRepositoryImpl(session)
        domain = TaskDomainService(repo)

        task_uuid = UUID(task_id)
        candidate = await repo.get_by_id(task_uuid)
        if candidate is None:
            return {"status": "failed", "message": f"任务 {task_id} 不存在"}

        task: Task = candidate
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

        try:
            await _prepare_download_registration(
                session, task_uuid, task.user_id, task.work_dir or ""
            )
            await session.commit()
            prepared_task = await repo.get_by_id(task_uuid)
            if prepared_task is not None:
                task.parameters = prepared_task.parameters
        except Exception as exc:
            task = await domain.transition_status(task, TaskStatus.FAILED)
            task.error_message = (
                f"下载产物需对账: {getattr(exc, 'code', 'DOWNLOAD_REGISTRATION_FAILED')}"
            )
            task.parameters = {
                **(task.parameters or {}),
                "_download_registration": {
                    "state": "RECONCILIATION_REQUIRED",
                    "scientific_ready": False,
                    "reason_code": getattr(exc, "code", "DOWNLOAD_REGISTRATION_FAILED"),
                },
            }
            await repo.save(task)
            await session.commit()
            return {
                "status": "failed",
                "task_id": task_id,
                "registration_state": "RECONCILIATION_REQUIRED",
            }

        source = str(params.get("source", "sra") or "sra")
        if source == "cloud_storage":
            return await _execute_cloud_storage_download(
                task_id=task_id,
                task_uuid=task_uuid,
                task=task,
                params=params,
                session=session,
                repo=repo,
                domain=domain,
                add_and_publish_log=_add_and_publish_log,
            )
        if source == "direct_link":
            return await _execute_direct_link_download(
                task_id=task_id,
                task_uuid=task_uuid,
                task=task,
                params=params,
                session=session,
                repo=repo,
                domain=domain,
                add_and_publish_log=_add_and_publish_log,
            )

        settings = get_settings()
        accession = str(params.get("accession", ""))
        method = str(params.get("download_method", "aws"))
        multithreads = int(params.get("multithreads", 4))
        aws_threads = int(params.get("aws_threads", 8))
        dry_run = bool(params.get("dry_run", False))
        work_dir = task.work_dir or ""

        # 为 progress API 分配动态端口
        from cygnusx.infrastructure.download.port_allocator import allocate_free_port

        progress_port = allocate_free_port()

        binary_args = [
            "--yaml",
            get_download_config().binaries.ebi_config or settings.ebi_download_yaml,
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
            binary=get_download_config().binaries.ebi or settings.ebi_download_binary,
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
                        1 for rid, sz in sizes.items() if sz > 0 and prev_sizes.get(rid) == sz
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
            from cygnusx.infrastructure.download.progress_crypto import (
                ProgressKeyTimeout,
                load_progress_key,
            )
            from cygnusx.infrastructure.download.progress_poller import ProgressPoller

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
            # Stop progress writers before committing registration metadata on the same Task.
            poll_cancel.set()
            poller_task.cancel()
            sampler.cancel()
            await asyncio.gather(sampler, poller_task, return_exceptions=True)

            files_ok = await _finalize_download_files(
                session,
                task_uuid,
                task.user_id,
                work_dir,
                str(params.get("target_directory", "") or ""),
                settings.storage_path,
                result.status == "success",
            )
            registered_task = await repo.get_by_id(task_uuid)
            if registered_task is not None:
                task.parameters = registered_task.parameters
            if result.status == "success" and files_ok:
                task.progress = 1.0
                task.result_path = work_dir
                await repo.save(task)
                task = await domain.transition_status(task, TaskStatus.SUCCESS)
                await _add_and_publish_log(LogLevel.INFO, "数据下载完成", source="binary")
                return_status = "success"
            else:
                task = await domain.transition_status(task, TaskStatus.FAILED)
                task.error_message = (
                    (result.stderr or result.stdout)[:2000]
                    if result.status != "success"
                    else "DOWNLOAD_REGISTRATION_RECONCILIATION_REQUIRED"
                )
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
                from cygnusx.infrastructure.cache.redis_client import get_redis

                r = get_redis()
                await r.delete(f"download_progress:{task_id}")
            except Exception:
                pass


async def _execute_cloud_storage_download(
    *,
    task_id: str,
    task_uuid: UUID,
    task: Task,
    params: dict[str, Any],
    session: AsyncSession,
    repo: TaskRepositoryImpl,
    domain: TaskDomainService,
    add_and_publish_log: DownloadLog,
) -> dict[str, Any]:
    """执行云存储对象下载，复用 Task 日志/进度/文件入库链路。"""
    settings = get_settings()
    provider = str(params.get("cloud_provider", ""))
    object_uri = str(params.get("object_uri", ""))
    recursive = bool(params.get("recursive", True))
    directory = str(params.get("target_directory", "") or "")
    work_dir = task.work_dir or ""
    label = _CLOUD_PROVIDER_LABELS.get(provider, provider)

    try:
        binary = _cloud_binary_path(settings, provider)
        binary_args = _build_cloud_storage_args(provider, object_uri, work_dir, recursive)
    except Exception as exc:  # noqa: BLE001
        task = await domain.transition_status(task, TaskStatus.FAILED)
        task.error_message = str(exc)[:2000]
        await repo.save(task)
        await add_and_publish_log(LogLevel.ERROR, f"云存储下载配置错误: {exc}", source="celery")
        await session.commit()
        return {"status": "failed", "task_id": task_id, "error": str(exc)}

    binary_exists = bool(binary) and await asyncio.to_thread(os.path.exists, binary)
    if not binary_exists:
        msg = f"{label} 下载工具未找到: {binary}"
        task = await domain.transition_status(task, TaskStatus.FAILED)
        task.error_message = msg
        await repo.save(task)
        await add_and_publish_log(LogLevel.ERROR, msg, source="celery")
        await session.commit()
        return {"status": "failed", "task_id": task_id, "error": msg}

    os.makedirs(work_dir, exist_ok=True)
    db_lock = asyncio.Lock()
    last_progress = -1.0

    async def _on_cloud_log(level: str, message: str, source: str = "binary") -> None:
        nonlocal last_progress, task
        parsed_progress = _parse_cloud_storage_progress(message)
        async with db_lock:
            if parsed_progress is not None:
                if parsed_progress - last_progress >= 0.02 or parsed_progress >= 1.0:
                    last_progress = parsed_progress
                    task.progress = parsed_progress
                    await repo.save(task)
                    await add_and_publish_log(
                        LogLevel.INFO,
                        f"云存储下载进度 {parsed_progress * 100:.0f}% ({label})",
                        source=source,
                    )
                    await session.commit()
                return
            try:
                lvl = LogLevel(level)
            except ValueError:
                lvl = LogLevel.INFO
            await add_and_publish_log(lvl, message[:1000], source=source)
            await session.commit()

    await add_and_publish_log(
        LogLevel.INFO,
        f"调用 {label} 下载工具: object_uri={object_uri}, work_dir={work_dir}, recursive={recursive}",
        source="binary",
    )
    await session.commit()

    ctx = ExecutionContext(
        engine="binary",
        work_dir=work_dir,
        binary=binary,
        binary_args=binary_args,
        on_log=_on_cloud_log,
    )

    try:
        executor = get_executor("binary")
        result = await executor.execute(ctx)

        files_ok = await _finalize_download_files(
            session,
            task_uuid,
            task.user_id,
            work_dir,
            directory,
            settings.storage_path,
            result.status == "success",
        )
        registered_task = await repo.get_by_id(task_uuid)
        if registered_task is not None:
            task.parameters = registered_task.parameters
        if result.status == "success" and files_ok:
            task.progress = 1.0
            task.result_path = work_dir
            await repo.save(task)
            task = await domain.transition_status(task, TaskStatus.SUCCESS)
            await add_and_publish_log(LogLevel.INFO, "云存储下载完成，文件已入库", source="binary")
            return_status = "success"
        else:
            task = await domain.transition_status(task, TaskStatus.FAILED)
            task.error_message = (
                (result.stderr or result.stdout)[:2000]
                if result.status != "success"
                else "DOWNLOAD_REGISTRATION_RECONCILIATION_REQUIRED"
            )
            await repo.save(task)
            await add_and_publish_log(
                LogLevel.ERROR,
                f"云存储下载失败 (returncode={result.returncode})",
                source="binary",
            )
            return_status = "failed"

        await session.commit()
        return {"status": return_status, "task_id": task_id, "returncode": result.returncode}
    except Exception as exc:  # noqa: BLE001
        await add_and_publish_log(LogLevel.ERROR, f"云存储下载执行异常: {exc}", source="celery")
        task = await domain.transition_status(task, TaskStatus.FAILED)
        task.error_message = str(exc)[:2000]
        await repo.save(task)
        await session.commit()
        return {"status": "failed", "task_id": task_id, "error": str(exc)}


def _build_direct_link_args(
    links: list[str], work_dir: str, threads: int, overwrite_policy: str
) -> list[str]:
    """构造 aria2c 直链参数；URL 作为独立参数传入，避免 shell 拼接注入。"""
    aria2 = get_download_config().aria2
    args = [
        "--dir",
        work_dir,
        "--continue=true",
        "--max-tries",
        str(aria2.max_tries),
        "--retry-wait",
        str(aria2.retry_wait),
        "--connect-timeout",
        str(aria2.connect_timeout),
        "--timeout",
        str(aria2.timeout),
        "--file-allocation",
        aria2.file_allocation,
        "--check-integrity",
        str(aria2.check_integrity).lower(),
        "--max-concurrent-downloads",
        str(aria2.max_concurrent_downloads),
        "--split",
        str(threads),
        "--max-connection-per-server",
        str(threads),
        "--ftp-reuse-connection",
        str(aria2.ftp_reuse_connection).lower(),
    ]
    if overwrite_policy == "overwrite":
        args.extend(["--allow-overwrite=true", "--auto-file-renaming=false"])
    elif overwrite_policy == "skip":
        args.extend(["--allow-overwrite=false", "--auto-file-renaming=false"])
    else:
        args.extend(["--allow-overwrite=false", "--auto-file-renaming=true"])
    return args + links


def _expand_ftp_directories(links: list[str], recursive: bool) -> list[str]:
    """展开以 / 结尾的匿名 FTP 目录；普通文件链接原样返回。"""
    if not recursive:
        return links
    expanded: list[str] = []
    for link in links:
        parsed = urlsplit(link)
        if parsed.scheme.lower() != "ftp" or not parsed.path.endswith("/"):
            expanded.append(link)
            continue
        ftp = FTP(parsed.hostname or "", timeout=30)
        try:
            ftp.login()
            root = unquote(parsed.path)
            files: list[str] = []

            def walk(path: str, ftp: FTP = ftp, files: list[str] = files) -> None:
                current = ftp.pwd()
                ftp.cwd(path)
                for name in ftp.nlst():
                    child = f"{path.rstrip('/')}/{name.rsplit('/', 1)[-1]}"
                    try:
                        ftp.cwd(child)
                    except Exception:
                        files.append(child)
                    else:
                        ftp.cwd(current)
                        walk(child)
                ftp.cwd(current)

            walk(root)
            for path in files:
                expanded.append(urlunsplit(("ftp", parsed.netloc, quote(path), "", "")))
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()
    return expanded


async def _execute_direct_link_download(
    *,
    task_id: str,
    task_uuid: UUID,
    task: Task,
    params: dict[str, Any],
    session: AsyncSession,
    repo: TaskRepositoryImpl,
    domain: TaskDomainService,
    add_and_publish_log: DownloadLog,
) -> dict[str, Any]:
    """使用 aria2c 下载 HTTP/HTTPS/FTP 直链，并复用文件入库链路。"""
    settings = get_settings()
    config = get_download_config()
    links = [str(link).strip() for link in params.get("links", []) if str(link).strip()]
    work_dir = task.work_dir or ""
    directory = str(params.get("target_directory", "") or "")
    threads = max(
        1,
        min(
            config.aria2.max_threads,
            int(params.get("download_threads", config.aria2.default_threads)),
        ),
    )
    overwrite_policy = str(params.get("overwrite_policy", "auto_rename"))
    recursive = bool(params.get("recursive", False))
    binary = config.binaries.aria2c or settings.direct_download_binary

    if not links:
        task = await domain.transition_status(task, TaskStatus.FAILED)
        task.error_message = "没有可下载的直链"
        await repo.save(task)
        await add_and_publish_log(LogLevel.ERROR, task.error_message, source="aria2c")
        await session.commit()
        return {"status": "failed", "task_id": task_id, "error": task.error_message}
    if not binary or not await asyncio.to_thread(os.path.exists, binary):
        msg = f"aria2c 下载工具未找到: {binary}"
        task = await domain.transition_status(task, TaskStatus.FAILED)
        task.error_message = msg
        await repo.save(task)
        await add_and_publish_log(LogLevel.ERROR, msg, source="aria2c")
        await session.commit()
        return {"status": "failed", "task_id": task_id, "error": msg}

    os.makedirs(work_dir, exist_ok=True)
    try:
        links = await asyncio.to_thread(_expand_ftp_directories, links, recursive)
    except Exception as exc:  # noqa: BLE001
        task = await domain.transition_status(task, TaskStatus.FAILED)
        task.error_message = f"FTP 目录解析失败: {exc}"[:2000]
        await repo.save(task)
        await add_and_publish_log(LogLevel.ERROR, task.error_message, source="aria2c")
        await session.commit()
        return {"status": "failed", "task_id": task_id, "error": task.error_message}
    if not links:
        task = await domain.transition_status(task, TaskStatus.FAILED)
        task.error_message = "FTP 目录中没有可下载文件"
        await repo.save(task)
        await add_and_publish_log(LogLevel.ERROR, task.error_message, source="aria2c")
        await session.commit()
        return {"status": "failed", "task_id": task_id, "error": task.error_message}
    last_progress = -1.0

    async def _on_direct_log(level: str, message: str, source: str = "aria2c") -> None:
        nonlocal last_progress, task
        parsed = _parse_cloud_storage_progress(message)
        if parsed is not None and (parsed - last_progress >= 0.02 or parsed >= 1.0):
            last_progress = parsed
            task.progress = parsed
            await repo.save(task)
            await add_and_publish_log(
                LogLevel.INFO, f"直链下载进度 {parsed * 100:.0f}%", source=source
            )
            await session.commit()
            return
        try:
            lvl = LogLevel(level)
        except ValueError:
            lvl = LogLevel.INFO
        await add_and_publish_log(lvl, message[:1000], source=source)
        await session.commit()

    await add_and_publish_log(
        LogLevel.INFO,
        f"调用 aria2c 下载 {len(links)} 个直链，线程 {threads}，策略 {overwrite_policy}",
        source="aria2c",
    )
    await session.commit()
    ctx = ExecutionContext(
        engine="binary",
        work_dir=work_dir,
        binary=binary,
        binary_args=_build_direct_link_args(links, work_dir, threads, overwrite_policy),
        on_log=_on_direct_log,
    )
    try:
        result = await get_executor("binary").execute(ctx)
        files_ok = await _finalize_download_files(
            session,
            task_uuid,
            task.user_id,
            work_dir,
            directory,
            settings.storage_path,
            result.status == "success",
        )
        registered_task = await repo.get_by_id(task_uuid)
        if registered_task is not None:
            task.parameters = registered_task.parameters
        if result.status == "success" and files_ok:
            task.progress = 1.0
            task.result_path = work_dir
            await repo.save(task)
            task = await domain.transition_status(task, TaskStatus.SUCCESS)
            await add_and_publish_log(LogLevel.INFO, "直链下载完成，文件已入库", source="aria2c")
            status = "success"
        else:
            task = await domain.transition_status(task, TaskStatus.FAILED)
            task.error_message = (
                (result.stderr or result.stdout)[:2000]
                if result.status != "success"
                else "DOWNLOAD_REGISTRATION_RECONCILIATION_REQUIRED"
            )
            await repo.save(task)
            await add_and_publish_log(LogLevel.ERROR, "直链下载失败", source="aria2c")
            status = "failed"
        await session.commit()
        return {"status": status, "task_id": task_id, "returncode": result.returncode}
    except Exception as exc:  # noqa: BLE001
        task = await domain.transition_status(task, TaskStatus.FAILED)
        task.error_message = str(exc)[:2000]
        await repo.save(task)
        await add_and_publish_log(LogLevel.ERROR, f"直链下载执行异常: {exc}", source="aria2c")
        await session.commit()
        return {"status": "failed", "task_id": task_id, "error": str(exc)}


async def _prepare_download_registration(
    session: AsyncSession, task_id: UUID, user_id: UUID, work_dir: str
) -> None:
    """Persist a pre-transfer inventory; unknown old files are never claimed by this task."""
    from cygnusx.infrastructure.database.models.file import FileRecordModel
    from cygnusx.infrastructure.database.models.task import TaskModel
    from cygnusx.infrastructure.download.outputs import (
        controlled_paths,
        inspect_output,
        is_control_file,
    )
    from cygnusx.infrastructure.storage import get_path_factory, get_storage_backend

    if get_storage_backend().name != "local":
        raise ValidationError("下载文件登记仅支持受管本地存储", code="DOWNLOAD_STORAGE_UNVERIFIED")
    task = await session.get(TaskModel, task_id)
    if task is None or task.user_id != user_id or task.work_dir != work_dir:
        raise ValidationError("下载登记任务上下文不匹配", code="DOWNLOAD_TASK_MISMATCH")
    factory = get_path_factory()
    owner_root = factory.user_root(str(user_id)).absolute()
    paths = await asyncio.to_thread(
        controlled_paths,
        await asyncio.to_thread(Path(work_dir).absolute),
        owner_root,
        get_download_config().validation.max_registration_entries,
    )
    duplicate = await session.scalar(
        select(TaskModel.id).where(TaskModel.work_dir == work_dir, TaskModel.id != task_id).limit(1)
    )
    if duplicate is not None:
        raise ValidationError(
            "下载目录被其他任务引用，请人工对账", code="DOWNLOAD_DIRECTORY_SHARED"
        )
    # A shared/old work directory must not be overwritten and then claimed after transfer.
    for path in paths:
        if is_control_file(path, Path(work_dir)):
            continue
        record = (
            await session.execute(
                select(FileRecordModel).where(
                    FileRecordModel.storage_path == path.relative_to(factory.data_root).as_posix()
                )
            )
        ).scalar_one_or_none()
        if (
            record is None
            or record.task_id != task_id
            or record.user_id != user_id
            or record.source != "download"
            or not record.checksum
        ):
            raise ValidationError("下载前已有未归属当前任务的文件", code="DOWNLOAD_LEGACY_UNLINKED")
        output = await asyncio.to_thread(
            inspect_output,
            path,
            owner_root,
            get_download_config().validation.max_registration_bytes,
        )
        if record.checksum != output.sha256 or record.size != output.size:
            raise ValidationError("下载前已有文件内容变化", code="DOWNLOAD_RECORD_CONFLICT")
    if "_download_output_baseline" not in (task.parameters or {}):
        task.parameters = {
            **(task.parameters or {}),
            "_download_output_baseline": [p.relative_to(Path(work_dir)).as_posix() for p in paths],
        }
        await session.flush()


async def _register_downloaded_files(
    *,
    session: AsyncSession,
    user_id: UUID,
    task_id: UUID,
    work_dir: str,
    directory: str,
    storage_root: str,
    complete: bool = True,
) -> dict[str, Any]:
    """Register this task's bounded, verified outputs through the existing FileRegistry.

    Registration is a savepoint: no partial SQL/quota commit if one file fails.
    Legacy/unrelated same-path records are not relinked. The caller owns commit.
    """
    from cygnusx.application.services.file_service import (
        canonical_original_name,
        ensure_directory_chain,
    )
    from cygnusx.domain.file.value_objects import FileSource
    from cygnusx.infrastructure.database.models.file import FileRecordModel
    from cygnusx.infrastructure.database.models.task import TaskModel
    from cygnusx.infrastructure.database.models.user import UserModel
    from cygnusx.infrastructure.download.outputs import (
        controlled_paths,
        inspect_output,
        is_control_file,
    )
    from cygnusx.infrastructure.storage import get_path_factory, get_storage_backend
    from cygnusx.infrastructure.storage.file_registry import FileRegistry

    factory = get_path_factory()
    root = factory.data_root.absolute()
    owner_root = factory.user_root(str(user_id)).absolute()
    work = await asyncio.to_thread(Path(work_dir).absolute)
    if await asyncio.to_thread(root.resolve) != await asyncio.to_thread(Path(storage_root).resolve):
        raise ValidationError("下载存储根与注册器不一致", code="DOWNLOAD_STORAGE_MISMATCH")
    task = await session.get(TaskModel, task_id)
    if (
        task is None
        or task.user_id != user_id
        or task.work_dir != work_dir
        or task.flow_id != "ebi_download"
    ):
        raise ValidationError("下载登记任务不匹配", code="DOWNLOAD_TASK_MISMATCH")
    baseline = (task.parameters or {}).get("_download_output_baseline")
    if not isinstance(baseline, list) or any(not isinstance(p, str) for p in baseline):
        raise ValidationError("缺少下载前文件清单，请对账", code="DOWNLOAD_BASELINE_MISSING")
    limits = get_download_config().validation
    paths = await asyncio.to_thread(
        controlled_paths, work, owner_root, limits.max_registration_entries
    )
    candidates = [p for p in paths if not is_control_file(p, work)]
    # aria2 sidecar identifies an incomplete payload even when the payload looks ordinary.
    incomplete = await asyncio.to_thread(
        lambda: [p for p in candidates if p.with_name(p.name + ".aria2").exists()]
    )
    candidates = [p for p in candidates if p not in incomplete]
    if len(candidates) > limits.max_registration_files:
        raise ValidationError("下载文件数量超过登记预算", code="DOWNLOAD_REGISTRATION_LIMIT")
    if complete and (not candidates or incomplete):
        raise ValidationError("成功下载没有完整产物", code="DOWNLOAD_OUTPUT_INCOMPLETE")
    outputs = []
    total = 0
    for path in candidates:
        output = await asyncio.to_thread(
            inspect_output, path, owner_root, limits.max_registration_bytes - total
        )
        total += output.size
        outputs.append(output)
    registry = FileRegistry(session, path_factory=factory, backend=get_storage_backend())
    ids: list[str] = []
    new_size = 0
    async with session.begin_nested():
        user = (
            await session.execute(
                select(UserModel)
                .where(UserModel.id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        duplicate = await session.scalar(
            select(TaskModel.id)
            .where(TaskModel.work_dir == work_dir, TaskModel.id != task_id)
            .limit(1)
        )
        if duplicate is not None:
            raise ValidationError("下载目录有其他任务，需对账", code="DOWNLOAD_DIRECTORY_SHARED")
        for output in outputs:
            rel = output.path.relative_to(root).as_posix()
            existing = (
                (
                    await session.execute(
                        select(FileRecordModel).where(FileRecordModel.storage_path == rel)
                    )
                )
                .scalars()
                .all()
            )
            if existing:
                if len(existing) != 1:
                    raise ValidationError("同路径有多个文件记录", code="DOWNLOAD_RECORD_CONFLICT")
                record = existing[0]
                if (
                    record.user_id != user_id
                    or record.task_id != task_id
                    or record.source != FileSource.DOWNLOAD.value
                    or record.checksum != output.sha256
                    or record.size != output.size
                    or record.status != "active"
                    or record.lifecycle_status != "active"
                    or record.owner_scope != "personal"
                    or record.team_id is not None
                ):
                    raise ValidationError(
                        "文件归属或内容需人工对账", code="DOWNLOAD_RECORD_CONFLICT"
                    )
            else:
                if output.path.relative_to(work).as_posix() in baseline:
                    raise ValidationError(
                        "下载前已存在的文件不可自动认领", code="DOWNLOAD_LEGACY_UNLINKED"
                    )
                logical_dir = output.path.parent.relative_to(owner_root).as_posix()
                await ensure_directory_chain(session, user_id, logical_dir)
                record = await registry.register(
                    user_id,
                    output.path,
                    source=FileSource.DOWNLOAD,
                    task_id=task_id,
                    checksum=output.sha256,
                    directory=logical_dir,
                    display_name=canonical_original_name(output.path.name),
                )
                if record.size != output.size or record.task_id != task_id:
                    raise ValidationError("下载登记期间产物变化", code="DOWNLOAD_OUTPUT_CHANGED")
                new_size += output.size
            verified = await asyncio.to_thread(
                inspect_output,
                output.path,
                owner_root,
                limits.max_registration_bytes,
            )
            if verified != output:
                raise ValidationError("登记期间文件内容变化", code="DOWNLOAD_OUTPUT_CHANGED")
            ids.append(str(record.id))
        if user.used_storage + new_size > user.storage_quota:
            raise ValidationError("下载登记超过用户配额", code="QUOTA_EXCEEDED")
        if new_size:
            # Same transaction as FileRegistry; the legacy repository helper commits early.
            await session.execute(
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(used_storage=UserModel.used_storage + new_size)
            )
        summary = {
            "state": "FILES_REGISTERED"
            if complete
            else ("PARTIAL" if ids else "RECONCILIATION_REQUIRED"),
            "file_ids": ids,
            "file_count": len(ids),
            "bytes": total,
            "new_bytes": new_size,
            "excluded_entries": len(paths) - len(candidates),
            "scientific_ready": False,
        }
        task.parameters = {**task.parameters, "_download_registration": summary}
        await session.flush()
    return summary


async def _finalize_download_files(
    session: AsyncSession,
    task_id: UUID,
    user_id: UUID,
    work_dir: str,
    directory: str,
    storage_root: str,
    complete: bool,
) -> bool:
    """Persist a recovery projection without converting a registration failure into success."""
    from cygnusx.infrastructure.database.models.task import TaskModel

    try:
        await _register_downloaded_files(
            session=session,
            task_id=task_id,
            user_id=user_id,
            work_dir=work_dir,
            directory=directory,
            storage_root=storage_root,
            complete=complete,
        )
    except Exception as exc:
        task = await session.get(TaskModel, task_id)
        if task is not None:
            task.parameters = {
                **(task.parameters or {}),
                "_download_registration": {
                    "state": "RECONCILIATION_REQUIRED",
                    "scientific_ready": False,
                    "reason_code": getattr(exc, "code", "DOWNLOAD_REGISTRATION_FAILED"),
                },
            }
            await session.flush()
        return False
    return complete
