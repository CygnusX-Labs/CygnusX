"""GEO processed candidates and bounded expansion reuse platform file registration."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.dataset import AssetAttach
from cygnusx.application.services.dataset_import_service import require_import_write
from cygnusx.application.services.dataset_service import DatasetService
from cygnusx.application.services.file_service import ensure_directory_chain
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import ConflictError, ValidationError
from cygnusx.domain.dataset.archives import ArchiveLimits, expand_archive
from cygnusx.domain.dataset.validation import checksum, open_owned_file
from cygnusx.domain.file.value_objects import FileSource
from cygnusx.infrastructure.database.models.dataset import DatasetAssetModel
from cygnusx.infrastructure.database.models.user import UserModel
from cygnusx.infrastructure.database.repositories.dataset_repository import DatasetRepository
from cygnusx.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
from cygnusx.infrastructure.geo.adapter import trusted_url
from cygnusx.infrastructure.storage import get_path_factory
from cygnusx.infrastructure.storage.file_registry import FileRegistry
from cygnusx.infrastructure.storage.path_factory import project_slug


class GeoProcessedDataService:
    def __init__(self, db: AsyncSession, registry: FileRegistry | None = None) -> None:
        self.db = db
        self.repo = DatasetRepository(db)
        self.registry = registry or FileRegistry(db)

    @staticmethod
    def candidates(candidate: dict[str, Any]) -> dict[str, Any]:
        files = []
        for item in candidate.get("files", []):
            url = trusted_url(item["url"])
            lower = item["original_name"].lower()
            kind = (
                "SERIES_MATRIX"
                if "series_matrix" in lower
                else "ARCHIVE"
                if lower.endswith((".tar", ".tar.gz", ".tgz", ".zip"))
                else "SINGLE_CELL_CONTAINER"
                if lower.endswith((".h5", ".h5ad", ".mtx", ".mtx.gz"))
                else "TABULAR_CANDIDATE"
                if lower.endswith((".tsv", ".txt", ".csv", ".tsv.gz", ".txt.gz", ".csv.gz"))
                else "UNKNOWN"
            )
            files.append(
                {
                    **item,
                    "url": url,
                    "candidate_kind": kind,
                    "data_type": "UNKNOWN",
                    "requires_content_validation": True,
                }
            )
        return {"files": files, "status": "NEEDS_REVIEW", "counts_not_inferred_from_filename": True}

    async def expand(
        self,
        owner: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        asset_id: uuid.UUID,
    ) -> dict[str, Any]:
        require_import_write()
        version = await self.repo.version(owner, project_id, dataset_id, version_id, mutable=True)
        query = select(DatasetAssetModel).where(
            DatasetAssetModel.id == asset_id, DatasetAssetModel.version_id == version.id
        )
        asset = (await self.db.execute(query)).scalar_one_or_none()
        if asset is None:
            raise ValidationError("压缩包资产不存在")
        record = await self.repo.file(owner, project_id, asset.file_record_id)
        if record.storage_backend != "local" or Path(record.storage_path).is_absolute():
            raise ValidationError("存储后端不支持本地展开", code="STORAGE_NOT_VERIFIED")
        project = await self.repo.project(owner, project_id)
        user = (
            await self.db.execute(select(UserModel).where(UserModel.id == owner).with_for_update())
        ).scalar_one()
        from cygnusx.application.services.dataset_handoff_service import validation_limits

        factory = get_path_factory()
        with open_owned_file(
            factory.data_root / record.storage_path, factory.user_root(str(owner))
        ) as source:
            sha, _ = checksum(source, validation_limits())
            existing_sizes = (
                (
                    await self.db.execute(
                        select(DatasetAssetModel.size).where(
                            DatasetAssetModel.version_id == version_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            remaining = min(
                get_settings().dataset_import_max_bytes - sum(existing_sizes),
                user.storage_quota - user.used_storage,
            )
            if remaining <= 0:
                raise ValidationError("展开空间配额不足", code="QUOTA_EXCEEDED")
            directory = factory.project_dir(str(owner), project.slug) / "datasets"
            directory.resolve().relative_to(factory.user_root(str(owner)).resolve())
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            stage = directory / ("expanded-" + project_slug(record.original_name) + "-" + sha[:12])
            if stage.exists():
                raise ConflictError(
                    "已有展开目录，需核对登记状态，禁止覆盖重放", code="RECONCILIATION_REQUIRED"
                )
            expanded = expand_archive(
                source,
                record.original_name,
                stage,
                limits=ArchiveLimits(
                    max_files=get_settings().dataset_archive_max_files,
                    max_file_bytes=min(get_settings().dataset_archive_max_file_bytes, remaining),
                    max_total_bytes=remaining,
                    max_ratio=get_settings().dataset_archive_max_ratio,
                ),
            )
        # From this point on DB failure deliberately leaves the stage for reconciliation.
        # Never erase user files or silently redownload to compensate SQL failures.
        total = 0
        result = []
        for path in expanded:
            relative_dir = path.parent.relative_to(factory.user_root(str(owner))).as_posix()
            await ensure_directory_chain(self.db, owner, relative_dir)
            with open_owned_file(path, factory.user_root(str(owner))) as stream:
                sha256, size = checksum(stream, validation_limits())
            file = await self.registry.register(
                owner,
                path,
                source=FileSource.DOWNLOAD,
                task_id=asset.download_task_id,
                directory=relative_dir,
                checksum=sha256,
            )
            child = await DatasetService(self.db).attach_asset(
                owner,
                project_id,
                dataset_id,
                version_id,
                AssetAttach(file_record_id=file.id, role="other"),
            )
            child.classification = {
                "parent_archive_file_record_id": str(record.id),
                "parent_sha256": sha,
                "status": "REVIEW_REQUIRED",
                "data_type": "UNKNOWN",
            }
            total += size
            result.append(
                {
                    "file_record_id": str(file.id),
                    "asset_id": str(child.id),
                    "sha256": sha256,
                    "size": size,
                }
            )
        await SqlAlchemyUserRepository(self.db).add_used_storage(owner, total)
        asset.role = "archive"
        asset.sha256, asset.checksum_status, asset.availability = sha, "VERIFIED", "AVAILABLE"
        await self.db.flush()
        return {
            "assets": result,
            "state": "REVIEW_REQUIRED",
            "source_archive_file_record_id": str(record.id),
        }
