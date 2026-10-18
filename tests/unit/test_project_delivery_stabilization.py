"""Isolated cache/authorization/budget/outbox checks; not PG/broker acceptance."""

import io
import zipfile
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import text

from cygnusx.application.schemas.project_delivery import (
    CreateProjectExport,
    DeliveryFile,
    ExportSelection,
)
from cygnusx.application.services import project_delivery_service as module
from cygnusx.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from cygnusx.domain.project_delivery_archive import verify_archive
from cygnusx.infrastructure.database.models.project_export import ProjectExportJobModel
from tests.unit.test_claim_provenance_ri10 import claim_env as claim_env
from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_project_delivery import create
from tests.unit.test_project_delivery import project_export as project_export
from tests.unit.test_report_snapshot import inline_file_capture as inline_file_capture
from tests.unit.test_research_delivery_phase4 import delivery as delivery

ORIGINAL_DISPATCH = module.dispatch_export
pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_current_project_deactivation_bypasses_stale_identity_cache(project_export):
    env = project_export
    from cygnusx.infrastructure.database.models.project import ProjectModel

    job = await create(env)
    await module.run_project_export(env.db, job.id)
    old = await env.db.get(ProjectModel, env.project)
    with env.db.sync.bind.begin() as connection:
        connection.execute(
            text("UPDATE projects SET status='disabled' WHERE id=:id"), {"id": env.project.hex}
        )
    assert old.status is None
    with pytest.raises(AuthorizationError):
        await env.service.download(env.owner, env.project, job.id)


async def test_result_record_deactivation_is_checked_again_after_cell_capture(claim_env):
    env = claim_env
    with env.db.sync.bind.begin() as connection:
        connection.execute(
            text("UPDATE file_records SET status='deleted' WHERE id=:id"), {"id": env.record.id.hex}
        )
    assert env.record.status == "active"
    with pytest.raises(NotFoundError):
        await env.claims.provenance(env.owner, env.project, env.query)


async def test_first_release_exact_payload_file_count_and_single_file_limits(project_export):
    env = project_export

    def item(index, size):
        return DeliveryFile(
            path=f"file-{index}.html", source_kind="report_file", size=size, sha256="a" * 64
        )

    limits = env.settings
    exact = [item(i, limits.project_export_file_max_bytes) for i in range(4)]
    assert sum(f.size for f in exact) == limits.project_export_max_bytes
    env.service.budget(exact)
    for invalid in (
        exact + [item(5, 1)],
        [item(1, limits.project_export_file_max_bytes + 1)],
        [item(i, 0) for i in range(limits.project_export_max_files + 1)],
    ):
        with pytest.raises(ValidationError):
            env.service.budget(invalid)
    env.service.budget([item(i, 0) for i in range(limits.project_export_max_files)])
    job = await create(env)
    await module.run_project_export(env.db, job.id)
    data = await env.service.download(env.owner, env.project, job.id)
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        expanded = sum(i.file_size for i in package.infolist())
    verify_archive(io.BytesIO(data), max_bytes=expanded)
    with pytest.raises(ValueError):
        verify_archive(io.BytesIO(data), max_bytes=expanded - 1)


@pytest.mark.parametrize("accepted", [False, True])
async def test_commit_then_broker_failure_or_lost_ack_retains_same_job(
    project_export, monkeypatch, accepted
):
    env = project_export
    from cygnusx.infrastructure.celery_app.tasks.project_exports import generate_project_export

    delivered = []

    def unavailable(*args, **kwargs):
        if accepted:
            delivered.append(kwargs["args"][0])
        raise ConnectionError("isolated broker/ack failure")

    delivery_call = Mock(side_effect=unavailable)
    monkeypatch.setattr(generate_project_export, "apply_async", delivery_call)
    monkeypatch.setattr(module, "dispatch_export", ORIGINAL_DISPATCH)
    preview = await env.service.prepare(env.owner, env.project, ExportSelection())
    request = CreateProjectExport(
        selection=preview.selection, manifest_digest=preview.content_digest(), request_key=uuid4()
    )
    first = await env.service.create(env.owner, env.project, request)
    second = await env.service.create(env.owner, env.project, request)
    assert first.id == second.id and first.status == "queued"
    assert env.db.sync.query(ProjectExportJobModel).count() == 1
    assert delivery_call.call_count == 1
    assert delivered == ([str(first.id)] if accepted else [])
