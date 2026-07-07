"""Celery 任务日志增强

为每个 Celery 任务自动创建独立的文本日志文件，实现「DB + WebSocket 实时流」之外的
文本备份，便于在宿主机上按任务 ID 直接 tail/grep 排查。

日志路径：/app/logs/celery/tasks/{task_id}.log
（通过 docker-compose.worker.yml 挂载到 /data/omichub/logs/celery/tasks）
"""

import os
from pathlib import Path

from celery import Task
from loguru import logger

TASK_LOG_DIR = Path(os.getenv("OMICHUB_CELERY_LOG_DIR", "/app/logs/celery/tasks"))


def _ensure_task_log_dir() -> None:
    """确保任务日志目录存在。"""
    TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)


class LoggedTask(Task):
    """Celery Task 基类：为每个任务自动创建独立日志文件。

    用法：在 Celery 应用实例中设置 task_cls=LoggedTask，所有 @shared_task
    自动继承此行为，无需逐个 task 修改。
    """

    def __call__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        task_id = self.request.id or "no-id"
        _ensure_task_log_dir()
        sink_path = TASK_LOG_DIR / f"{task_id}.log"

        handler_id = logger.add(
            sink_path,
            level="INFO",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "{name}:{function}:{line} | {message}"
            ),
            enqueue=True,
        )

        try:
            logger.info(f"Task {task_id} started: {self.name}")
            return self.run(*args, **kwargs)
        finally:
            logger.info(f"Task {task_id} finished: {self.name}")
            logger.remove(handler_id)
