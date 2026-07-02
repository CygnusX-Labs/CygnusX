"""分析任务 - Snakemake 工作流执行"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

from celery import shared_task

from omichub.domain.task.value_objects import LogLevel, TaskStatus
from omichub.infrastructure.cache.pubsub import publish_task_log
from omichub.infrastructure.execution.local import LocalSnakemakeExecutor


@shared_task(name="omichub.infrastructure.celery_app.tasks.analysis.run_snakemake")
def run_snakemake(
    snakefile: str,
    task_id: str,
    config_file: str = "",
    config_file_param: str = "analysisyaml",
    work_dir: str = "",
    cores: int = 4,
) -> dict:
    """执行 Snakemake 工作流

    本地模式: 通过 subprocess 调用 Snakemake CLI；
    远程模式: 通过 HTTP 调用远程 Executor（后续扩展）。
    """
    return asyncio.run(
        _execute_snakemake(
            snakefile=snakefile,
            task_id=task_id,
            config_file=config_file,
            config_file_param=config_file_param,
            work_dir=work_dir,
            cores=cores,
        )
    )


async def _execute_snakemake(
    snakefile: str,
    task_id: str,
    config_file: str,
    config_file_param: str,
    work_dir: str,
    cores: int,
) -> dict:
    """异步执行 Snakemake 并更新任务状态/日志。"""
    from omichub.infrastructure.database.repositories.task_repository import (
        TaskRepositoryImpl,
    )
    from omichub.infrastructure.database.session import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = TaskRepositoryImpl(session)
        from omichub.domain.task.services import TaskDomainService

        domain = TaskDomainService(repo)

        task_uuid = UUID(task_id)
        task = await repo.get_by_id(task_uuid)
        if task is None:
            return {"status": "failed", "message": f"任务 {task_id} 不存在"}

        async def _add_and_publish_log(level: LogLevel, message: str, source: str = "") -> None:
            await domain.add_log(task_uuid, level, message, source=source)
            await publish_task_log(
                task_id=task_id,
                level=level.value,
                message=message,
                source=source,
            )

        # 推送开始日志
        await _add_and_publish_log(LogLevel.INFO, "开始执行 Snakemake 分析任务", source="celery")

        # 推进到 RUNNING
        task = await domain.transition_status(task, TaskStatus.RUNNING)
        await session.commit()
        await _add_and_publish_log(
            LogLevel.INFO,
            f"调用 Snakemake: snakefile={snakefile}, work_dir={work_dir}",
            source="snakemake",
        )

        try:
            executor = LocalSnakemakeExecutor()
            result = await executor._execute(
                snakefile=snakefile,
                work_dir=work_dir,
                cores=cores,
                config_file=config_file,
                config_file_param=config_file_param,
            )

            # 记录 stdout / stderr 摘要
            for line in (result.get("stdout") or "").splitlines()[-200:]:
                if line.strip():
                    await _add_and_publish_log(LogLevel.INFO, line, source="snakemake")
            for line in (result.get("stderr") or "").splitlines()[-200:]:
                if line.strip():
                    await _add_and_publish_log(LogLevel.WARNING, line, source="snakemake")

            if result.get("status") == "success":
                task = await domain.transition_status(task, TaskStatus.SUCCESS)
                await _add_and_publish_log(LogLevel.INFO, "Snakemake 执行完成", source="snakemake")
                return_status = "success"
            else:
                task = await domain.transition_status(task, TaskStatus.FAILED)
                task.error_message = result.get("stderr", "")[:2000]
                await repo.save(task)
                await _add_and_publish_log(
                    LogLevel.ERROR,
                    f"Snakemake 执行失败 (returncode={result.get('returncode')})",
                    source="snakemake",
                )
                return_status = "failed"

            # 集成点#3: 任务完成时结算饼干 (多退少补)
            pre_deducted = task.parameters.get("_cookie_pre_deducted", 0) if task.parameters else 0
            if pre_deducted > 0:
                from omichub.application.services.task_cookie_consumer import (
                    TaskCookieConsumer,
                )

                consumer = TaskCookieConsumer(session)
                await consumer.on_complete(
                    user_id=task.user_id,
                    task_id=str(task.id),
                    flow_id=task.flow_id,
                    pre_deducted=Decimal(str(pre_deducted)),
                    sample_count=task.sample_count,
                    comparison_count=len((task.parameters or {}).get("comparisons", [])),
                    resource_cores=cores,
                )

            await session.commit()
            return {
                "status": return_status,
                "task_id": task_id,
                "returncode": result.get("returncode"),
            }

        except Exception as exc:  # noqa: BLE001
            await _add_and_publish_log(LogLevel.ERROR, f"执行异常: {exc}", source="celery")
            task = await domain.transition_status(task, TaskStatus.FAILED)
            task.error_message = str(exc)[:2000]
            await repo.save(task)
            await session.commit()
            return {"status": "failed", "task_id": task_id, "error": str(exc)}


@shared_task(name="omichub.infrastructure.celery_app.tasks.analysis.cleanup_expired")
def cleanup_expired() -> dict:
    """[已迁移] 过期清理逻辑移至 tasks.storage.cleanup_expired。

    保留任务名仅为向后兼容旧 beat 配置；实际由 storage.cleanup_expired 承担。
    新部署的 beat 已直接指向 storage.cleanup_expired。
    """
    from omichub.infrastructure.celery_app.tasks.storage import cleanup_expired as _real

    return _real()  # shared_task 直接调用即在进程内执行其函数体
