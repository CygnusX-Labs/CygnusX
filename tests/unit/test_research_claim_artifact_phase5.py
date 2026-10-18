"""Real temporary manifest/table bytes on SQLite, not actual public-science results."""

import hashlib
import json
from uuid import uuid4

import pytest

from cygnusx.application.schemas.research_claims import ArtifactCellRequest, ClaimDraft
from cygnusx.application.services import research_claim_service as claims
from cygnusx.core.exceptions import NotFoundError, ValidationError
from cygnusx.infrastructure.database.models.file import FileRecordModel
from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_research_delivery_phase4 import delivery as delivery
from tests.unit.test_research_delivery_phase4 import linked

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_statistical_value_only_from_actual_pinned_artifact(delivery, monkeypatch):
    db, _, owner, other, project, factory, settings = delivery
    settings.research_plan_enabled = True
    monkeypatch.setattr(claims, "require_plan_enabled", lambda: None)
    monkeypatch.setattr(claims, "get_path_factory", lambda: factory)
    task, _, artifact, manifest = await linked(delivery, monkeypatch)
    artifact.write_text("gene_id\tlog2FoldChange\tpvalue\tpadj\nsynthetic_gene\t1.234\t0.03\tNA\n")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest["files"][0].update(sha256=sha, size_bytes=artifact.stat().st_size)
    (artifact.parent / "result_manifest.json").write_text(json.dumps(manifest))
    record = FileRecordModel(
        user_id=owner,
        task_id=task.id,
        original_name="deg.tsv",
        storage_path=artifact.relative_to(factory.data_root).as_posix(),
        size=artifact.stat().st_size,
        checksum=sha,
        directory="projects/owned",
        status="active",
        lifecycle_status="active",
        owner_scope="personal",
        storage_backend="local",
    )
    db.add(record)
    await db.flush()
    service = claims.ResearchClaimService(db)
    request = ArtifactCellRequest(
        task_id=task.id, file_record_id=record.id, feature_id="synthetic_gene", column="pvalue"
    )
    fact = await service.cell(owner, project, request)
    assert fact["value"] == 0.03 and fact["row"] == 2 and fact["sha256"] == sha
    assert fact["scope"] == "verified_artifact_cell_not_causal_inference"
    missing_value = await service.cell(
        owner, project, request.model_copy(update={"column": "padj"})
    )
    assert missing_value["value"] is None and missing_value["gaps"] == ["STATISTICAL_VALUE_MISSING"]
    for uid, pid in [(other, project), (owner, uuid4())]:
        with pytest.raises(NotFoundError):
            await service.cell(uid, pid, request)
    claim = ClaimDraft(
        claim_id="synthetic",
        claim_text="Unsupported mechanism assertion",
        claim_type="COMPUTATIONAL_RESULT",
        evidence_refs=[{"kind": "ARTIFACT", "resource_id": str(record.id)}],
    )
    assessment = await service.assessment(owner, project, task.id, claim)
    assert assessment.provenance_status == "PARTIAL" and not assessment.fact_checked
    artifact.write_text("modified")
    with pytest.raises(ValidationError):
        await service.cell(owner, project, request)
