"""One owner-scoped asset registry shared by UI, REST and Agent adapters."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.dataset import AssetAttach, DatasetCreate, SampleAttach
from cygnusx.core.exceptions import ConflictError, ValidationError
from cygnusx.infrastructure.database.models.dataset import (
    DatasetAssetModel,
    DatasetModel,
    DatasetSampleModel,
    DatasetSourceModel,
    DatasetVersionModel,
)
from cygnusx.infrastructure.database.repositories.dataset_repository import DatasetRepository


class DatasetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = DatasetRepository(db)

    async def create(
        self, owner: uuid.UUID, project_id: uuid.UUID, req: DatasetCreate
    ) -> DatasetModel:
        await self.repo.project(owner, project_id)
        result = DatasetModel(user_id=owner, project_id=project_id, **req.model_dump())
        self.db.add(result)
        await self.db.flush()
        await self.new_version(owner, project_id, result.id, "Initial explicit registration")
        return result

    async def new_version(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        reason: str,
        *,
        copy_latest: bool = True,
    ) -> DatasetVersionModel:
        await self.repo.dataset(owner, project_id, dataset_id, lock=True)
        number = (
            await self.db.execute(
                select(func.max(DatasetVersionModel.number)).where(
                    DatasetVersionModel.dataset_id == dataset_id
                )
            )
        ).scalar_one()
        result = DatasetVersionModel(
            dataset_id=dataset_id,
            number=(number or 0) + 1,
            revision_reason=reason,
            initiated_by=owner,
        )
        self.db.add(result)
        await self.db.flush()
        if number and copy_latest:
            previous = (
                await self.db.execute(
                    select(DatasetVersionModel).where(
                        DatasetVersionModel.dataset_id == dataset_id,
                        DatasetVersionModel.number == number,
                    )
                )
            ).scalar_one()
            result.source_snapshot = deepcopy(previous.source_snapshot)
            result.review_annotations = deepcopy(previous.review_annotations)
            for model in (DatasetAssetModel, DatasetSourceModel, DatasetSampleModel):
                rows = (
                    (await self.db.execute(select(model).where(model.version_id == previous.id)))
                    .scalars()
                    .all()
                )
                for row in rows:
                    if isinstance(row, DatasetAssetModel):
                        await self.repo.file(owner, project_id, row.file_record_id)
                    elif isinstance(row, DatasetSampleModel):
                        await self.repo.sample(owner, row.sample_id)
                    payload = {
                        column.name: deepcopy(getattr(row, column.name))
                        for column in model.__table__.columns
                        if column.name not in {"id", "version_id", "created_at", "updated_at"}
                    }
                    if isinstance(row, DatasetAssetModel):
                        payload.update(checksum_status="PENDING", availability="UNKNOWN")
                    self.db.add(model(version_id=result.id, **payload))
            await self.db.flush()
        return result

    async def attach_asset(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        req: AssetAttach,
    ) -> DatasetAssetModel:
        await self.repo.version(owner, project_id, dataset_id, version_id, mutable=True)
        record = await self.repo.file(owner, project_id, req.file_record_id)
        existing = (
            await self.db.execute(
                select(DatasetAssetModel).where(
                    DatasetAssetModel.version_id == version_id,
                    DatasetAssetModel.file_record_id == req.file_record_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.role != req.role:
                raise ConflictError("资产角色已登记；修正应显式创建新版本")
            return existing
        asset = DatasetAssetModel(
            version_id=version_id,
            file_record_id=record.id,
            # Human role is a requested purpose, never proof of scientific type.
            role=req.role,
            original_name=record.original_name,
            storage_name=PurePath(record.storage_path).name,
            size=record.size,
            checksum_status="PENDING",
            availability="UNKNOWN",
            data_type="UNKNOWN",
            classification={
                "classification_source": "unverified",
                "evidence": [],
                "inference": [],
                "reviewer_override": None,
            },
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def attach_sample(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        req: SampleAttach,
    ) -> DatasetSampleModel:
        await self.repo.version(owner, project_id, dataset_id, version_id, mutable=True)
        sample = await self.repo.sample(owner, req.sample_id)
        for existing_file_id in sample.file_ids:
            await self.repo.file(owner, project_id, uuid.UUID(existing_file_id))
        if req.group_confirmed and not req.group:
            raise ValidationError("确认分组必须指定分组")
        asset_ids = set(
            (
                await self.db.execute(
                    select(DatasetAssetModel.file_record_id).where(
                        DatasetAssetModel.version_id == version_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for file_id in req.file_record_ids:
            await self.repo.file(owner, project_id, file_id)
            if file_id not in asset_ids:
                raise ValidationError("样本文件必须先登记到同一版本")
        existing = (
            await self.db.execute(
                select(DatasetSampleModel).where(
                    DatasetSampleModel.version_id == version_id,
                    DatasetSampleModel.sample_key == req.sample_key,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("样本已登记；更正应追加新版本，不覆盖来源")
        association = DatasetSampleModel(
            version_id=version_id,
            sample_id=sample.id,
            sample_key=req.sample_key,
            source_accessions=req.source_accessions,
            file_record_ids=[str(fid) for fid in req.file_record_ids],
            source_metadata={
                "name": sample.name,
                "species": sample.species,
                "tissue": sample.tissue,
                "metadata": {
                    key: value
                    for key, value in sample.meta.items()
                    if key
                    in {
                        "title",
                        "characteristics",
                        "treatment",
                        "disease",
                        "tissue",
                        "organism",
                        "platform",
                        "batch",
                        "source_url",
                        "processing",
                    }
                },
            },
            user_annotation={
                "group": req.group,
                "group_confirmed": req.group_confirmed,
                "reviewed_by": str(owner) if req.group_confirmed else None,
            },
            mapping_status="CONFIRMED" if req.group_confirmed else "NEEDS_REVIEW",
        )
        self.db.add(association)
        await self.db.flush()
        return association

    async def detail(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
    ) -> dict[str, Any]:
        dataset = await self.repo.dataset(owner, project_id, dataset_id)
        versions = list(
            (
                await self.db.execute(
                    select(DatasetVersionModel)
                    .where(DatasetVersionModel.dataset_id == dataset_id)
                    .order_by(DatasetVersionModel.number.desc())
                )
            )
            .scalars()
            .all()
        )
        return {
            "id": str(dataset.id),
            "project_id": str(dataset.project_id),
            "name": dataset.name,
            "description": dataset.description,
            "assay_type": dataset.assay_type,
            "organism": dataset.organism,
            "status": dataset.status,
            "schema_version": dataset.schema_version,
            "versions": [
                {
                    "id": str(v.id),
                    "number": v.number,
                    "status": v.status,
                    "revision_reason": v.revision_reason,
                    "asset_fingerprint": v.asset_fingerprint,
                }
                for v in versions
            ],
        }

    async def review_sample(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        sample_key: str,
        group: str,
    ) -> dict[str, Any]:
        await self.repo.version(owner, project_id, dataset_id, version_id, mutable=True)
        row = (
            await self.db.execute(
                select(DatasetSampleModel).where(
                    DatasetSampleModel.version_id == version_id,
                    DatasetSampleModel.sample_key == sample_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            from cygnusx.core.exceptions import NotFoundError

            raise NotFoundError("样本关联不存在")
        await self.repo.sample(owner, row.sample_id)
        prior = row.user_annotation
        history = [
            *prior.get("review_history", []),
            {
                "previous_group": prior.get("group"),
                "group": group,
                "reviewed_by": str(owner),
                "reviewed_at": datetime.now(UTC).isoformat(),
            },
        ]
        row.user_annotation = {
            "group": group,
            "group_confirmed": True,
            "reviewed_by": str(owner),
            "review_history": history,
        }
        row.mapping_status = "CONFIRMED"
        await self.db.flush()
        return {"sample_key": sample_key, "group": group, "mapping_status": row.mapping_status}

    async def review_version(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        assay_type: str,
        reason: str,
    ) -> dict[str, Any]:
        version = await self.repo.version(owner, project_id, dataset_id, version_id, mutable=True)
        annotation = deepcopy(version.review_annotations or {})
        history = list(annotation.get("history", []))
        history.append(
            {
                "assay_type": assay_type,
                "reason": reason,
                "reviewed_by": str(owner),
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        annotation.update(assay_type=assay_type, history=history)
        version.review_annotations = annotation
        await self.db.flush()
        return annotation

    async def review_asset_role(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        asset_id: uuid.UUID,
        role: str,
        reason: str,
    ) -> dict[str, Any]:
        await self.repo.version(owner, project_id, dataset_id, version_id, mutable=True)
        asset = (
            await self.db.execute(
                select(DatasetAssetModel).where(
                    DatasetAssetModel.id == asset_id, DatasetAssetModel.version_id == version_id
                )
            )
        ).scalar_one_or_none()
        if asset is None:
            raise ValidationError("资产不属于当前版本")
        await self.repo.file(owner, project_id, asset.file_record_id)
        history = list(asset.classification.get("role_review_history", []))
        history.append(
            {
                "old_role": asset.role,
                "role": role,
                "reason": reason,
                "reviewed_by": str(owner),
                "reviewed_at": datetime.now(UTC).isoformat(),
            }
        )
        # Human role never promotes scientific type. Content must be verified again.
        asset.role = role
        asset.data_type, asset.checksum_status = "UNKNOWN", "PENDING"
        asset.classification = {"role_review_history": history, "data_type": "UNKNOWN"}
        await self.db.flush()
        return {"asset_id": str(asset.id), "role": role, "data_type": "UNKNOWN"}
