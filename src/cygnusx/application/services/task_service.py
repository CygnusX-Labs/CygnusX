"""Task 应用服务 — 用例编排：提交、查询、列表。"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.task import (
    TaskListResponse,
    TaskResponse,
    TaskSubmitRequest,
    task_to_response,
)
from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.flow_service import FlowService
from cygnusx.application.services.managed_file_resolver import ManagedFileResolver
from cygnusx.application.services.mas_task_projection import MASTaskProjection
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import NotFoundError, ValidationError
from cygnusx.domain.flow.submission_validator import FlowSubmissionValidator
from cygnusx.domain.task.services import TaskDomainService
from cygnusx.domain.task.value_objects import TaskStatus
from cygnusx.infrastructure.celery_app.tasks.analysis import run_snakemake
from cygnusx.infrastructure.database.repositories.mas_repository import MASRepository
from cygnusx.infrastructure.database.repositories.task_repository import (
    TaskRepositoryImpl,
)
from cygnusx.infrastructure.database.repositories.user_repository import (
    SqlAlchemyUserRepository,
)
from cygnusx.infrastructure.execution.generic_builder import GenericFlowBuilder
from cygnusx.infrastructure.execution.local import LocalSnakemakeExecutor
from cygnusx.infrastructure.task_queue.dispatcher import enqueue_task


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
        5. 保存执行证据及启用时的预扣参数，持久化 QUEUED；
        6. 投递 Celery 异步任务，投递不明交由对账。
        """
        if req.flow_id == "counts_deg":
            from cygnusx.application.services.agent_tool_gateway import require_agent_write_gate

            # Experimental matrix Flow cannot be reached by bypassing Dataset APIs.
            require_agent_write_gate("analysis.submit")
            from cygnusx.application.services.dataset_analysis_service import (
                validate_counts_task_request,
            )

            await validate_counts_task_request(self._db, UUID(user_id), req)

        from cygnusx.application.services.research_execution_binding import (
            validate_dataset_submission,
        )

        dataset_link = await validate_dataset_submission(self._db, UUID(user_id), req)

        if req.idempotency_key:
            existing = await self._repo.get_by_idempotency_key(req.idempotency_key)
            if existing is not None:
                if str(existing.user_id) != user_id:
                    raise ValidationError("幂等键已被其他用户使用")
                return task_to_response(existing)

        # Every entry point converges here. Re-run the authoritative Flow validator
        # immediately before creating work files or enqueueing a worker.
        validation = await FlowSubmissionValidator(ManagedFileResolver()).validate(
            ToolInvocationContext(
                user_id=user_id,
                session_id="task-submit",
                db=self._db,
                extra={"final_submission": True},
            ),
            self._flow_service.get_flow_config(req.flow_id),
            {
                "name": req.name,
                "parameters": dict(req.parameters),
                "sample_sheet": list(req.sample_sheet),
                "comparisons": req.comparisons,
                "execution_mode": req.execution_mode,
            },
        )
        if not validation.valid or validation.normalized_request is None:
            detail = "; ".join(error.message for error in validation.errors)
            raise ValidationError(detail or "任务参数校验失败")
        req = validation.normalized_request.model_copy(
            update={"idempotency_key": req.idempotency_key}
        )

        flow_config = self._flow_service.get_flow_config(req.flow_id)
        flow_detail = self._flow_service.get_flow(req.flow_id)

        # 预生成 task_id 用于数据库、队列和审计关联；用户目录由项目名和运行时间生成。
        task_id = uuid.uuid4()
        work_dir = self._make_work_dir(req.flow_id, req.name, user_id)
        from cygnusx.application.services.file_service import ensure_directory_chain
        from cygnusx.infrastructure.storage import get_path_factory

        project_relative = (
            Path(work_dir).parent.relative_to(get_path_factory().user_root(user_id)).as_posix()
        )
        await ensure_directory_chain(self._db, UUID(user_id), project_relative)

        # 参数快照：复制一份不可变的提交时参数
        parameter_snapshot = dict(req.parameters)

        from cygnusx.application.services.execution_evidence_service import (
            EVIDENCE_KEY,
            capture_generated_files,
            freeze_execution_evidence,
        )

        handoff = None
        if dataset_link is not None:
            from cygnusx.application.services.research_execution_binding import check_inputs

            handoff = await check_inputs(self._db, UUID(user_id), dataset_link)

        # 通用构建器生成底层流程输入文件
        builder = GenericFlowBuilder()
        files = builder.build_project_files(
            flow_config=flow_config,
            parameters=dict(req.parameters),
            sample_rows=req.sample_sheet,
            comparisons=req.comparisons,
            work_dir=work_dir,
        )
        config_file = str(files["config"])
        if dataset_link is not None:
            import yaml

            config_path = Path(config_file)
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # noqa: ASYNC240
            config["platform"] = {
                "task_id": str(task_id),
                "user_id": user_id,
                "flow_id": req.flow_id,
            }
            config["cygnusx"] = {
                **(dataset_link.execution_binding or {}),
                "dataset_version_id": str(dataset_link.version_id),
            }
            config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")  # noqa: ASYNC240
        self._write_monitor_config(
            work_dir=work_dir,
            task_id=str(task_id),
            flow_id=req.flow_id,
            user_id=user_id,
            project_name=req.name,
        )
        parameter_snapshot[EVIDENCE_KEY] = freeze_execution_evidence(
            task_id,
            UUID(user_id),
            req,
            flow_config.model_dump(mode="json"),
            link=dataset_link,
            handoff=handoff,
            generated_files=capture_generated_files(UUID(user_id), work_dir, files),
        )

        # 创建任务聚合根（复用预生成的 task_id，保证 work_dir 路径与 task id 一致）
        task = await self._domain.submit(
            flow_id=req.flow_id,
            user_id=UUID(user_id),
            name=req.name,
            parameters=parameter_snapshot,
            execution_mode=req.execution_mode,
            sample_count=len(req.sample_sheet),
            task_id=task_id,
            idempotency_key=req.idempotency_key,
        )

        # 写入工作目录等运行信息
        task.work_dir = work_dir
        await self._repo.save(task)

        # 集成点#2: 任务提交前预扣饼干
        pre_deducted = Decimal("0")
        if self._settings.enable_cookie_system:
            from cygnusx.application.services.task_cookie_consumer import (
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

        if dataset_link is not None:
            dataset_link.task_id = task.id
        task = await self._domain.transition_status(task, TaskStatus.QUEUED)
        # Freeze evidence before queue visibility for both manual and Dataset submissions.
        # Ambiguous queue delivery is reconciled; it is never an implicit execution retry.
        await self._db.commit()

        enqueue_task(
            run_snakemake,
            flow_detail.execution["snakefile"],
            str(task.id),
            task_id=f"analysis-{task.id}-attempt-0",
            config_file=config_file,
            config_file_param=flow_detail.execution.get("config_file_param") or "analysisyaml",
            work_dir=work_dir,
            cores=flow_detail.execution.get("default_resources", {}).get("cores", 4),
        )

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

    async def list_tasks(
        self,
        user_id: str,
        status: str | None = None,
        limit: int | None = None,
    ) -> TaskListResponse:
        """获取用户任务列表。

        ``limit`` 为 None 时返回全部（任务中心整表）；传入正整数时仅返回
        按提交时间倒序的前 N 条（仪表板「最近任务」卡片用），``total`` 仍为
        未截断前的总数，保证分页 / 概览计数语义不变。
        """
        tasks = await self._repo.list_by_user(UUID(user_id), status=status)
        mas_tasks = await self._mas_projection.list_for_user(UUID(user_id), status=status)
        items = [*(task_to_response(task) for task in tasks), *mas_tasks]
        items.sort(key=lambda item: item.created_at, reverse=True)
        await self._attach_user_display_info(items)
        total = len(items)
        if limit is not None:
            items = items[:limit]
        return TaskListResponse(
            items=items,
            total=total,
        )

    async def _attach_user_display_info(self, items: list[TaskResponse]) -> None:
        """按 user_id 回填用户展示信息（去重后逐个查询）。"""
        user_ids = {item.user_id for item in items if item.user_id is not None}
        if not user_ids:
            return
        user_repo = SqlAlchemyUserRepository(self._db)
        users: dict[UUID, tuple[str, str | None]] = {}
        for uid in user_ids:
            user = await user_repo.get_by_id(uid)
            if user is not None:
                users[uid] = (user.username, user.nickname)
        for item in items:
            user = users.get(item.user_id)
            if user:
                item.username, item.nickname = user

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
        if task.flow_id == "ebi_download":
            from sqlalchemy import select

            from cygnusx.infrastructure.database.models.task import TaskModel

            await self._db.execute(select(TaskModel).where(TaskModel.id == task_id)
                                   .with_for_update().execution_options(populate_existing=True))
            task = await self._repo.get_by_id(task_id)
            if task is None or str(task.user_id) != user_id:
                raise NotFoundError("任务不存在")
        if task.flow_id == "ebi_download" and task.status == TaskStatus.CANCELLED:
            return task_to_response(task)
        if task.status not in {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING}:
            raise ValidationError(f"当前状态 {task.status.value} 不允许取消")
        if task.flow_id == "ebi_download":
            # Business cancellation is not evidence of OS/process/egress cleanup.
            task.parameters = {
                **task.parameters,
                "_download_cancellation": {
                    "request_accepted": True,
                    "process_tree_stopped": False,
                    "egress_revoked": False,
                    "reconciliation_required": True,
                },
            }
        task = await self._domain.transition_status(task, TaskStatus.CANCELLED)

        # 集成点#4: 任务取消退还预扣饼干
        if self._settings.enable_cookie_system:
            pre_deducted = task.parameters.get("_cookie_pre_deducted", 0)
            if pre_deducted > 0:
                from cygnusx.application.services.task_cookie_consumer import (
                    TaskCookieConsumer,
                )

                consumer = TaskCookieConsumer(self._db)
                await consumer.on_cancel(UUID(user_id), str(task.id), Decimal(str(pre_deducted)))

        return task_to_response(task)

    async def delete_task(self, task_id: UUID, user_id: str) -> None:
        """删除任务（硬删除）。

        所有权校验：仅任务拥有者可删；MAS 任务为只读投影，不允许经此接口删除
        （前端已对 execution_mode=='mas' 隐藏删除按钮，此处再做后端兜底）。
        任务表无被外键引用的子表（日志为 JSON 列随行删除），故直接删行即可，
        会话 commit 由 ``get_db`` 依赖在请求结束时统一完成。
        """
        task = await self._repo.get_by_id(task_id)
        if task is None:
            projected = await self._mas_projection.get_for_user(task_id, UUID(user_id))
            if projected is not None:
                raise ValidationError("MAS 任务为只读投影，无法删除")
            raise NotFoundError("任务不存在")
        if str(task.user_id) != user_id:
            raise NotFoundError("任务不存在")
        deleted = await self._repo.delete(task_id)
        if not deleted:
            raise NotFoundError("任务不存在")

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

    def _write_monitor_config(
        self, work_dir: str, task_id: str, flow_id: str, user_id: str, project_name: str
    ) -> None:
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
                "project_name": project_name,
                "cygnusx_monitor_url": monitor_event_url,
                "cygnusx_monitor_token": token_placeholder,
                "cygnusx_task_id": task_id,
                "cygnusx_flow_id": flow_id,
                "cygnusx_user_id": user_id,
                "cygnusx_monitor_sign_requests": True,
                "cygnusx_monitor_signing_key": token_placeholder,
                "cygnusx_monitor_encrypt_payload": False,
                "cygnusx_monitor_tls_verify": True,
            }
            path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
        except OSError:
            # Monitoring must not block task submission; the workflow can still run without it.
            return

    def _make_work_dir(self, flow_id: str, project_name: str, user_id: str) -> str:
        """生成任务工作目录 — 使用统一路径工厂。

        新路径: users/{uid}/projects/{project}/runs/{flow}-{timestamp}/work/
        旧路径 users/{uid}/results/{flow_id}/{task_id}/ 保留给历史任务。
        """
        from cygnusx.infrastructure.storage import get_path_factory

        pf = get_path_factory()
        run_dir = pf.create_project_run_dir(user_id, project_name, flow_id)
        for name in ("input", "output", "work", "logs"):
            (run_dir / name).mkdir(parents=True, exist_ok=True)
        work_dir = run_dir / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        return str(work_dir)
