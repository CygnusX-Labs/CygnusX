"""Project-scoped dataset APIs; mutation/approval is human JWT only."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from cygnusx.api.deps import CurrentJwtUserId, CurrentUserId, DbSession
from cygnusx.application.schemas.dataset import (
    AssetAttach,
    AssetRoleReview,
    DatasetAnalysisPrepare,
    DatasetCreate,
    ImportPrepare,
    SampleAttach,
    SampleGroupReview,
    VersionCreate,
    VersionReview,
)
from cygnusx.application.services.dataset_handoff_service import DatasetHandoffService
from cygnusx.application.services.dataset_import_service import (
    DatasetImportService,
    require_dataset_read,
)
from cygnusx.application.services.dataset_service import DatasetService
from cygnusx.application.services.tool_confirmation_service import ConfirmationError
from cygnusx.core.exceptions import ConflictError
from cygnusx.infrastructure.database.models.dataset import DatasetAssetModel, DatasetSampleModel


async def dataset_read_dependency() -> None:
    require_dataset_read()


router = APIRouter(dependencies=[Depends(dataset_read_dependency)])
BASE = "/projects/{project_id}/datasets"
VERSION = BASE + "/{dataset_id}/versions/{version_id}"
IMPORT = "/projects/{project_id}/import-proposals"


@router.get(BASE)
async def list_datasets(
    project_id: UUID, user: CurrentUserId, db: DbSession
) -> list[dict[str, Any]]:
    rows = await DatasetService(db).repo.list(UUID(user), project_id)
    return [
        {
            "id": str(row.id),
            "project_id": str(row.project_id),
            "name": row.name,
            "assay_type": row.assay_type,
            "status": row.status,
        }
        for row in rows
    ]


@router.post(BASE, status_code=201)
async def create_dataset(
    project_id: UUID, request: DatasetCreate, user: CurrentJwtUserId, db: DbSession
) -> dict[str, Any]:
    service = DatasetService(db)
    row = await service.create(UUID(user), project_id, request)
    return await service.detail(UUID(user), project_id, row.id)


@router.get(BASE + "/{dataset_id}")
async def dataset_detail(
    project_id: UUID, dataset_id: UUID, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    return await DatasetService(db).detail(UUID(user), project_id, dataset_id)


@router.post(BASE + "/{dataset_id}/versions", status_code=201)
async def new_version(
    project_id: UUID,
    dataset_id: UUID,
    request: VersionCreate,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, Any]:
    version = await DatasetService(db).new_version(
        UUID(user), project_id, dataset_id, request.revision_reason
    )
    return {"version_id": str(version.id), "number": version.number, "status": version.status}


@router.get(VERSION + "/assets")
async def assets(
    project_id: UUID, dataset_id: UUID, version_id: UUID, user: CurrentUserId, db: DbSession
) -> list[dict[str, Any]]:
    service = DatasetService(db)
    await service.repo.version(UUID(user), project_id, dataset_id, version_id)
    rows = (
        (
            await db.execute(
                select(DatasetAssetModel).where(DatasetAssetModel.version_id == version_id)
            )
        )
        .scalars()
        .all()
    )
    result = []
    for row in rows:
        await service.repo.file(UUID(user), project_id, row.file_record_id)
        result.append(
            {
                "id": str(row.id),
                "file_record_id": str(row.file_record_id),
                "role": row.role,
                "original_name": row.original_name,
                "format": row.format,
                "data_type": row.data_type,
                "size": row.size,
                "sha256": row.sha256,
                "checksum_status": row.checksum_status,
                "availability": row.availability,
                "classification": row.classification,
            }
        )
    return result


@router.post(VERSION + "/assets", status_code=201)
async def attach_asset(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    request: AssetAttach,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, str]:
    row = await DatasetService(db).attach_asset(
        UUID(user), project_id, dataset_id, version_id, request
    )
    return {
        "asset_id": str(row.id),
        "checksum_status": row.checksum_status,
        "data_type": row.data_type,
    }


@router.get(VERSION + "/samples")
async def samples(
    project_id: UUID, dataset_id: UUID, version_id: UUID, user: CurrentUserId, db: DbSession
) -> list[dict[str, Any]]:
    service = DatasetService(db)
    await service.repo.version(UUID(user), project_id, dataset_id, version_id)
    rows = (
        (
            await db.execute(
                select(DatasetSampleModel).where(DatasetSampleModel.version_id == version_id)
            )
        )
        .scalars()
        .all()
    )
    result = []
    for row in rows:
        await service.repo.sample(UUID(user), row.sample_id)
        result.append(
            {
                "sample_id": str(row.sample_id),
                "sample_key": row.sample_key,
                "file_record_ids": row.file_record_ids,
                "source_accessions": row.source_accessions,
                "source_metadata": row.source_metadata,
                "user_annotation": row.user_annotation,
                "mapping_status": row.mapping_status,
            }
        )
    return result


@router.post(VERSION + "/samples", status_code=201)
async def attach_sample(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    request: SampleAttach,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, str]:
    row = await DatasetService(db).attach_sample(
        UUID(user), project_id, dataset_id, version_id, request
    )
    return {"sample_association_id": str(row.id), "mapping_status": row.mapping_status}


@router.post(VERSION + "/verify")
async def verify(
    project_id: UUID, dataset_id: UUID, version_id: UUID, user: CurrentJwtUserId, db: DbSession
) -> dict[str, Any]:
    return await DatasetHandoffService(db).verify(UUID(user), project_id, dataset_id, version_id)


@router.get(VERSION + "/handoff")
async def handoff(
    project_id: UUID, dataset_id: UUID, version_id: UUID, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    return await DatasetHandoffService(db).manifest(UUID(user), project_id, dataset_id, version_id)


@router.post(VERSION + "/handoff/freeze")
async def freeze(
    project_id: UUID, dataset_id: UUID, version_id: UUID, user: CurrentJwtUserId, db: DbSession
) -> dict[str, Any]:
    return await DatasetHandoffService(db).manifest(
        UUID(user), project_id, dataset_id, version_id, freeze=True
    )


@router.get(VERSION + "/provenance")
async def provenance(
    project_id: UUID, dataset_id: UUID, version_id: UUID, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    return await DatasetHandoffService(db).provenance(
        UUID(user), project_id, dataset_id, version_id
    )


@router.get("/projects/{project_id}/dataset-discovery/{accession}")
async def discover(
    project_id: UUID, accession: str, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    return await DatasetImportService(db).discover(UUID(user), project_id, accession)


@router.post(IMPORT)
async def prepare_import(
    project_id: UUID, request: ImportPrepare, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    return await DatasetImportService(db).prepare(UUID(user), project_id, request)


@router.get(IMPORT + "/{proposal_id}")
async def import_proposal(
    project_id: UUID, proposal_id: UUID, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    return await DatasetImportService(db).view(UUID(user), project_id, proposal_id)


@router.post(IMPORT + "/{proposal_id}/{decision}")
async def decide_import(
    project_id: UUID, proposal_id: UUID, decision: str, user: CurrentJwtUserId, db: DbSession
) -> dict[str, Any]:
    service = DatasetImportService(db)
    if decision == "execute":
        return await service.execute(UUID(user), project_id, proposal_id)
    if decision == "reconcile":
        return await service.reconcile(UUID(user), project_id, proposal_id)
    if decision not in {"approve", "reject"}:
        from cygnusx.core.exceptions import NotFoundError

        raise NotFoundError("操作不存在")
    try:
        return await service.decide(UUID(user), project_id, proposal_id, decision == "approve")
    except ConfirmationError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc


@router.post(VERSION + "/analysis-prepare")
async def analysis_prepare(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    request: DatasetAnalysisPrepare,
    user: CurrentUserId,
    db: DbSession,
) -> dict[str, Any]:
    from cygnusx.application.services.dataset_analysis_service import DatasetAnalysisService

    return await DatasetAnalysisService(db).prepare(
        UUID(user), project_id, dataset_id, version_id, request
    )


@router.post(VERSION + "/samples/{sample_key}/review")
async def review_sample(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    sample_key: str,
    request: SampleGroupReview,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, Any]:
    return await DatasetService(db).review_sample(
        UUID(user), project_id, dataset_id, version_id, sample_key, request.group
    )


@router.get(VERSION + "/compatible-workflows")
async def compatible_workflows(
    project_id: UUID, dataset_id: UUID, version_id: UUID, user: CurrentUserId, db: DbSession
) -> dict[str, Any]:
    from cygnusx.application.services.dataset_analysis_service import DatasetAnalysisService

    return await DatasetAnalysisService(db).compatible(
        UUID(user), project_id, dataset_id, version_id
    )


@router.post(VERSION + "/analysis-proposals/{proposal_id}/{decision}")
async def decide_analysis(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    proposal_id: UUID,
    decision: str,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, Any]:
    from cygnusx.application.services.dataset_analysis_service import DatasetAnalysisService
    from cygnusx.core.exceptions import NotFoundError

    service = DatasetAnalysisService(db)
    try:
        if decision == "approve":
            return await service.approve(
                UUID(user), project_id, dataset_id, version_id, proposal_id
            )
        if decision == "execute":
            return await service.execute(
                UUID(user), project_id, dataset_id, version_id, proposal_id
            )
    except ConfirmationError as exc:
        raise ConflictError(exc.message, code=exc.code) from exc
    raise NotFoundError("操作不存在")


@router.post(VERSION + "/assets/{asset_id}/expand")
async def expand_asset(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    asset_id: UUID,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, Any]:
    from cygnusx.application.services.geo_processed_data_service import GeoProcessedDataService

    return await GeoProcessedDataService(db).expand(
        UUID(user), project_id, dataset_id, version_id, asset_id
    )


@router.get(IMPORT)
async def import_proposals(
    project_id: UUID, user: CurrentUserId, db: DbSession
) -> list[dict[str, Any]]:
    return await DatasetImportService(db).list_proposals(UUID(user), project_id)


@router.get(VERSION + "/analysis-proposals/{proposal_id}")
async def analysis_proposal(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    proposal_id: UUID,
    user: CurrentUserId,
    db: DbSession,
) -> dict[str, Any]:
    from cygnusx.application.services.dataset_analysis_service import DatasetAnalysisService

    return await DatasetAnalysisService(db).view(
        UUID(user), project_id, dataset_id, version_id, proposal_id
    )


@router.post(VERSION + "/review")
async def review_version(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    request: VersionReview,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, Any]:
    return await DatasetService(db).review_version(
        UUID(user), project_id, dataset_id, version_id, request.assay_type, request.reason
    )


@router.post(VERSION + "/assets/{asset_id}/review")
async def review_asset_role(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    asset_id: UUID,
    request: AssetRoleReview,
    user: CurrentJwtUserId,
    db: DbSession,
) -> dict[str, Any]:
    return await DatasetService(db).review_asset_role(
        UUID(user), project_id, dataset_id, version_id, asset_id, request.role, request.reason
    )
