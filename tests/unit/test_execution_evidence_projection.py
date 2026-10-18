"""New evidence reaches new snapshots and provenance; historical snapshot protocol retained."""

import pytest

from cygnusx.application.schemas.task import TaskSubmitRequest
from cygnusx.application.services.execution_evidence_service import (
    EVIDENCE_KEY,
    freeze_execution_evidence,
)
from tests.unit.test_dataset_phase3 import registry as registry
from tests.unit.test_report_snapshot import inline_file_capture as inline_file_capture
from tests.unit.test_report_snapshot import synthetic_rna as synthetic_rna
from tests.unit.test_research_delivery_phase4 import delivery as delivery
from tests.unit.test_research_delivery_phase4 import linked

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def freeze(task):
    return freeze_execution_evidence(
        task.id,
        task.user_id,
        TaskSubmitRequest(flow_id=task.flow_id, name="synthetic", parameters=task.parameters),
        {"fixture_flow_id": task.flow_id},  # Declared fixture, never an actual release attestation.
    )


async def test_new_snapshot_keeps_definition_binding_and_unknown_environment(synthetic_rna):
    task = synthetic_rna.records.task
    payload = freeze(task)
    task.parameters = {**task.parameters, EVIDENCE_KEY: payload}
    snapshot = await synthetic_rna.build()
    facts = {item.field: item.value for item in snapshot.inputs}
    assert facts["execution_evidence.definition_digest"] == payload["definition_digest"]
    assert (
        facts["execution_evidence.execution_binding_digest"] == payload["execution_binding_digest"]
    )
    assert "execution_definition_is_not_runtime_attestation" in snapshot.warnings


async def test_existing_provenance_links_new_evidence_to_real_task(delivery, monkeypatch):
    from pathlib import Path

    from cygnusx.application.services import research_provenance_service as module
    from cygnusx.infrastructure.database.models.result_observation import ResultObservationModel

    task, _, _, _ = await linked(delivery, monkeypatch)
    task.parameters = {EVIDENCE_KEY: freeze(task)}
    await delivery[0].flush()
    graph = await module.ResearchProvenanceService(delivery[0]).task(delivery[2], task.id)
    assert (
        graph.runtime["execution_evidence"]["definition_digest"]
        == task.parameters[EVIDENCE_KEY]["definition_digest"]
    )
    assert graph.delivery_state != "READY"
    assert "WORKFLOW_RELEASE_NOT_ATTESTED" in graph.gaps
    # Preserve a partial observation with the binding; no artifact registration or compute.
    (Path(task.work_dir) / "results/result_manifest.json").unlink()
    monkeypatch.setattr(module, "require_research_write", lambda: None)
    captured = await module.ResearchProvenanceService(delivery[0]).reconcile(delivery[2], task.id)
    row = await delivery[0].get(ResultObservationModel, captured.result_observation_id)
    assert row.task_id == task.id and row.user_id == task.user_id
    assert (
        row.payload["runtime"]["execution_evidence"]["definition_digest"]
        == (task.parameters[EVIDENCE_KEY]["definition_digest"])
    )
