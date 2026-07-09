"""报告应用服务"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.report import (
    ReportFileResponse,
    ReportFilterParams,
    ReportListResponse,
    ReportResponse,
)
from omichub.application.services.flow_service import FlowService
from omichub.core.config import get_settings
from omichub.core.exceptions import AuthorizationError, NotFoundError
from omichub.infrastructure.database.models.report import ReportFileModel, ReportModel
from omichub.infrastructure.database.repositories.report_repository import (
    ReportRepositoryImpl,
)


class ReportService:
    """报告应用服务"""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = ReportRepositoryImpl(db)
        self._flow_service = FlowService()
        self._settings = get_settings()

    def _resolve_report_path(self, path: str) -> Path:
        """校验报告文件路径必须位于 storage_root 内，防止路径穿越。

        历史数据可能存的是绝对路径，故先 resolve 再 relative_to 校验。
        """
        if not path:
            raise NotFoundError("报告路径不能为空")
        target = Path(path).resolve()
        try:
            target.relative_to(Path(self._settings.storage_path).resolve())
        except ValueError as exc:
            raise AuthorizationError("非法报告路径：路径越权") from exc
        return target

    async def list_reports(
        self,
        user_id: str,
        params: ReportFilterParams,
    ) -> ReportListResponse:
        """获取用户报告列表"""
        items, total = await self._repo.list_by_user(
            UUID(user_id),
            keyword=params.keyword,
            flow_id=params.flow_id,
            status=params.status,
            date_range=params.date_range,
            is_starred=params.is_starred,
            page=params.page,
            page_size=params.page_size,
        )
        return ReportListResponse(
            items=[_model_to_response(item) for item in items],
            total=total,
        )

    async def get_report(self, report_id: UUID, user_id: str) -> ReportResponse:
        """获取报告详情"""
        model = await self._repo.get_by_id(report_id)
        if model is None or str(model.user_id) != user_id:
            raise NotFoundError("报告不存在")
        return _model_to_response(model)

    async def preview_html(self, report_id: UUID, user_id: str) -> str:
        """获取报告 HTML 预览内容"""
        model = await self._repo.get_by_id(report_id)
        if model is None or str(model.user_id) != user_id:
            raise NotFoundError("报告不存在")

        primary = next((f for f in model.files if f.is_primary and f.type == "html"), None)
        if primary is None:
            primary = next((f for f in model.files if f.type == "html"), None)
        if primary is None:
            return "<p>未找到可预览的 HTML 报告</p>"

        path = self._resolve_report_path(primary.path)
        if not path.exists():
            return "<p>报告文件已丢失，请尝试下载</p>"

        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return f"<p>报告读取失败: {exc}</p>"

    async def download_file(self, report_id: UUID, file_id: UUID, user_id: str) -> Path:
        """获取报告文件路径"""
        model = await self._repo.get_by_id(report_id)
        if model is None or str(model.user_id) != user_id:
            raise NotFoundError("报告不存在")

        file_model = await self._repo.get_file_by_id(file_id)
        if file_model is None or file_model.report_id != report_id:
            raise NotFoundError("文件不存在")

        path = self._resolve_report_path(file_model.path)
        if not path.exists():
            raise NotFoundError("文件已丢失")
        return path

    async def delete_report(self, report_id: UUID, user_id: str) -> None:
        """删除报告（仅删除记录）"""
        model = await self._repo.get_by_id(report_id)
        if model is None or str(model.user_id) != user_id:
            raise NotFoundError("报告不存在")
        await self._repo.delete(report_id)

    async def toggle_star(self, report_id: UUID, user_id: str, is_starred: bool) -> ReportResponse:
        """切换收藏状态"""
        model = await self._repo.get_by_id(report_id)
        if model is None or str(model.user_id) != user_id:
            raise NotFoundError("报告不存在")
        model.is_starred = is_starred
        await self._repo.save(model)
        return _model_to_response(model)

    async def mark_read(self, report_id: UUID, user_id: str) -> ReportResponse:
        """标记已读"""
        model = await self._repo.get_by_id(report_id)
        if model is None or str(model.user_id) != user_id:
            raise NotFoundError("报告不存在")
        model.is_read = True
        await self._repo.save(model)
        return _model_to_response(model)

    async def create_report_from_task(
        self,
        task_id: str,
        user_id: str,
        flow_id: str,
        work_dir: str,
        sample_count: int,
        duration: int,
    ) -> ReportModel | None:
        """任务完成后扫描目录并创建报告记录"""
        existing = await self._repo.get_by_task_id(UUID(task_id))
        if existing is not None:
            return existing

        flow_detail = self._flow_service.get_flow(flow_id)
        flow_name = flow_detail.meta.name if flow_detail else flow_id
        flow_version = flow_detail.meta.version if flow_detail else ""
        flow_icon = flow_detail.meta.icon or "📄" if flow_detail else "📄"

        now = datetime.now()
        title = f"{flow_name} 分析报告"
        description = ""

        work_path = Path(work_dir)
        report_dir = work_path / "Analysis_Report"
        html_path = report_dir / "index.html"

        # 尝试从 project_summary.json 读取更丰富的元信息
        summary_path = work_path / "report_data" / "project_summary.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                project_meta = summary.get("project_meta", {})
                stats = summary.get("stats", {})
                if project_meta.get("client"):
                    title = f"{project_meta.get('client')} - {flow_name} 分析报告"
                description = (
                    f"物种: {project_meta.get('species', 'N/A')} | "
                    f"基因组: {project_meta.get('genome_version', 'N/A')} | "
                    f"样本数: {stats.get('total_samples', sample_count)}"
                )
                sample_count = stats.get("total_samples", sample_count) or sample_count
            except Exception:  # noqa: BLE001
                pass

        status = "completed" if html_path.exists() else "failed"

        report = ReportModel(
            id=uuid.uuid4(),
            task_id=UUID(task_id),
            user_id=UUID(user_id),
            flow_id=flow_id,
            flow_name=flow_name,
            flow_version=flow_version,
            flow_icon=flow_icon,
            title=title,
            description=description,
            status=status,
            sample_count=sample_count,
            duration=duration,
            created_at=now,
            completed_at=now if status == "completed" else None,
        )
        await self._repo.create(report)

        if html_path.exists():
            file_model = ReportFileModel(
                id=uuid.uuid4(),
                report_id=report.id,
                name=html_path.name,
                type="html",
                size=html_path.stat().st_size,
                path=str(html_path),
                is_primary=True,
            )
            self._db.add(file_model)
            await self._db.flush()
            await self._db.refresh(report)

        return report

    async def stats(self, user_id: str) -> dict[str, int]:
        """用户报告统计"""
        return await self._repo.count_by_user(UUID(user_id))


def _model_to_response(model: ReportModel) -> ReportResponse:
    return ReportResponse(
        id=model.id,
        task_id=model.task_id,
        user_id=model.user_id,
        flow_id=model.flow_id,
        flow_name=model.flow_name,
        flow_version=model.flow_version,
        flow_icon=model.flow_icon,
        title=model.title,
        description=model.description,
        status=model.status,
        sample_count=model.sample_count,
        duration=model.duration,
        created_at=model.created_at,
        completed_at=model.completed_at,
        is_read=model.is_read,
        is_starred=model.is_starred,
        files=[
            ReportFileResponse(
                id=f.id,
                report_id=f.report_id,
                name=f.name,
                type=f.type,
                size=f.size,
                path=f.path,
                is_primary=f.is_primary,
                created_at=f.created_at,
            )
            for f in model.files
        ],
    )
