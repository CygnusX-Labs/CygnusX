"""RI09.5 read-only HTML prototype, not published scientific-report acceptance."""

import json
from html.parser import HTMLParser
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from cygnusx.application.schemas.project_delivery import ExportSelection
from cygnusx.application.services.report_audit_renderer import (
    PROJECT_SUMMARY_TEMPLATE,
    render_project_summary_prototype,
)
from tests.unit.test_claim_provenance_ri10 import claim_env as claim_env
from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_project_delivery import create
from tests.unit.test_project_delivery import project_export as project_export
from tests.unit.test_report_snapshot import inline_file_capture as inline_file_capture
from tests.unit.test_research_delivery_phase4 import delivery as delivery

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class Sections(HTMLParser):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.scripts = 0

    def handle_starttag(self, tag, _attrs):
        self.count += tag == "section"
        self.scripts += tag == "script"


async def test_pr01_pr08_prototype_reuses_frozen_manifest_and_does_not_create_reports(
    project_export, monkeypatch
):
    env = project_export
    from cygnusx.application.services.bioreport_adapter import BioReportAdapter
    from cygnusx.application.services.download_service import DownloadService
    from cygnusx.application.services.task_service import TaskService

    monkeypatch.setattr(TaskService, "submit", AsyncMock(side_effect=AssertionError("No compute")))
    monkeypatch.setattr(
        DownloadService, "submit", AsyncMock(side_effect=AssertionError("No download"))
    )
    monkeypatch.setattr(
        BioReportAdapter,
        "render",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("No rendering subprocess")),
    )
    job = await create(env)
    from cygnusx.application.schemas.project_delivery import ProjectDeliveryManifest

    frozen = ProjectDeliveryManifest.model_validate(job.manifest)
    original = json.dumps(job.manifest, sort_keys=True)
    html = render_project_summary_prototype(frozen, job.manifest_digest)
    parser = Sections()
    parser.feed(html)
    assert parser.count == 14 and parser.scripts == 0
    assert job.manifest_digest in html and PROJECT_SUMMARY_TEMPLATE in html
    assert "只读原型" in html and "PDF_NOT_GENERATED" in html
    assert "NOT_RUN" in html and "NOT_RECORDED" in html
    assert "REPORT_SNAPSHOT_MISSING" in html
    assert json.dumps(job.manifest, sort_keys=True) == original
    assert env.dispatch.await_count == 1  # Only the explicitly created export, no summary job.
    assert job.file_record_id is None and job.status == "queued"


async def test_pr03_pr04_missing_reports_and_hostile_metadata_are_explicit(project_export):
    env = project_export
    manifest = await env.service.prepare(env.owner, env.project, ExportSelection())
    hostile = manifest.model_copy(
        update={"gaps": (*manifest.gaps, '<script>alert("not fact")</script>')}
    )
    html = render_project_summary_prototype(hostile, hostile.content_digest())
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "REPRODUCIBILITY_REPORT_MISSING" in html
    with pytest.raises(ValueError):
        render_project_summary_prototype(manifest, "0" * 64)


async def test_pr10_pr12_only_scope_bound_claim_values_can_be_shown(claim_env):
    env = claim_env
    claim = await env.claims.provenance(env.owner, env.project, env.query)
    manifest = await env.service.prepare(env.owner, env.project, ExportSelection(kind="results"))
    html = render_project_summary_prototype(manifest, manifest.content_digest(), (claim,))
    assert claim.claim_id in html and claim.file_sha256 in html
    assert "0.03" in html
    with pytest.raises(ValueError):
        render_project_summary_prototype(
            manifest, manifest.content_digest(), (claim.model_copy(update={"project_id": uuid4()}),)
        )
    evidence_only = await env.service.prepare(env.owner, env.project, ExportSelection())
    with pytest.raises(ValueError):
        render_project_summary_prototype(evidence_only, evidence_only.content_digest(), (claim,))


async def test_pr05_readonly_api_retains_user_scope_and_script_free_response(project_export):
    import httpx
    from fastapi import FastAPI

    from cygnusx.api import deps
    from cygnusx.api.v1.research_delivery import router

    env = project_export
    job = await create(env)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def database():
        yield env.db

    async def owner():
        return str(env.owner)

    app.dependency_overrides[deps.get_db] = database
    app.dependency_overrides[deps.get_current_user_id] = owner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated.test"
    ) as client:
        response = await client.get(
            f"/api/v1/projects/{env.project}/exports/{job.id}/summary-preview"
        )
        assert response.status_code == 200
        assert response.headers["x-report-status"] == "prototype"
        assert response.headers["x-manifest-digest"] == job.manifest_digest
        assert response.headers["cache-control"] == "no-store"
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert job.status == "queued" and job.file_record_id is None


async def test_pr02_multiple_explicit_dataset_task_references(project_export, delivery):
    from cygnusx.application.schemas.dataset import DatasetCreate
    from cygnusx.infrastructure.database.models.dataset import (
        DatasetAnalysisLinkModel,
        DatasetVersionModel,
    )
    from cygnusx.infrastructure.database.models.task import TaskModel

    env = project_export
    dataset = await delivery[1].create(
        env.owner, env.project, DatasetCreate(name="second synthetic", assay_type="bulk_rnaseq")
    )
    version = env.db.sync.query(DatasetVersionModel).filter_by(dataset_id=dataset.id).one()
    task = TaskModel(
        id=uuid4(), user_id=env.owner, flow_id="counts_deg", status="failed", parameters={}
    )
    env.db.add(task)
    env.db.add(
        DatasetAnalysisLinkModel(
            id=uuid4(),
            version_id=version.id,
            task_id=task.id,
            flow_id=task.flow_id,
            handoff_hash="a" * 64,
            parameters_hash="b" * 64,
            normalized_request={"owner_id": str(env.owner), "project_id": str(env.project)},
            state="QUEUED",
        )
    )
    await env.db.commit()
    manifest = await env.service.prepare(env.owner, env.project, ExportSelection())
    html = render_project_summary_prototype(manifest, manifest.content_digest())
    assert str(env.task.id) in html and str(task.id) in html
    assert str(version.id) in html
