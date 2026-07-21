"""Task 应用服务 — 用例编排：提交、查询、列表。"""

from __future__ import annotations

import uuid
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
from omichub.application.services.mas_task_projection import MASTaskProjection
from omichub.core.config import get_settings
from omichub.core.exceptions import NotFoundError, ValidationError
from omichub.domain.task.services import TaskDomainService
from omichub.domain.task.value_objects import TaskStatus
from omichub.infrastructure.celery_app.tasks.analysis import run_snakemake
from omichub.infrastructure.database.repositories.task_repository import (
    TaskRepositoryImpl,
)
from omichub.infrastructure.database.repositories.mas_repository import MASRepository
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
        self._mas_projection = MASTaskProjection(MASRepository(db))
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

        # 预生成 task_id 用于工作目录路径（统一收拢到 users/{uid}/results/{flow_id}/{task_id}/）
        task_id = uuid.uuid4()
        work_dir = self._make_work_dir(req.flow_id, user_id, task_id)

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
        self._write_monitor_config(
            work_dir=work_dir,
            task_id=str(task_id),
            flow_id=req.flow_id,
            user_id=user_id,
        )

        # 创建任务聚合根（复用预生成的 task_id，保证 work_dir 路径与 task id 一致）
        task = await self._domain.submit(
            flow_id=req.flow_id,
            user_id=UUID(user_id),
            name=req.name or f"{flow_detail.meta.name} - {datetime.now().strftime('%Y%m%d%H%M%S')}",
            parameters=parameter_snapshot,
            execution_mode=req.execution_mode,
            sample_count=len(req.sample_sheet),
            task_id=task_id,
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
            pre_deducted = await consumer.on_submit(
                UUID(user_id),
                str(task.id),
                req.flow_id,
                sample_count=len(req.sample_sheet),
                comparison_count=len(req.comparisons or []),
            )
            task.parameters["_cookie_pre_deducted"] = float(pre_deducted)
            task = await self._repo.save(task)

        return task_to_response(task)

    async def get_task(self, task_id: UUID, user_id: str) -> TaskResponse:
        """获取任务详情"""
        task = await self._repo.get_by_id(task_id)
        if task is not None:
            if str(task.user_id) != user_id:
                raise NotFoundError("任务不存在")
            return task_to_response(task)
        projected = await self._mas_projection.get_for_user(task_id, UUID(user_id))
        if projected is None:
            raise NotFoundError("任务不存在")
        return projected

    async def list_tasks(self, user_id: str, status: str | None = None) -> TaskListResponse:
        """获取用户任务列表"""
        tasks = await self._repo.list_by_user(UUID(user_id), status=status)
        mas_tasks = await self._mas_projection.list_for_user(UUID(user_id), status=status)
        items = [*(task_to_response(task) for task in tasks), *mas_tasks]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return TaskListResponse(
            items=items,
            total=len(items),
        )

    async def cancel_task(self, task_id: UUID, user_id: str) -> TaskResponse:
        """取消任务"""
        task = await self._repo.get_by_id(task_id)
        if task is None:
            projected = await self._mas_projection.get_for_user(task_id, UUID(user_id))
            if projected is not None:
                raise ValidationError("MAS 任务为只读投影，请通过 MAS Run 接口取消")
            raise NotFoundError("任务不存在")
        if str(task.user_id) != user_id:
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
        if task is None:
            projected_dag = await self._mas_projection.dag_for_user(task_id, UUID(user_id))
            if projected_dag is None:
                raise NotFoundError("任务不存在")
            return projected_dag
        if str(task.user_id) != user_id:
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

    def _write_monitor_config(self, work_dir: str, task_id: str, flow_id: str, user_id: str) -> None:
        """Write per-task monitor config for the Snakemake logger plugin."""
        if not self._settings.workflow_monitor_enabled:
            return
        try:
            import yaml

            path = Path(work_dir) / "monitor_config.yaml"
            monitor_base_url = self._settings.workflow_monitor_internal_url.rstrip("/")
            monitor_event_url = (
                monitor_base_url
                if monitor_base_url.endswith("/events")
                else f"{monitor_base_url}/events"
            )
            token_placeholder = "${" + self._settings.workflow_monitor_plugin_token_env + "}"
            data = {
                "project_name": task_id,
                "omichub_monitor_url": monitor_event_url,
                "omichub_monitor_token": token_placeholder,
                "omichub_task_id": task_id,
                "omichub_flow_id": flow_id,
                "omichub_user_id": user_id,
                "omichub_monitor_sign_requests": True,
                "omichub_monitor_signing_key": token_placeholder,
                "omichub_monitor_encrypt_payload": False,
                "omichub_monitor_tls_verify": True,
            }
            path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
        except OSError:
            # Monitoring must not block task submission; the workflow can still run without it.
            return

    def _make_work_dir(self, flow_id: str, user_id: str, task_id: uuid.UUID) -> str:
        """生成任务工作目录 — 使用统一路径工厂。

        新路径: users/{uid}/tasks/{task_id}/work/{flow_id}/
        旧路径 users/{uid}/results/{flow_id}/{task_id}/ 保留给历史任务。
        """
        from omichub.infrastructure.storage import get_path_factory

        pf = get_path_factory()
        pf.ensure_task_dirs(user_id, str(task_id))
        work_dir = pf.task_work_dir(user_id, str(task_id)) / flow_id
        work_dir.mkdir(parents=True, exist_ok=True)
        return str(work_dir)
