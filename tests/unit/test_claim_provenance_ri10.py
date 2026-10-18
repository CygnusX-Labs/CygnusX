"""RI10 synthetic SQLite + real TSV reads; never real scientific/runtime acceptance."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from cygnusx.application.schemas.claim_provenance import ClaimProvenanceRequest
from cygnusx.application.schemas.research_claims import ClaimDraft
from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.services import research_claim_service as claims
from cygnusx.application.services.dataset_import_service import digest
from cygnusx.application.services.execution_evidence_service import (
    EVIDENCE_KEY,
    freeze_execution_evidence,
)
from cygnusx.application.services.research_provenance_service import (
    ResearchProvenanceService,
    observation_payload,
)
from cygnusx.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from cygnusx.infrastructure.database.models.project import ProjectModel
from cygnusx.infrastructure.database.models.report import ReportModel
from cygnusx.infrastructure.database.models.result_observation import ResultObservationModel
from cygnusx.infrastructure.storage.file_registry import FileRegistry
from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_project_delivery import create
from tests.unit.test_project_delivery import project_export as project_export
from tests.unit.test_report_snapshot import inline_file_capture as inline_file_capture
from tests.unit.test_research_delivery_phase4 import delivery as delivery

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
async def claim_env(project_export, monkeypatch):
    env = project_export
    env.settings.research_plan_enabled = True
    from cygnusx.application.services import research_plan_service

    monkeypatch.setattr(research_plan_service, "get_settings", lambda: env.settings)
    monkeypatch.setattr(claims, "get_settings", lambda: env.settings)
    monkeypatch.setattr(claims, "get_path_factory", lambda: env.factory)
    env.artifact.write_text("gene_id\tlog2FoldChange\tpvalue\tpadj\nfixture_gene\t1.25\t0.03\tNA\n")
    sha = hashlib.sha256(env.artifact.read_bytes()).hexdigest()
    manifest_file = env.artifact.parent / "result_manifest.json"
    raw = json.loads(manifest_file.read_bytes())
    raw["files"][0].update(sha256=sha, size_bytes=env.artifact.stat().st_size)
    manifest_file.write_text(json.dumps(raw))
    record = await FileRegistry(env.db).register(
        env.owner, env.artifact, task_id=env.task.id, checksum=sha
    )
    request = TaskSubmitRequest(flow_id=env.task.flow_id, name="isolated-fixture", parameters={})
    env.task.parameters = {
        EVIDENCE_KEY: freeze_execution_evidence(
            env.task.id, env.owner, request, {"isolated_fixture": True}
        )
    }
    await env.db.commit()
    graph = await ResearchProvenanceService(env.db).task(
        env.owner, env.task.id, include_reports=False
    )
    payload = observation_payload(graph)
    observation = ResultObservationModel(
        user_id=env.owner,
        project_id=env.project,
        task_id=env.task.id,
        analysis_link_id=env.link.id,
        evidence_digest=digest(payload),
        manifest_sha256=graph.manifest_sha256,
        payload=payload,
    )
    env.db.add(observation)
    await env.db.flush()
    env.report.result_observation_id = observation.id
    await env.db.commit()
    assert (
        await ResearchProvenanceService(env.db).task(env.owner, env.task.id, include_reports=False)
    ).result_observation_id == observation.id
    env.record, env.observation, env.sha = record, observation, sha
    env.query = ClaimProvenanceRequest(
        task_id=env.task.id,
        file_record_id=record.id,
        feature_id="fixture_gene",
        column="pvalue",
        source_report_id=env.report.id,
    )
    env.claims = claims.ResearchClaimService(env.db)
    return env


async def test_cp01_cp04_verified_cell_links_only_real_saved_identities(claim_env):
    env = claim_env
    result = await env.claims.provenance(env.owner, env.project, env.query)
    assert result.value == 0.03 and result.row_number == 2
    assert result.verification_status == "VERIFIED_VALUE"
    assert result.supported_statement_status == "SUPPORTED_CLAIM"
    assert not result.claim_text_verified
    assert result.task_id == env.task.id and result.dataset_version_id == env.link.version_id
    assert result.result_observation_id == env.observation.id
    assert result.observation_digest == env.observation.evidence_digest
    assert result.file_record_id == env.record.id and result.file_sha256 == env.sha
    assert result.definition_digest == env.task.parameters[EVIDENCE_KEY]["definition_digest"]
    assert result.definition_status == "VERIFIED_DOCUMENT"
    assert "REPORT_SNAPSHOT_NOT_RECORDED" in result.missing_evidence
    assert result.reproducibility_status == "NOT_RUN"
    assert (
        await env.claims.provenance(env.owner, env.project, env.query)
    ).claim_id == result.claim_id


async def test_cp02_cp05_missing_or_drifted_file_never_yields_verified_value(claim_env):
    env = claim_env
    env.artifact.write_bytes(b"changed")
    with pytest.raises(ValidationError):
        await env.claims.provenance(env.owner, env.project, env.query)
    env.artifact.unlink()
    with pytest.raises(ValidationError):
        await env.claims.provenance(env.owner, env.project, env.query)


async def test_cp06_old_report_without_observation_cannot_borrow_latest(claim_env):
    env = claim_env
    legacy = ReportModel(
        user_id=env.owner,
        task_id=env.task.id,
        flow_id=env.task.flow_id,
        report_kind="scientific",
        status="completed",
        created_at=datetime.now(UTC),
        version=2,
    )
    env.db.add(legacy)
    await env.db.commit()
    value = await env.claims.provenance(
        env.owner, env.project, env.query.model_copy(update={"source_report_id": legacy.id})
    )
    assert value.value == 0.03
    assert value.report_version == 2 and value.source_report_id == legacy.id
    assert value.result_observation_id is None and value.definition_digest is None
    assert value.report_snapshot_id is None
    assert "RESULT_OBSERVATION_NOT_RECORDED" in value.missing_evidence


async def test_cp07_free_prose_is_only_interpretation_even_with_doi_or_pmid(claim_env):
    env = claim_env
    draft = ClaimDraft(
        claim_id="unverified_mechanism",
        claim_text="PMID 12345 proves a causal mechanism",
        claim_type="HYPOTHESIS",
        evidence_refs=[{"kind": "ARTICLE", "resource_id": "PMID:12345"}],
    )
    result = await env.claims.provenance(
        env.owner, env.project, env.query.model_copy(update={"claim": draft})
    )
    assert result.interpretation_status == "AI_INTERPRETATION"
    assert result.claim_text == draft.claim_text and not result.claim_text_verified
    assert "PMID" not in result.supported_statement
    assert result.verification_status == "VERIFIED_VALUE"  # value scope only


@pytest.mark.parametrize("field", ["task_id", "file_record_id", "source_report_id"])
async def test_cp08_forged_id_and_cross_owner_are_not_found(claim_env, field):
    env = claim_env
    with pytest.raises(NotFoundError):
        await env.claims.provenance(
            env.owner, env.project, env.query.model_copy(update={field: uuid4()})
        )
    with pytest.raises(NotFoundError):
        await env.claims.provenance(env.other, env.project, env.query)


async def test_na_and_forged_historical_artifact_binding_are_not_verified(claim_env):
    env = claim_env
    missing = await env.claims.provenance(
        env.owner, env.project, env.query.model_copy(update={"column": "padj"})
    )
    assert missing.value is None and missing.verification_status == "NOT_VERIFIED"
    assert missing.supported_statement_status == "NOT_VERIFIED"
    payload = json.loads(json.dumps(env.observation.payload))
    payload["artifacts"][0]["sha256"] = "0" * 64
    other = ResultObservationModel(
        user_id=env.owner,
        project_id=env.project,
        task_id=env.task.id,
        analysis_link_id=env.link.id,
        evidence_digest=digest(payload),
        payload=payload,
    )
    env.db.add(other)
    await env.db.flush()
    env.report.result_observation_id = other.id
    await env.db.commit()
    with pytest.raises(ConflictError, match="bind"):
        await env.claims.provenance(env.owner, env.project, env.query)


async def test_inactive_project_and_post_ready_association_change_block_download(project_export):
    env = project_export
    from cygnusx.application.services.project_delivery_service import run_project_export

    job = await create(env)
    await run_project_export(env.db, job.id)
    project = await env.db.get(ProjectModel, env.project)
    project.status = "disabled"
    await env.db.commit()
    with pytest.raises(AuthorizationError):
        await env.service.download(env.owner, env.project, job.id)
    project.status = "completed"
    await env.db.commit()
    env.report.version = 2
    await env.db.commit()
    with pytest.raises(ConflictError):
        await env.service.download(env.owner, env.project, job.id)


async def test_readonly_api_rejects_caller_value_and_dataset_assertions(claim_env):
    import httpx
    from fastapi import FastAPI

    from cygnusx.api import deps
    from cygnusx.api.v1.research_claims import router

    env = claim_env
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def database():
        yield env.db

    async def owner():
        return str(env.owner)

    app.dependency_overrides[deps.get_db] = database
    app.dependency_overrides[deps.get_current_user_id] = owner
    url = f"/api/v1/projects/{env.project}/research-evidence/claim-provenance"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://isolated.test"
    ) as client:
        result = await client.post(url, json=env.query.model_dump(mode="json"))
        assert result.status_code == 200 and result.json()["value"] == 0.03
        for assertion in (
            {"value": 999},
            {"dataset_version_id": str(uuid4())},
            {"verification_status": "VERIFIED_VALUE"},
        ):
            denied = await client.post(url, json={**env.query.model_dump(mode="json"), **assertion})
            assert denied.status_code == 422


async def test_explicit_snapshot_identity_is_validated_and_preserved(claim_env):
    from cygnusx.application.schemas.report_snapshot import (
        EvidenceCoverage,
        EvidenceSource,
        ReportSnapshot,
        ReproducibilityEvidence,
        SourceExecution,
        freeze_snapshot,
    )
    from cygnusx.infrastructure.database.models.report import ReportSnapshotModel

    env = claim_env
    now = datetime.now(UTC)
    source = EvidenceSource(
        source_type="gap",
        source_id="isolated_fixture",
        captured_at=now,
        capture_method="gap_annotation",
        verification_status="not_recorded",
        verification_details="Synthetic metadata-only snapshot fixture",
    )
    graph = await ResearchProvenanceService(env.db).task(env.owner, env.task.id)
    snapshot = freeze_snapshot(
        ReportSnapshot(
            generated_at=now,
            source_execution=SourceExecution(
                owner_id=env.owner,
                task_id=env.task.id,
                project_id=env.project,
                source_reference=str(env.task.id),
                association_status="not_recorded",
            ),
            research_delivery=graph,
            source_references=(source,),
            source_watermarks=(),
            inputs=(),
            environment=(),
            execution_steps=(),
            tool_calls=(),
            quality_gates=(),
            artifacts=(),
            provenance=(),
            reproducibility=ReproducibilityEvidence(
                blockers=("SYNTHETIC_FIXTURE_ONLY",), source=source
            ),
            evidence_coverage=EvidenceCoverage(not_recorded=1),
            warnings=("SYNTHETIC_FIXTURE_ONLY",),
            missing_evidence=(),
            capture_started_at=now,
            capture_finished_at=now,
        )
    )
    row = ReportSnapshotModel(
        user_id=env.owner,
        task_id=env.task.id,
        schema_version=snapshot.schema_version,
        snapshot_digest=snapshot.snapshot_digest,
        payload=snapshot.model_dump(mode="json"),
        captured_at=now,
    )
    env.db.add(row)
    await env.db.flush()
    env.report.snapshot_id = row.id
    await env.db.commit()
    before = json.dumps(row.payload, sort_keys=True)
    result = await env.claims.provenance(env.owner, env.project, env.query)
    assert result.report_snapshot_id == row.id and result.snapshot_digest == row.snapshot_digest
    assert result.result_observation_id == env.observation.id
    assert json.dumps(row.payload, sort_keys=True) == before
    wrong_source = snapshot.source_execution.model_copy(update={"project_id": uuid4()})
    wrong = freeze_snapshot(
        snapshot.model_copy(update={"source_execution": wrong_source, "snapshot_digest": None})
    )
    mismatch = ReportSnapshotModel(
        user_id=env.owner,
        task_id=env.task.id,
        schema_version=wrong.schema_version,
        snapshot_digest=wrong.snapshot_digest,
        payload=wrong.model_dump(mode="json"),
        captured_at=now,
    )
    env.db.add(mismatch)
    await env.db.flush()
    env.report.snapshot_id = mismatch.id
    await env.db.commit()
    with pytest.raises(ConflictError, match="project"):
        await env.claims.provenance(env.owner, env.project, env.query)
