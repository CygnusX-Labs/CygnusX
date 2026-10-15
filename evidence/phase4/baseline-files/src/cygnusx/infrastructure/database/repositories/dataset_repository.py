"""Dataset persistence with owner/project authorization at every entry point."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from cygnusx.infrastructure.database.models.dataset import DatasetModel, DatasetVersionModel
from cygnusx.infrastructure.database.models.file import FileRecordModel, SampleModel
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.user import UserModel


class DatasetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def project(
        self, owner: uuid.UUID, project_id: uuid.UUID, *, lock: bool = False
    ) -> ProjectModel:
        user = await self.db.get(UserModel, owner)
        if user is None or user.status != "active":
            raise NotFoundError("用户不可用")
        if user.role != "admin" and "files" in (user.disabled_modules or []):
            raise AuthorizationError("数据管理模块无权限", code="FORBIDDEN")
        query = select(ProjectModel).where(
            ProjectModel.id == project_id, ProjectModel.user_id == owner
        )
        if lock:
            query = query.with_for_update()
        project = (await self.db.execute(query)).scalar_one_or_none()
        if project is None:
            raise NotFoundError("项目不存在或无权访问")
        return project

    async def require_module(self, owner: uuid.UUID, module: str) -> None:
        user = await self.db.get(UserModel, owner)
        if user is None or user.status != "active" or (user.role != "admin" and module in (user.disabled_modules or [])):
            raise AuthorizationError("模块无权限", code="FORBIDDEN")

    async def dataset(
        self, owner: uuid.UUID, project_id: uuid.UUID, dataset_id: uuid.UUID, *, lock: bool = False
    ) -> DatasetModel:
        await self.project(owner, project_id)
        query = select(DatasetModel).where(
            DatasetModel.id == dataset_id,
            DatasetModel.user_id == owner,
            DatasetModel.project_id == project_id,
        )
        if lock:
            query = query.with_for_update()
        result = (await self.db.execute(query)).scalar_one_or_none()
        if result is None:
            raise NotFoundError("Dataset 不存在或无权访问")
        return result

    async def version(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        mutable: bool = False,
    ) -> DatasetVersionModel:
        await self.dataset(owner, project_id, dataset_id, lock=mutable)
        query = select(DatasetVersionModel).where(
            DatasetVersionModel.id == version_id, DatasetVersionModel.dataset_id == dataset_id
        )
        result = (await self.db.execute(query)).scalar_one_or_none()
        if result is None:
            raise NotFoundError("DatasetVersion 不存在")
        if mutable and result.handoff is not None:
            raise ValidationError("版本已冻结，修正应创建新版本", code="VERSION_SEALED")
        return result

    async def list(self, owner: uuid.UUID, project_id: uuid.UUID) -> list[DatasetModel]:
        await self.project(owner, project_id)
        result = await self.db.execute(
            select(DatasetModel)
            .where(DatasetModel.user_id == owner, DatasetModel.project_id == project_id)
            .order_by(DatasetModel.created_at.desc(), DatasetModel.id)
            .limit(200)
        )
        return list(result.scalars().all())

    async def file(
        self, owner: uuid.UUID, project_id: uuid.UUID, file_id: uuid.UUID
    ) -> FileRecordModel:
        project = await self.project(owner, project_id)
        result = await self.db.get(FileRecordModel, file_id)
        if (
            result is None
            or result.user_id != owner
            or result.owner_scope != "personal"
            or result.status != "active"
            or result.lifecycle_status != "active"
        ):
            raise NotFoundError("文件不存在或无权访问")
        # A legacy unassociated personal upload may be explicitly associated. A
        # known different project directory is never silently reassigned.
        parts = result.directory.split("/")
        if len(parts) >= 2 and parts[0] == "projects" and parts[1] != project.slug:
            raise NotFoundError("文件属于其他项目")
        return result

    async def sample(self, owner: uuid.UUID, sample_id: uuid.UUID) -> SampleModel:
        result = await self.db.get(SampleModel, sample_id)
        if result is None or result.user_id != owner:
            raise NotFoundError("样本不存在或无权访问")
        return result
