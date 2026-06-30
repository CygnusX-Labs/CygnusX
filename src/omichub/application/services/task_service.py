"""Task 应用服务 — 用例编排：提交、查询、列表。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.task import (
    TaskListResponse,
    TaskResponse,
    TaskSubmitRequest,
    task_to_response,
)
from omichub.application.services.flow_service import FlowService
from omichub.core.config import get_settings
from omichub.core.exceptions import NotFoundError, ValidationError
from omichub.domain.task.services import TaskDomainService
from omichub.domain.task.value_objects import TaskStatus
from omichub.infrastructure.celery_app.tasks.analysis import run_snakemake
from omichub.infrastructure.database.repositories.task_repository import (
    TaskRepositoryImpl,
)
from omichub.infrastructure.execution.generic_builder import GenericFlowBuilder
from omichub.infrastructure.execution.local import LocalSnakemakeExecutor


class TaskService:
    """任务应用服务"""

    def __init__(
        self,
        db: AsyncSession,
        flow_service: FlowService | None = None,
    ):
        self._db = db
        self._repo = TaskRepositoryImpl(db)
        self._domain = TaskDomainService(self._repo)
        self._flow_service = flow_service or FlowService()
        self._settings = get_settings()

    async def submit(self, user_id: str, req: TaskSubmitRequest) -> TaskResponse:
        """提交分析任务。

        流程：
        1. 校验流程定义存在；
        2. 锁定参数快照；
        3. 通过通用构建器生成流程输入文件；
        4. 创建任务聚合根并持久化；
        5. 投递 Celery 异步任务；
        6. 将任务状态推进为 QUEUED。
        """
        flow_config = self._flow_service.get_flow_config(req.flow_id)
        flow_detail = self._flow_service.get_flow(req.flow_id)

        work_dir = self._make_work_dir(req.flow_id, user_id)

        # 参数快照：复制一份不可变的提交时参数
        parameter_snapshot = dict(req.parameters)

        # 通用构建器生成底层流程输入文件
        builder = GenericFlowBuilder()
        files = builder.build_project_files(
            flow_config=flow_config,
            parameters=parameter_snapshot,
            sample_rows=req.sample_sheet,
            comparisons=req.comparisons,
            work_dir=work_dir,
        )
        config_file = str(files["config"])

        # 创建任务聚合根
        task = await self._domain.submit(
            flow_id=req.flow_id,
            user_id=UUID(user_id),
            name=req.name or f"{flow_detail.meta.name} - {datetime.now().strftime('%Y%m%d%H%M%S')}",
            parameters=parameter_snapshot,
            execution_mode=req.execution_mode,
            sample_count=len(req.sample_sheet),
        )

        # 写入工作目录等运行信息
        task.work_dir = work_dir
        await self._repo.save(task)

        # 投递 Celery 任务
        run_snakemake.delay(
            snakefile=flow_detail.execution["snakefile"],
            task_id=str(task.id),
            config_file=config_file,
            config_file_param=flow_detail.execution.get("config_file_param") or "analysisyaml",
            work_dir=work_dir,
            cores=flow_detail.execution.get("default_resources", {}).get("cores", 4),
        )

        # 状态推进为已入队
        task = await self._domain.transition_status(task, TaskStatus.QUEUED)

        # 集成点#2: 任务提交前预扣饼干
        pre_deducted = Decimal("0")
        if self._settings.enable_cookie_system:
            from omichub.application.services.task_cookie_consumer import (
                TaskCookieConsumer,
            )

            consumer = TaskCookieConsumer(self._db)
            pre_deducted = await consumer.on_submit(UUID(user_id), str(task.id), req.flow_id)
            task.parameters["_cookie_pre_deducted"] = float(pre_deducted)
            task = await self._repo.save(task)

        return task_to_response(task)

    async def get_task(self, task_id: UUID, user_id: str) -> TaskResponse:
        """获取任务详情"""
        task = await self._repo.get_by_id(task_id)
        if task is None or str(task.user_id) != user_id:
            raise NotFoundError("任务不存在")
        return task_to_response(task)

    async def list_tasks(self, user_id: str, status: str | None = None) -> TaskListResponse:
        """获取用户任务列表"""
        tasks = await self._repo.list_by_user(UUID(user_id), status=status)
        return TaskListResponse(
            items=[task_to_response(t) for t in tasks],
            total=len(tasks),
        )

    async def cancel_task(self, task_id: UUID, user_id: str) -> TaskResponse:
        """取消任务"""
        task = await self._repo.get_by_id(task_id)
        if task is None or str(task.user_id) != user_id:
            raise NotFoundError("任务不存在")
        if task.status not in {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING}:
            raise ValidationError(f"当前状态 {task.status.value} 不允许取消")
        task = await self._domain.transition_status(task, TaskStatus.CANCELLED)

        # 集成点#4: 任务取消退还预扣饼干
        if self._settings.enable_cookie_system:
            pre_deducted = task.parameters.get("_cookie_pre_deducted", 0)
            if pre_deducted > 0:
                from omichub.application.services.task_cookie_consumer import (
                    TaskCookieConsumer,
                )

                consumer = TaskCookieConsumer(self._db)
                await consumer.on_cancel(UUID(user_id), str(task.id), Decimal(str(pre_deducted)))

        return task_to_response(task)

    async def get_task_dag(self, task_id: UUID, user_id: str) -> dict[str, Any]:
        """获取任务 DAG 可视化"""
        task = await self._repo.get_by_id(task_id)
        if task is None or str(task.user_id) != user_id:
            raise NotFoundError("任务不存在")

        flow_config = self._flow_service.get_flow_config(task.flow_id)
        flow_detail = self._flow_service.get_flow(task.flow_id)

        config_file = str(Path(task.work_dir) / flow_config.execution.config_file_name)

        executor = LocalSnakemakeExecutor()
        return await executor.generate_dag(
            snakefile=flow_detail.execution["snakefile"],
            config_file=config_file,
            config_file_param=flow_detail.execution.get("config_file_param") or "analysisyaml",
            work_dir=task.work_dir,
        )

    def _make_work_dir(self, flow_id: str, user_id: str) -> str:
        """生成任务工作目录"""
        base = Path(self._settings.storage_path) / "tasks" / user_id / flow_id
        # 使用 task_id 占位目录会在创建聚合根后重命名；这里先用时间戳目录
        work_dir = base / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        work_dir.mkdir(parents=True, exist_ok=True)
        return str(work_dir)
