"""Phase3 SQLite persistence/contracts; no live database, downloader or Worker."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from cygnusx.application.schemas.dataset import AssetAttach, DatasetCreate, SampleAttach
from cygnusx.application.services.dataset_service import DatasetService
from cygnusx.core.exceptions import NotFoundError, ValidationError
from cygnusx.infrastructure.database.models.dataset import (
    DatasetAssetModel,
    DatasetModel,
    DatasetSampleModel,
    DatasetSourceModel,
    DatasetVersionModel,
)
from cygnusx.infrastructure.database.models.file import FileRecordModel, SampleModel
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.user import UserModel

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class OfflineDB(AsyncSession):
    def __init__(self, engine):
        self.sync = Session(engine, expire_on_commit=False)

    async def get(self, model, key, **kwargs):
        return self.sync.get(model, key, **kwargs)

    async def execute(self, statement, **kwargs):
        return self.sync.execute(statement, **kwargs)

    def add(self, row, **kwargs):
        self.sync.add(row)

    async def flush(self, **kwargs):
        self.sync.flush()

    async def commit(self):
        self.sync.commit()

    async def rollback(self):
        self.sync.rollback()


@pytest.fixture
def registry():
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def sqlite_json(element, compiler, **kwargs):
        return "JSON"

    engine = sa.create_engine("sqlite://")
    tables = [
        UserModel,
        ProjectModel,
        FileRecordModel,
        SampleModel,
        DatasetModel,
        DatasetVersionModel,
        DatasetAssetModel,
        DatasetSourceModel,
        DatasetSampleModel,
    ]
    for cls in tables:
        cls.__table__.create(engine)
    db = OfflineDB(engine)
    owner, other, project, second, foreign = [uuid4() for _ in range(5)]
    for uid in (owner, other):
        db.add(
            UserModel(
                id=uid,
                username=str(uid),
                email=f"{uid}@invalid.test",
                hashed_password="unused",
                role="user",
                status="active",
                token_version=0,
            )
        )
    for pid, uid, slug in (
        (project, owner, "owned"),
        (second, owner, "second"),
        (foreign, other, "foreign"),
    ):
        db.add(ProjectModel(id=pid, user_id=uid, name=slug, slug=slug))
    files = []
    for uid, directory in (
        (owner, "projects/owned/raw"),
        (owner, ""),
        (owner, "projects/second/raw"),
        (other, "projects/foreign/raw"),
    ):
        file = FileRecordModel(
            user_id=uid,
            original_name="reads.fastq",
            storage_path=f"users/{uid}/reads.fastq",
            size=20,
            directory=directory,
            status="active",
            lifecycle_status="active",
            owner_scope="personal",
            storage_backend="local",
        )
        db.add(file)
        files.append(file)
    sample = SampleModel(
        user_id=owner, name="sample1", file_ids=[], meta={"group_inferred": "unknown"}
    )
    db.add(sample)
    db.sync.commit()
    yield db, DatasetService(db), owner, other, project, second, foreign, files, sample
    db.sync.close()
    engine.dispose()


async def test_dataset_multiple_assets_sample_and_source_relationships(registry):
    db, service, owner, _, project, _, _, files, sample = registry
    ds = await service.create(
        owner, project, DatasetCreate(name="research", assay_type="bulk_rnaseq")
    )
    detail = await service.detail(owner, project, ds.id)
    version = await db.get(
        DatasetVersionModel, __import__("uuid").UUID(detail["versions"][0]["id"])
    )
    for file in files[:2]:
        asset = await service.attach_asset(
            owner, project, ds.id, version.id, AssetAttach(file_record_id=file.id, role="raw_reads")
        )
        assert asset.data_type == "UNKNOWN" and asset.sha256 is None
    row = await service.attach_sample(
        owner,
        project,
        ds.id,
        version.id,
        SampleAttach(
            sample_id=sample.id,
            sample_key="GSM1",
            file_record_ids=[f.id for f in files[:2]],
            source_accessions=["GSM1", "SRR1", "SRR2"],
            group="control",
            group_confirmed=True,
        ),
    )
    assert len(row.file_record_ids) == 2
    for acc, parent in (("GSE1", None), ("GSM1", "GSE1"), ("SRR1", "GSM1"), ("SRR2", "GSM1")):
        db.add(
            DatasetSourceModel(
                version_id=version.id,
                repository="GEO",
                accession=acc,
                parent_accession=parent,
                source_url="https://www.ncbi.nlm.nih.gov/geo/",
            )
        )
    await db.commit()
    assert len(db.sync.scalars(sa.select(DatasetSourceModel)).all()) == 4
    assert db.sync.get(SampleModel, sample.id).meta == {"group_inferred": "unknown"}
    assert files[1].directory == ""  # legacy unassociated file is not moved/rewritten


async def test_dataset_versions_are_distinct_and_sealed_version_immutable(registry):
    db, service, owner, _, project, _, _, files, _ = registry
    ds = await service.create(owner, project, DatasetCreate(name="GSE1"))
    versions = db.sync.scalars(sa.select(DatasetVersionModel)).all()
    versions[0].handoff = {"frozen": True}
    v2 = await service.new_version(owner, project, ds.id, "Explicit metadata correction")
    assert v2.number == 2 and v2.id != versions[0].id
    with pytest.raises(ValidationError, match="冻结"):
        await service.attach_asset(
            owner, project, ds.id, versions[0].id, AssetAttach(file_record_id=files[0].id)
        )
    assert versions[0].handoff == {"frozen": True}
    # Same accession/name is not an automatic global dedupe identity.
    ds2 = await service.create(owner, project, DatasetCreate(name="GSE1"))
    assert ds2.id != ds.id


async def test_dataset_owner_project_and_file_scope(registry):
    db, service, owner, other, project, second, foreign, files, _ = registry
    ds = await service.create(owner, project, DatasetCreate(name="owned"))
    version = db.sync.scalar(sa.select(DatasetVersionModel))
    for uid, pid in ((other, project), (owner, second), (owner, foreign)):
        with pytest.raises(NotFoundError):
            await service.detail(uid, pid, ds.id)
    for file in files[2:]:
        with pytest.raises(NotFoundError):
            await service.attach_asset(
                owner, project, ds.id, version.id, AssetAttach(file_record_id=file.id)
            )
    project_row = await db.get(ProjectModel, project)
    project_row.user_id = other
    await db.flush()
    with pytest.raises(NotFoundError):
        await service.new_version(owner, project, ds.id, "revoked")
    assert not db.sync.scalars(sa.select(DatasetAssetModel)).all()


async def test_sample_only_links_same_version_owned_files(registry):
    db, service, owner, other, project, _, _, files, sample = registry
    ds = await service.create(owner, project, DatasetCreate(name="owned"))
    version = db.sync.scalar(sa.select(DatasetVersionModel))
    with pytest.raises(ValidationError, match="先登记"):
        await service.attach_sample(
            owner,
            project,
            ds.id,
            version.id,
            SampleAttach(sample_id=sample.id, sample_key="s1", file_record_ids=[files[0].id]),
        )
    sample.user_id = other
    await db.flush()
    with pytest.raises(NotFoundError):
        await service.attach_sample(
            owner, project, ds.id, version.id, SampleAttach(sample_id=sample.id, sample_key="s1")
        )


async def test_dataset_migration_real_sqlite_upgrade_downgrade_preserves_legacy():
    """Execute actual migration operations, not metadata.create_all or SQL text inspection."""
    path = Path("alembic/versions/bioopsphase3_dataset_inputs.py")
    spec = importlib.util.spec_from_file_location("phase3_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        for name in (
            "users",
            "projects",
            "file_records",
            "samples",
            "tasks",
            "agent_tool_invocations",
        ):
            connection.exec_driver_sql(f"CREATE TABLE {name} (id CHAR(32) PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO file_records (id) VALUES ('legacy-file')")
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert "dataset_assets" in sa.inspect(connection).get_table_names()
        assert sa.inspect(connection).get_unique_constraints("dataset_versions")[0][
            "column_names"
        ] == ["dataset_id", "number"]
        assert len(sa.inspect(connection).get_foreign_keys("dataset_assets")) == 3
        module.downgrade()
        assert not any(n.startswith("dataset") for n in sa.inspect(connection).get_table_names())
        assert connection.exec_driver_sql("SELECT id FROM file_records").scalar() == "legacy-file"
    engine.dispose()
