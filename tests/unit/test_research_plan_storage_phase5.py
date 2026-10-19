"""Actual SQLite plan persistence and authorization; not PostgreSQL acceptance."""

from uuid import uuid4

import pytest

from cygnusx.application.schemas.research_plan import PlanPrepare, PlanRevision, PlanStatus
from cygnusx.application.services import research_plan_service as module
from cygnusx.core.config import Settings
from cygnusx.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from cygnusx.infrastructure.database.models.research_plan import ResearchPlanModel
from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_research_plan_phase5 import discovery

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def plans(registry, monkeypatch):
    db, _, owner, other, project, second, foreign, *_ = registry
    ResearchPlanModel.__table__.create(db.sync.bind)
    settings = Settings(research_plan_enabled=True)
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    return db, module.ResearchPlanService(db), owner, other, project, second, foreign, settings


async def test_prepare_dedup_restore_and_cross_owner_project(plans):
    db, service, owner, other, project, second, foreign, _ = plans
    request = PlanPrepare(request_key=uuid4(), draft=discovery())
    one = await service.prepare(owner, project, request)
    await db.commit()
    two = await module.ResearchPlanService(db).prepare(owner, project, request)
    assert one.plan_id == two.plan_id and two.version == 1
    assert two.mode == "PLAN_ONLY" and all(s.task_id is None for s in two.steps)
    for uid, pid in [(other, project), (owner, second), (owner, foreign)]:
        with pytest.raises(NotFoundError):
            await service.view(uid, pid, one.plan_id)
    changed = discovery()
    changed["research_question"] = "different request"
    with pytest.raises(ConflictError):
        await service.prepare(
            owner, project, PlanPrepare(request_key=request.request_key, draft=changed)
        )


async def test_revision_retains_history_and_invalidates_review(plans):
    db, service, owner, _, project, *_ = plans
    # Exercise the immediate self-reference constraint used by PostgreSQL too.
    connection = db.sync.connection()
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    one = await service.prepare(owner, project, PlanPrepare(request_key=uuid4(), draft=discovery()))
    one = await service.review(owner, project, one.plan_id, one.digest)
    assert one.status == PlanStatus.APPROVED
    changed = discovery()
    changed["research_question"] = "new intent"
    two = await service.revise(
        owner,
        project,
        one.plan_id,
        PlanRevision(expected_digest=one.digest, request_key=uuid4(), draft=changed),
    )
    await db.commit()
    assert two.version == 2 and two.reviewed_at is None
    assert two.status == PlanStatus.READY_FOR_REVIEW
    assert (await service.view(owner, project, one.plan_id)).superseded_by == two.plan_id
    with pytest.raises(ConflictError):
        await service.review(owner, project, two.plan_id, one.digest)
    with pytest.raises(ConflictError):
        await service.review(owner, project, one.plan_id, one.digest)


async def test_gate_before_db_and_plan_cancellation_preserves_data(plans):
    db, service, owner, _, project, *rest = plans
    one = await service.prepare(owner, project, PlanPrepare(request_key=uuid4(), draft=discovery()))
    row = await service.owned(owner, project, one.plan_id)
    old_draft = row.draft.copy()
    cancelled = await service.control(owner, project, one.plan_id, "cancel")
    assert cancelled.status == PlanStatus.CANCELLED
    assert row.draft == old_draft and len(row.events) == 2
    rest[-1].research_plan_enabled = False
    with pytest.raises(AuthorizationError) as error:
        await service.prepare(owner, project, PlanPrepare(request_key=uuid4(), draft=discovery()))
    assert error.value.code == "FEATURE_DISABLED"
    assert db.sync.query(ResearchPlanModel).count() == 1


async def test_sqlite_migration_upgrade_downgrade_preserves_old_rows():
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    for name in ("users", "projects", "tasks"):
        sa.Table(name, metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    metadata.create_all(engine)
    path = Path("alembic/versions/bioopsphase5_research_plans.py")
    spec = importlib.util.spec_from_file_location("phase5_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    sentinel = uuid4()
    with engine.begin() as connection:
        connection.execute(metadata.tables["tasks"].insert().values(id=sentinel))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert "research_plans" in sa.inspect(connection).get_table_names()
            constraints = sa.inspect(connection).get_unique_constraints("research_plans")
            assert len(constraints) == 2
            migration.downgrade()
        assert connection.scalar(sa.select(metadata.tables["tasks"].c.id)) == sentinel
    engine.dispose()


async def test_actual_jwt_http_review_rejects_api_key_and_foreign_owner(plans, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import httpx
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from cygnusx.api import deps
    from cygnusx.api.v1 import research_plans
    from cygnusx.core import security
    from cygnusx.core.exceptions import CygnusXError

    db, service, owner, other, project, *_ = plans
    view = await service.prepare(
        owner, project, PlanPrepare(request_key=uuid4(), draft=discovery())
    )

    @asynccontextmanager
    async def factory():
        yield db

    monkeypatch.setattr(deps, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key="phase5-isolated-only-not-production-secret",
            jwt_algorithm="HS256",
            access_token_expire_minutes=5,
        ),
    )
    monkeypatch.setattr(deps, "_authenticate_api_key", AsyncMock(return_value=str(owner)))
    app = FastAPI()
    app.include_router(research_plans.router)

    async def isolated_db():
        yield db
        await db.commit()

    app.dependency_overrides[deps.get_db] = isolated_db

    @app.exception_handler(CygnusXError)
    async def handle(request, error):
        return JSONResponse({"code": error.code}, status_code=error.status_code)

    human = {"Authorization": "Bearer " + security.create_access_token(str(owner), 0)}
    foreign = {"Authorization": "Bearer " + security.create_access_token(str(other), 0)}
    path = f"/projects/{project}/research-plans/{view.plan_id}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=foreign)).status_code == 404
        assert (await client.get(path, headers=human)).status_code == 200
        body = {"expected_digest": view.digest}
        assert (
            await client.post(path + "/review", json=body, headers={"X-API-Key": "test"})
        ).status_code == 401
        assert (
            await client.post(path + "/review", json={**body, "approved": True}, headers=human)
        ).status_code == 422
        assert (await client.post(path + "/review", json=body, headers=human)).status_code == 200


async def test_persisted_plan_intent_is_append_only(plans):
    db, service, owner, _, project, *_ = plans
    view = await service.prepare(
        owner, project, PlanPrepare(request_key=uuid4(), draft=discovery())
    )
    await db.commit()
    row = await service.owned(owner, project, view.plan_id)
    row.draft = {**row.draft, "research_question": "mutated old intent"}
    with pytest.raises(ValueError, match="immutable"):
        await db.flush()
    await db.rollback()
    restored = await service.view(owner, project, view.plan_id)
    assert restored.draft.research_question == "synthetic discovery"


async def test_locked_read_refreshes_persisted_state_in_identity_map(plans):
    from sqlalchemy import update

    db, service, owner, _, project, *_ = plans
    view = await service.prepare(
        owner, project, PlanPrepare(request_key=uuid4(), draft=discovery())
    )
    cached = await service.owned(owner, project, view.plan_id)
    await db.commit()
    # Model a state changed by another writer without synchronizing this identity map.
    # This checks refresh semantics, not PostgreSQL lock/concurrency acceptance.
    await db.execute(
        update(ResearchPlanModel)
        .where(ResearchPlanModel.id == view.plan_id)
        .values(status=PlanStatus.CANCELLED)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    assert cached.status == PlanStatus.READY_FOR_REVIEW
    refreshed = await service.owned(owner, project, view.plan_id, lock=True)
    assert refreshed.status == PlanStatus.CANCELLED
