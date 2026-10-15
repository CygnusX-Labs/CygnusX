"""Synthetic fixtures only: these tests do not create or execute real RNA analyses."""

import asyncio
import hashlib
import json
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.report_snapshot import (
    EvidenceStatus,
    ReportSnapshot,
    canonical_serialization,
    snapshot_digest,
)
from cygnusx.application.services.report_snapshot_builder import ReportSnapshotBuilder
from cygnusx.application.services.report_snapshot_sources import (
    DatabaseTaskEvidenceSource,
    TaskEvidenceRecords,
    TaskEvidenceSource,
)
from cygnusx.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from cygnusx.infrastructure.config.storage_config import StorageConfig
from cygnusx.infrastructure.database.models.file import FileRecordModel
from cygnusx.infrastructure.database.models.run import RunModel
from cygnusx.infrastructure.database.models.run_event import RunEventModel
from cygnusx.infrastructure.database.models.task import TaskModel
from cygnusx.infrastructure.storage.path_factory import StoragePathFactory

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 12, 1, 0, tzinfo=UTC)
THEN = NOW - timedelta(days=30)
P = ParamSpec("P")
T = TypeVar("T")


@pytest.fixture(autouse=True)
def inline_file_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test file reads deterministically without depending on executor wakeup sockets.

    The managed sandbox cannot wake asyncio from worker threads (a standalone
    asyncio.to_thread(lambda: 42) also hangs). Production still uses to_thread.
    """

    async def inline(function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline)


@dataclass
class SyntheticRNA:
    owner: UUID
    records: TaskEvidenceRecords
    factory: StoragePathFactory
    deliver: Path
    manifest: dict[str, Any]

    def write_manifest(self) -> None:
        (self.deliver / "result_manifest.json").write_text(json.dumps(self.manifest))

    async def build(self, *, run_id: UUID | None = None, now: datetime = NOW) -> ReportSnapshot:
        source = MagicMock()
        source.read = AsyncMock(return_value=self.records)
        builder = ReportSnapshotBuilder(
            cast(TaskEvidenceSource, source), factory=self.factory, clock=lambda: now
        )
        return await builder.build(self.owner, self.records.task.id, run_id=run_id)


@pytest.fixture
def synthetic_rna(tmp_path: Path) -> SyntheticRNA:
    owner = uuid4()
    factory = StoragePathFactory(StorageConfig(data_root=str(tmp_path), users_subdir="users"))
    run_dir = factory.create_project_run_dir(str(owner), "synthetic-fixture", "rna")
    deliver = run_dir / "data_deliver"
    deliver.mkdir()
    (deliver / "counts.tsv").write_bytes(b"gene\tcount\ng1\t1\n")
    task = TaskModel(
        id=uuid4(),
        user_id=owner,
        flow_id="rna_seq",
        status="completed",
        work_dir=str(run_dir / "work"),
        sample_count=2,
        parameters={"cores": 2},
        created_at=THEN,
        updated_at=THEN,
        started_at=THEN,
        finished_at=THEN,
    )
    manifest = {
        "manifest_version": "1.0",
        "kind": "omichub.analysis.result",
        "platform": {"task_id": str(task.id), "user_id": str(owner), "flow_id": "rna_seq"},
        "run": {
            "status": "completed",
            "pipeline": {"version": "v0.1.9"},
            "started_at": THEN.isoformat(),
            "duration_seconds": 42,
        },
        "files": [
            {
                "path": "counts.tsv",
                "type": "tsv",
                "category": "expression",
                "size_bytes": (deliver / "counts.tsv").stat().st_size,
            }
        ],
    }
    fixture = SyntheticRNA(
        owner, TaskEvidenceRecords(task, None, (), ()), factory, deliver, manifest
    )
    fixture.write_manifest()
    return fixture


def associated_run(fixture: SyntheticRNA) -> RunModel:
    return RunModel(
        id=uuid4(),
        user_id=fixture.owner,
        task_id=fixture.records.task.id,
        project_slug="synthetic-fixture",
        flow_id="rna_seq",
        release_id="2.3.0",
        status="queued",
        confirmed_at=THEN,
        created_at=THEN,
        updated_at=THEN,
        plan_json={"secret": "MUST-NOT-EXPORT"},
        plan_digest="a" * 64,
    )


def registered_file(fixture: SyntheticRNA, path: Path) -> FileRecordModel:
    return FileRecordModel(
        id=uuid4(),
        user_id=fixture.owner,
        task_id=fixture.records.task.id,
        storage_path=path.relative_to(fixture.factory.data_root).as_posix(),
        storage_backend="local",
        status="active",
        owner_scope="personal",
        checksum="opaque-legacy-checksum",
        source="pipeline",
        created_at=THEN,
        updated_at=THEN,
    )


async def test_task_without_run_is_supported(synthetic_rna: SyntheticRNA) -> None:
    snapshot = await synthetic_rna.build()
    identity = snapshot.source_execution
    assert identity.task_id == synthetic_rna.records.task.id
    assert identity.run_id is None
    assert identity.project_id is None and identity.project_slug is None
    assert identity.execution_attempt_id is None
    assert identity.association_status == "not_recorded"
    assert snapshot.artifacts[0].source.verification_status == EvidenceStatus.VERIFIED
    assert snapshot.artifacts[0].origin.verification_status == EvidenceStatus.VERIFIED
    assert snapshot.reproducibility.assessment == "insufficient_evidence"
    assert snapshot.snapshot_digest == snapshot_digest(snapshot)


async def test_registered_artifacts_survive_unrecorded_work_dir(
    synthetic_rna: SyntheticRNA,
) -> None:
    record = registered_file(synthetic_rna, synthetic_rna.deliver / "counts.tsv")
    synthetic_rna.records = replace(synthetic_rna.records, files=(record,))
    synthetic_rna.records.task.work_dir = None
    snapshot = await synthetic_rna.build()
    assert snapshot.artifacts[0].file_record_id == record.id
    assert any(w.source_type == "file_record" for w in snapshot.source_watermarks)
    assert any(m.field == "result_manifest" for m in snapshot.missing_evidence)


async def test_confirmed_run_and_events_are_explicit(synthetic_rna: SyntheticRNA) -> None:
    run = associated_run(synthetic_rna)
    event = RunEventModel(
        id=uuid4(),
        run_id=run.id,
        task_id=run.task_id,
        sequence=1,
        phase="task",
        status="queued",
        occurred_at=THEN,
        payload={"token": "MUST-NOT-EXPORT"},
    )
    synthetic_rna.records = replace(synthetic_rna.records, run=run, events=(event,))
    snapshot = await synthetic_rna.build(run_id=run.id)
    assert snapshot.source_execution.run_id == run.id
    assert snapshot.source_execution.project_slug == "synthetic-fixture"
    assert snapshot.source_execution.association_status == "verified"
    assert snapshot.execution_steps[-1].source.observed_at == THEN
    assert snapshot.execution_steps[-1].sequence == 1
    assert "MUST-NOT-EXPORT" not in snapshot.model_dump_json()


@pytest.mark.parametrize("conflict", ["task_id", "flow_id", "unconfirmed", "requested_run"])
async def test_run_identity_conflicts_rejected(synthetic_rna: SyntheticRNA, conflict: str) -> None:
    run = associated_run(synthetic_rna)
    if conflict == "task_id":
        run.task_id = uuid4()
    elif conflict == "flow_id":
        run.flow_id = "atac_seq"
    elif conflict == "unconfirmed":
        run.confirmed_at = None
    synthetic_rna.records = replace(synthetic_rna.records, run=run)
    with pytest.raises(ConflictError):
        await synthetic_rna.build(run_id=uuid4() if conflict == "requested_run" else run.id)


@pytest.mark.parametrize("object_kind", ["task", "run", "file"])
async def test_cross_owner_rejected(synthetic_rna: SyntheticRNA, object_kind: str) -> None:
    if object_kind == "task":
        synthetic_rna.records.task.user_id = uuid4()
    elif object_kind == "run":
        run = associated_run(synthetic_rna)
        run.user_id = uuid4()
        synthetic_rna.records = replace(synthetic_rna.records, run=run)
    else:
        file = registered_file(synthetic_rna, synthetic_rna.deliver / "counts.tsv")
        file.user_id = uuid4()
        synthetic_rna.records = replace(synthetic_rna.records, files=(file,))
    with pytest.raises(AuthorizationError):
        await synthetic_rna.build()


async def test_missing_manifest_never_verifies_legacy_html(synthetic_rna: SyntheticRNA) -> None:
    (synthetic_rna.deliver / "result_manifest.json").unlink()
    (synthetic_rna.deliver / "index.html").write_text("legacy HTML")
    snapshot = await synthetic_rna.build()
    assert not snapshot.artifacts
    missing = {item.field: item.source.verification_status for item in snapshot.missing_evidence}
    assert missing["result_manifest"] == EvidenceStatus.NOT_RECORDED
    assert snapshot.quality_gates[0].decision is None


async def test_explicit_registered_artifact_survives_missing_manifest(
    synthetic_rna: SyntheticRNA,
) -> None:
    (synthetic_rna.deliver / "result_manifest.json").unlink()
    file = registered_file(synthetic_rna, synthetic_rna.deliver / "counts.tsv")
    synthetic_rna.records = replace(synthetic_rna.records, files=(file,))
    snapshot = await synthetic_rna.build()
    assert snapshot.artifacts[0].file_record_id == file.id
    assert snapshot.artifacts[0].origin.verification_status == EvidenceStatus.VERIFIED
    assert len(snapshot.artifacts[0].fingerprints) == 1  # legacy checksum algorithm never guessed


async def test_missing_artifact_is_unavailable(synthetic_rna: SyntheticRNA) -> None:
    (synthetic_rna.deliver / "counts.tsv").unlink()
    snapshot = await synthetic_rna.build()
    assert snapshot.artifacts[0].source.verification_status == EvidenceStatus.UNAVAILABLE
    assert not snapshot.artifacts[0].fingerprints
    assert snapshot.evidence_coverage.unavailable == 1


@pytest.mark.parametrize("algorithm", ["md5", "sha256", "size_bytes"])
async def test_mismatched_artifact_is_not_verified(
    synthetic_rna: SyntheticRNA, algorithm: str
) -> None:
    synthetic_rna.manifest["files"][0][algorithm] = {
        "md5": "0" * 32,
        "sha256": "0" * 64,
        "size_bytes": 999,
    }[algorithm]
    synthetic_rna.write_manifest()
    snapshot = await synthetic_rna.build()
    artifact = snapshot.artifacts[0]
    assert artifact.source.verification_status == EvidenceStatus.VERIFICATION_FAILED
    assert "artifact_verification_failed" in snapshot.warnings
    for fingerprint in artifact.fingerprints:
        if fingerprint.scope == "manifest_declared":
            assert fingerprint.verified_at is None


async def test_hashes_are_current_not_execution_time(synthetic_rna: SyntheticRNA) -> None:
    content = (synthetic_rna.deliver / "counts.tsv").read_bytes()
    synthetic_rna.manifest["files"][0]["md5"] = hashlib.md5(content).hexdigest()  # noqa: S324
    synthetic_rna.write_manifest()
    snapshot = await synthetic_rna.build()
    fingerprints = snapshot.artifacts[0].fingerprints
    assert {fp.algorithm for fp in fingerprints} == {"md5", "sha256"}
    assert {fp.scope for fp in fingerprints} == {"manifest_declared", "capture_bytes"}
    assert all(fp.verified_at == NOW for fp in fingerprints)
    assert snapshot.artifacts[0].source.observed_at is None


async def test_unbound_file_origin_is_unknown(synthetic_rna: SyntheticRNA) -> None:
    synthetic_rna.manifest["platform"] = {}
    synthetic_rna.write_manifest()
    snapshot = await synthetic_rna.build()
    assert (
        snapshot.artifacts[0].source.verification_status == EvidenceStatus.VERIFIED
    )  # current bytes
    assert snapshot.artifacts[0].origin.verification_status == EvidenceStatus.NOT_RECORDED
    assert snapshot.provenance[0].relation == "source_unknown"
    assert snapshot.provenance[0].object_reference is None


async def test_history_is_not_replaced_by_current_environment(
    synthetic_rna: SyntheticRNA,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_VERSION", "CURRENT-CHANGED-9.9.9")
    (synthetic_rna.deliver / "environment.json").write_text(
        '{"python_version":"CURRENT-CHANGED-9.9.9","software":{"STAR":"9.9.9"}}'
    )
    snapshot = await synthetic_rna.build()
    facts = {item.field: item for item in snapshot.environment}
    assert facts["pipeline_declared_version"].value == "v0.1.9"
    assert facts["pipeline_declared_version"].source.verification_status == EvidenceStatus.ESTIMATED
    assert (
        facts["observed_software_versions"].source.verification_status
        == EvidenceStatus.NOT_RECORDED
    )
    assert "CURRENT-CHANGED" not in snapshot.model_dump_json()


async def test_estimated_timing_and_directory_never_become_verified(
    synthetic_rna: SyntheticRNA,
) -> None:
    (synthetic_rna.deliver / "qc").mkdir()
    synthetic_rna.manifest["files"].append({"path": "qc/", "type": "dir", "category": "qc"})
    synthetic_rna.write_manifest()
    snapshot = await synthetic_rna.build()
    assert snapshot.execution_steps[1].duration_seconds == 42
    assert snapshot.execution_steps[1].source.verification_status == EvidenceStatus.ESTIMATED
    assert snapshot.artifacts[-1].source.verification_status == EvidenceStatus.ESTIMATED
    assert snapshot.quality_gates[0].decision is None


async def test_roundtrip_deep_immutability_and_digest_validation(
    synthetic_rna: SyntheticRNA,
) -> None:
    snapshot = await synthetic_rna.build()
    encoded = canonical_serialization(snapshot)
    assert ReportSnapshot.model_validate_json(encoded) == snapshot
    assert isinstance(snapshot.artifacts, tuple)
    with pytest.raises(PydanticValidationError):
        snapshot.artifacts[0].source.verification_status = EvidenceStatus.NOT_RECORDED
    data = json.loads(encoded)
    data["inputs"][0]["value"] = "atac_seq"
    with pytest.raises(PydanticValidationError, match="digest mismatch"):
        ReportSnapshot.model_validate(data)
    data = json.loads(encoded)
    data["schema_version"] = "cygnusx.report_snapshot.v2"
    with pytest.raises(PydanticValidationError):
        ReportSnapshot.model_validate(data)
    data = json.loads(encoded)
    data["evidence_coverage"]["verified"] += 1
    with pytest.raises(PydanticValidationError, match="coverage"):
        ReportSnapshot.model_validate(data)


async def test_stable_digest_and_new_fact_versions(synthetic_rna: SyntheticRNA) -> None:
    first = await synthetic_rna.build()
    later = await synthetic_rna.build(now=NOW + timedelta(hours=1))
    assert first.snapshot_digest == later.snapshot_digest
    assert canonical_serialization(first) != canonical_serialization(later)
    archived = first.model_dump(mode="json")
    archived["report_id"] = str(uuid4())
    archived["immutable_version"] = 2
    assert ReportSnapshot.model_validate(archived).snapshot_digest == first.snapshot_digest
    (synthetic_rna.deliver / "counts.tsv").write_text("changed")
    changed = await synthetic_rna.build()
    assert changed.snapshot_digest != first.snapshot_digest
    assert first.artifacts[0].source.verification_status == EvidenceStatus.VERIFIED
    assert changed.artifacts[0].source.verification_status == EvidenceStatus.VERIFICATION_FAILED


async def test_secret_canaries_are_not_exported(synthetic_rna: SyntheticRNA) -> None:
    canary = "CANARY-SUPER-SECRET-123"
    synthetic_rna.records.task.parameters.update(
        {
            "api_key": canary,
            "headers": {"Authorization": canary},
            "sample_name": canary,
            "cores": canary,
            "path": f"https://example.invalid/?token={canary}",
            "password": canary,
            "nested": {"token": canary},
        }
    )
    synthetic_rna.records.task.logs = [{"prompt": canary}]
    synthetic_rna.records.task.error_message = canary
    synthetic_rna.manifest["extra"] = {"credentials": canary}
    synthetic_rna.manifest["run"]["output_dir"] = canary
    synthetic_rna.manifest["files"][0]["name"] = canary
    synthetic_rna.write_manifest()
    snapshot = await synthetic_rna.build()
    encoded = snapshot.model_dump_json()
    assert canary not in encoded
    assert str(synthetic_rna.factory.data_root) not in encoded


@pytest.mark.parametrize(
    "path", ["../counts.tsv", "/etc/passwd", "..\\secret", "../../other-user/file"]
)
async def test_manifest_paths_rejected(synthetic_rna: SyntheticRNA, path: str) -> None:
    synthetic_rna.manifest["files"][0]["path"] = path
    synthetic_rna.write_manifest()
    with pytest.raises(AuthorizationError):
        await synthetic_rna.build()


async def test_symlink_escape_rejected(synthetic_rna: SyntheticRNA, tmp_path: Path) -> None:
    target = tmp_path / "private.txt"
    target.write_text("secret")
    artifact = synthetic_rna.deliver / "counts.tsv"
    artifact.unlink()
    artifact.symlink_to(target)
    with pytest.raises(AuthorizationError):
        await synthetic_rna.build()


async def test_task_work_path_cannot_cross_owner(
    synthetic_rna: SyntheticRNA, tmp_path: Path
) -> None:
    synthetic_rna.records.task.work_dir = str(tmp_path)
    with pytest.raises(AuthorizationError):
        await synthetic_rna.build()


async def test_manifest_identity_conflict_rejected(synthetic_rna: SyntheticRNA) -> None:
    synthetic_rna.manifest["platform"]["task_id"] = str(uuid4())
    synthetic_rna.write_manifest()
    with pytest.raises(ConflictError):
        await synthetic_rna.build()


@pytest.mark.parametrize("invalid", ["json", "version", "size", "hash"])
async def test_bad_manifest_fails_explicitly_without_raw_errors(
    synthetic_rna: SyntheticRNA, invalid: str
) -> None:
    if invalid == "version":
        synthetic_rna.manifest["manifest_version"] = "99"
    elif invalid == "size":
        synthetic_rna.manifest["files"][0]["size_bytes"] = "secret-not-integer"
    elif invalid == "hash":
        synthetic_rna.manifest["files"][0]["md5"] = "secret-invalid-md5"
    synthetic_rna.write_manifest()
    if invalid == "json":
        (synthetic_rna.deliver / "result_manifest.json").write_text("secret-not-json")
    snapshot = await synthetic_rna.build()
    missing = next(item for item in snapshot.missing_evidence if item.field == "result_manifest")
    assert missing.source.verification_status == EvidenceStatus.VERIFICATION_FAILED
    assert "secret-" not in snapshot.model_dump_json()


async def test_conflicting_manifests_are_not_silently_selected(synthetic_rna: SyntheticRNA) -> None:
    work = Path(synthetic_rna.records.task.work_dir)
    (work / "result_manifest.json").write_text(json.dumps(synthetic_rna.manifest))
    with pytest.raises(ConflictError):
        await synthetic_rna.build()


async def test_database_adapter_is_owner_scoped_and_never_writes(
    synthetic_rna: SyntheticRNA,
) -> None:
    db = MagicMock()
    db.no_autoflush = nullcontext()
    db.scalar = AsyncMock(return_value=synthetic_rna.records.task)
    db.scalars = AsyncMock(side_effect=[MagicMock(all=lambda: []), MagicMock(all=lambda: [])])
    source = DatabaseTaskEvidenceSource(cast(AsyncSession, db))
    result = await source.read(synthetic_rna.owner, synthetic_rna.records.task.id)
    assert result.run is None
    task_query = str(db.scalar.await_args.args[0])
    assert "tasks.user_id =" in task_query and "tasks.id =" in task_query
    run_query = str(db.scalars.await_args_list[0].args[0])
    assert "platform_runs.user_id =" in run_query and "platform_runs.task_id =" in run_query
    for method in (db.flush, db.commit, db.add, db.delete, db.execute):
        method.assert_not_called()


async def test_database_adapter_hides_missing_or_foreign_task() -> None:
    db = MagicMock(no_autoflush=nullcontext())
    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await DatabaseTaskEvidenceSource(cast(AsyncSession, db)).read(uuid4(), uuid4())
    db.scalars.assert_not_called()


async def test_truncated_events_warn_not_claim_complete(synthetic_rna: SyntheticRNA) -> None:
    synthetic_rna.records = replace(synthetic_rna.records, events_truncated=True)
    snapshot = await synthetic_rna.build()
    assert "run_events_truncated_at_1000" in snapshot.warnings
    assert any(item.field == "execution_steps.complete" for item in snapshot.missing_evidence)
