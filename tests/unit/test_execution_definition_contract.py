"""RI12 design contract: immutable definitions, no persistence or execution."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from cygnusx.application.schemas.execution_definition import (
    DefinitionParameter,
    ExecutionDefinition,
    ExecutionFileRef,
)

pytestmark = pytest.mark.unit


def test_ri12_01_deep_immutability():
    item = ExecutionFileRef(file_record_id=uuid4(), role="raw_reads")
    definition = ExecutionDefinition(workflow_id="rna_seq", input_refs=(item,))
    with pytest.raises(ValidationError):
        definition.workflow_id = "counts_deg"
    with pytest.raises(ValidationError):
        definition.input_refs[0].sha256 = "a" * 64


def test_ri12_02_digest_order_and_canonical_json():
    a = DefinitionParameter(name="a", value_json='{"b": 2, "a": 1}')
    b = DefinitionParameter(name="b", value_json="2")
    first = ExecutionDefinition(workflow_id="rna_seq", normalized_parameters=(a, b))
    second = ExecutionDefinition(workflow_id="rna_seq", normalized_parameters=(b, a))
    assert first.content_digest() == second.content_digest()
    assert a.value_json == '{"a":1,"b":2}'
    assert (
        first.content_digest()
        != first.model_copy(update={"workflow_id": "atac_seq"}).content_digest()
    )


def test_ri12_03_unknown_history_not_invented():
    definition = ExecutionDefinition(workflow_id="rna_seq")
    assert definition.container_image_digest is None
    assert definition.workflow_release_digest is None
    assert definition.provenance_status == "UNKNOWN"


def test_ri12_04_roundtrip_and_version_rejection():
    definition = ExecutionDefinition(workflow_id="rna_seq")
    assert (
        ExecutionDefinition.model_validate_json(definition.model_dump_json()).content_digest()
        == definition.content_digest()
    )
    with pytest.raises(ValidationError):
        ExecutionDefinition(workflow_id="rna_seq", schema_version="future")


@pytest.mark.parametrize(
    "name,value",
    [
        ("api_key", '"secret"'),
        ("raw_data_path", '"/host/private"'),
        ("options", '{"token":"secret"}'),
        ("options", '"Bearer secret"'),
        ("options", "NaN"),
        ("options", '{"x":1,"x":2}'),
    ],
)
def test_ri12_05_sensitive_or_ambiguous_parameters(name, value):
    with pytest.raises(ValidationError):
        DefinitionParameter(name=name, value_json=value)


def test_ri12_06_existing_models_are_not_migrated_or_backfilled():
    from cygnusx.infrastructure.database.models.dataset import DatasetAnalysisLinkModel
    from cygnusx.infrastructure.database.models.research_plan import ResearchPlanModel
    from cygnusx.infrastructure.database.models.run import RunModel

    assert "plan_json" in RunModel.__table__.columns
    assert "draft" in ResearchPlanModel.__table__.columns
    assert "execution_binding" in DatasetAnalysisLinkModel.__table__.columns
    definition = ExecutionDefinition(workflow_id="rna_seq")
    assert definition.task_id is None and definition.input_refs == ()
    with pytest.raises(ValidationError):
        ExecutionDefinition(workflow_id="rna_seq", execute=True)
