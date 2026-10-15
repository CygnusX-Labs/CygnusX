"""FlowSubmissionValidator 单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.flow_service import FlowService
from cygnusx.application.services.managed_file_resolver import (
    FileMetadata,
    ManagedFileResolver,
)
from cygnusx.domain.flow.submission_validator import FlowSubmissionValidator


class _FakeAsyncSession(AsyncSession):
    """仅用于构造 ToolInvocationContext 的占位 session。"""

    def __init__(self):
        pass


def _make_context() -> ToolInvocationContext:
    return ToolInvocationContext(
        user_id="test-user",
        session_id="test-session",
        db=_FakeAsyncSession(),  # type: ignore[arg-type]
    )


@pytest.fixture
def validator() -> FlowSubmissionValidator:
    return FlowSubmissionValidator()


@pytest.fixture
def rna_flow():
    return FlowService().get_flow_config("rna_seq")


@pytest.mark.asyncio
async def test_valid_rna_submission(validator: FlowSubmissionValidator, rna_flow) -> None:
    context = _make_context()
    arguments = {
        "name": "Test RNA-seq",
        "parameters": {
            "project_name": "TestProject",
            "Genome_Version": "hg38",
            "species": "Homo sapiens",
            "client": "Test",
            "raw_data_path": "/data/raw",
            "execution_mode": "local",
            "queue_id": "default",
            "Library_Types": "fr-unstranded",
            "only_qc": False,
            "deg": True,
            "report": True,
        },
        "sample_sheet": [
            {"sample": "S1", "sample_name": "Sample1", "group": "ctrl"},
            {"sample": "S2", "sample_name": "Sample2", "group": "treat"},
        ],
        "comparisons": [{"name": "Treat_vs_Ctrl", "Control": "ctrl", "Treat": "treat"}],
    }

    result = await validator.validate(context, rna_flow, arguments)

    assert result.valid is True
    assert result.normalized_request is not None
    assert result.normalized_request.flow_id == "rna_seq"
    assert len(result.normalized_request.sample_sheet) == 2
    assert len(result.normalized_request.comparisons) == 1


@pytest.mark.asyncio
async def test_missing_required_parameter(validator: FlowSubmissionValidator, rna_flow) -> None:
    context = _make_context()
    arguments = {
        "name": "Local RNA-seq",
        "parameters": {
            "project_name": "",  # 显式空字符串，覆盖默认值
            "Genome_Version": "hg38",
        },
        "sample_sheet": [{"sample": "S1", "sample_name": "Sample1", "group": "ctrl"}],
    }

    result = await validator.validate(context, rna_flow, arguments)

    assert result.valid is False
    assert any(e.field == "parameters.project_name" for e in result.errors)


@pytest.mark.asyncio
async def test_missing_task_name(validator: FlowSubmissionValidator, rna_flow) -> None:
    context = _make_context()
    arguments = {
        "parameters": {
            "project_name": "Test",
            "Genome_Version": "hg38",
            "species": "Homo sapiens",
            "client": "Test",
            "raw_data_path": "/data/raw",
            "execution_mode": "local",
            "Library_Types": "fr-unstranded",
        },
        "sample_sheet": [{"sample": "S1", "sample_name": "Sample1", "group": "ctrl"}],
    }

    result = await validator.validate(context, rna_flow, arguments)

    assert result.valid is False
    assert any(e.field == "name" and e.code == "MISSING_REQUIRED" for e in result.errors)


@pytest.mark.asyncio
async def test_invalid_enum_value(validator: FlowSubmissionValidator, rna_flow) -> None:
    context = _make_context()
    arguments = {
        "name": "Local RNA-seq",
        "parameters": {
            "project_name": "Test",
            "Genome_Version": "not_a_genome",
            "species": "Homo sapiens",
            "client": "Test",
            "raw_data_path": "/data/raw",
            "execution_mode": "local",
            "queue_id": "default",
            "Library_Types": "fr-unstranded",
        },
        "sample_sheet": [{"sample": "S1", "sample_name": "Sample1", "group": "ctrl"}],
    }

    result = await validator.validate(context, rna_flow, arguments)

    assert result.valid is False
    assert any(e.code == "INVALID_ENUM" for e in result.errors)


@pytest.mark.asyncio
async def test_comparisons_group_not_found(validator: FlowSubmissionValidator, rna_flow) -> None:
    context = _make_context()
    arguments = {
        "name": "Referenced sample sheet RNA-seq",
        "parameters": {
            "project_name": "Test",
            "Genome_Version": "hg38",
            "species": "Homo sapiens",
            "client": "Test",
            "raw_data_path": "/data/raw",
            "execution_mode": "local",
            "queue_id": "default",
            "Library_Types": "fr-unstranded",
        },
        "sample_sheet": [{"sample": "S1", "sample_name": "Sample1", "group": "ctrl"}],
        "comparisons": [{"name": "x", "Control": "not_exist", "Treat": "ctrl"}],
    }

    result = await validator.validate(context, rna_flow, arguments)

    assert result.valid is False
    assert any(e.code == "GROUP_NOT_FOUND" for e in result.errors)


@pytest.mark.asyncio
async def test_parameter_not_in_whitelist(validator: FlowSubmissionValidator, rna_flow) -> None:
    context = _make_context()
    arguments = {
        "parameters": {
            "project_name": "Test",
            "Genome_Version": "hg38",
            "species": "Homo sapiens",
            "client": "Test",
            "raw_data_path": "/data/raw",
            "execution_mode": "local",
            "queue_id": "default",
            "Library_Types": "fr-unstranded",
            "malicious_param": "bad",
        },
        "sample_sheet": [{"sample": "S1", "sample_name": "Sample1", "group": "ctrl"}],
    }

    result = await validator.validate(context, rna_flow, arguments)

    assert result.valid is False
    assert any(e.code == "PARAMETER_NOT_ALLOWED" for e in result.errors)


@pytest.mark.asyncio
async def test_condition_param_ignored_when_not_met(
    validator: FlowSubmissionValidator, rna_flow
) -> None:
    context = _make_context()
    arguments = {
        "name": "Conditional RNA-seq",
        "parameters": {
            "project_name": "Test",
            "Genome_Version": "hg38",
            "species": "Homo sapiens",
            "client": "Test",
            "raw_data_path": "/data/raw",
            "execution_mode": "local",  # 不是 cluster，queue_id 不应必填
            "Library_Types": "fr-unstranded",
        },
        "sample_sheet": [{"sample": "S1", "sample_name": "Sample1", "group": "ctrl"}],
    }

    result = await validator.validate(context, rna_flow, arguments)

    # queue_id 有条件必填，local 模式下不报错
    assert result.valid is True


@pytest.mark.asyncio
async def test_sample_sheet_ref_resolution(validator: FlowSubmissionValidator, rna_flow) -> None:
    context = _make_context()
    fake_meta = FileMetadata(
        ref="upload://samples.csv",
        resolved_type="upload",
        file_id="samples.csv",
        file_name="samples.csv",
        file_size=100,
        internal_path="/tmp/samples.csv",
        content="sample,sample_name,group\nS1,Sample1,ctrl\nS2,Sample2,treat\n",
    )
    resolver = ManagedFileResolver()
    resolver._resolve_upload = AsyncMock(return_value=fake_meta)  # type: ignore[method-assign]
    validator = FlowSubmissionValidator(file_resolver=resolver)

    arguments = {
        "name": "Referenced sample sheet RNA-seq",
        "parameters": {
            "project_name": "Test",
            "Genome_Version": "hg38",
            "species": "Homo sapiens",
            "client": "Test",
            "raw_data_path": "/data/raw",
            "execution_mode": "local",
            "queue_id": "default",
            "Library_Types": "fr-unstranded",
        },
        "sample_sheet": "sample_sheet_ref://upload://samples.csv",
    }

    result = await validator.validate(context, rna_flow, arguments)

    assert result.valid is True
    assert len(result.normalized_request.sample_sheet) == 2


@pytest.mark.asyncio
async def test_final_submission_rejects_path_outside_user_root(rna_flow) -> None:
    context = _make_context()
    context.extra["final_submission"] = True
    result = await FlowSubmissionValidator().validate(
        context,
        rna_flow,
        {
            "name": "unsafe path",
            "parameters": {
                "project_name": "Test",
                "Genome_Version": "hg38",
                "species": "Homo sapiens",
                "client": "Test",
                "raw_data_path": "/tmp/not-owned",
                "execution_mode": "local",
                "Library_Types": "fr-unstranded",
            },
            "sample_sheet": [{"sample": "S1", "sample_name": "S1", "group": "ctrl"}],
        },
    )

    assert result.valid is False
    assert any(error.code == "PATH_OUTSIDE_USER_ROOT" for error in result.errors)


@pytest.mark.asyncio
async def test_file_reference_path_is_written_to_normalized_request(rna_flow) -> None:
    fake_meta = FileMetadata(
        ref="upload://reads",
        resolved_type="upload",
        file_id="reads",
        file_name="reads.fastq.gz",
        file_size=10,
        internal_path="/owned/users/test-user/reads.fastq.gz",
    )
    resolver = ManagedFileResolver()
    resolver._resolve_upload = AsyncMock(return_value=fake_meta)  # type: ignore[method-assign]
    validator = FlowSubmissionValidator(file_resolver=resolver)
    result = await validator.validate(
        _make_context(),
        rna_flow,
        {
            "name": "reference path",
            "parameters": {
                "project_name": "Test",
                "Genome_Version": "hg38",
                "species": "Homo sapiens",
                "client": "Test",
                "raw_data_path": "upload://reads",
                "execution_mode": "local",
                "Library_Types": "fr-unstranded",
            },
            "sample_sheet": [{"sample": "S1", "sample_name": "S1", "group": "ctrl"}],
        },
    )

    assert result.valid is True
    assert result.normalized_request is not None
    assert result.normalized_request.parameters["raw_data_path"] == fake_meta.internal_path
