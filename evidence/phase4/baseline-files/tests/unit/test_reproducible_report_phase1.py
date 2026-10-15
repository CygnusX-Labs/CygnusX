"""Evidence-delivery tests use synthetic RNA records; no scientific rerun claims."""

import hashlib
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateIndex

from cygnusx.application.schemas.report_snapshot import FactEvidence, freeze_snapshot
from cygnusx.application.services.report_audit_renderer import render_audit_report
from cygnusx.application.services.report_snapshot_manifest import (
    CaptureBudgetError,
    current_hashes,
    open_evidence_file,
)
from cygnusx.application.services.reproducible_report_service import (
    ReproducibleReportService,
    dispatch_report_job,
    run_reproducible_report,
)
from cygnusx.core.exceptions import AuthorizationError, ConflictError, NotFoundError
from cygnusx.infrastructure.celery_app.tasks.reports import failure_details, record_failure
from cygnusx.infrastructure.database.models.report import ReportGenerationJobModel
from tests.unit.test_report_snapshot import SyntheticRNA
from tests.unit.test_report_snapshot import inline_file_capture as inline_file_capture
from tests.unit.test_report_snapshot import synthetic_rna as synthetic_rna

pytestmark = pytest.mark.unit


class Elements(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


@pytest.mark.asyncio
async def test_renderer_has_eight_actual_modules_offline_and_explicit_gaps(
    synthetic_rna: SyntheticRNA,
) -> None:
    snapshot = await synthetic_rna.build()
    html = render_audit_report(snapshot)
    parsed = Elements()
    parsed.feed(html)
    assert [attrs["id"] for tag, attrs in parsed.tags if tag == "section"] == [
        f"m{i}" for i in range(1, 9)
    ]
    assert [attrs["href"] for tag, attrs in parsed.tags if tag == "a"] == [
        f"#m{i}" for i in range(1, 9)
    ]
    assert not any(tag in {"script", "iframe", "link", "img", "form"} for tag, _ in parsed.tags)
    assert not any(key.startswith("on") for _, attrs in parsed.tags for key in attrs)
    assert "not_run" in html and "复现成功" not in html
    assert "not_recorded" in html and "证据不完整" in html
    assert str(snapshot.source_execution.task_id) in html
    assert "capture_bytes" in html and "sha256" in html
    assert str(snapshot.generated_at) in html
    assert "default-src 'none'" in html
    assert str(synthetic_rna.factory.data_root) not in html
    assert "QC 阈值：未记录。人工豁免：未记录。" in html


@pytest.mark.asyncio
async def test_renderer_escapes_every_untrusted_value_and_handles_many_artifacts(
    synthetic_rna: SyntheticRNA,
) -> None:
    snapshot = await synthetic_rna.build()
    payload = '<script>alert("x")</script><img src=x onerror=alert(1)>&'
    snapshot = freeze_snapshot(
        snapshot.model_copy(
            update={
                "snapshot_digest": None,
                "inputs": snapshot.inputs
                + (
                    FactEvidence(
                        field=payload, value=payload, source=snapshot.source_references[0]
                    ),
                ),
                "artifacts": snapshot.artifacts * 2000,
            }
        )
    )
    html = render_audit_report(snapshot, title=payload)
    parsed = Elements()
    parsed.feed(html)
    assert not any(tag in {"script", "img"} for tag, _ in parsed.tags)
    assert "&lt;script&gt;" in html and "&quot;x&quot;" in html
    assert html.count("capture_bytes") >= 2000
    assert render_audit_report(snapshot, title=payload) == html


@pytest.mark.asyncio
async def test_ready_job_is_not_republished() -> None:
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(status="ready")
    await run_reproducible_report(db, uuid4())
    db.commit.assert_not_awaited()
    db.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_rolls_back_and_redacts_exception() -> None:
    db = AsyncMock()
    job = SimpleNamespace(status="publishing", attempt_count=1)
    db.get.return_value = job
    await record_failure(db, uuid4(), OSError("secret-token /internal/private/path"))
    db.rollback.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert job.status == "failed" and job.retryable
    assert job.error_code == "storage_or_timeout"
    assert "secret-token" not in job.error_message and "/internal" not in job.error_message
    assert job.finished_at is not None


@pytest.mark.parametrize(
    "exc",
    [
        AuthorizationError(),
        ConflictError(),
        NotFoundError(),
        ValueError("secret"),
        RuntimeError("secret"),
    ],
)
def test_permanent_failures_are_not_automatically_retried(exc: Exception) -> None:
    code, message, retryable = failure_details(exc)
    assert code and "secret" not in message and not retryable


@pytest.mark.asyncio
async def test_dispatch_failure_preserves_durable_outbox(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("redis://secret")

    monkeypatch.setattr(
        "cygnusx.infrastructure.celery_app.tasks.reports.generate_reproducible_report.apply_async",
        fail,
    )
    await dispatch_report_job(uuid4())


@pytest.mark.asyncio
async def test_cross_owner_generation_and_status_hidden() -> None:
    db = AsyncMock()
    db.scalar.return_value = None
    service = ReproducibleReportService(db)
    with pytest.raises(NotFoundError):
        await service.enqueue(str(uuid4()), uuid4())
    with pytest.raises(NotFoundError):
        await service.get_job(str(uuid4()), uuid4())
    with pytest.raises(NotFoundError):
        await service.get_snapshot_for_report(str(uuid4()), uuid4())
    db.commit.assert_not_awaited()


def test_database_uniqueness_protects_active_generation() -> None:
    index = next(
        i
        for i in ReportGenerationJobModel.__table__.indexes
        if i.name == "uq_report_generation_jobs_active"
    )
    ddl = str(CreateIndex(index).compile(dialect=dialect()))
    assert "UNIQUE" in ddl and "WHERE status IN" in ddl and "publishing" in ddl


def test_fd_open_refuses_parent_and_leaf_symlink_swaps(tmp_path: Path) -> None:
    outside = tmp_path / "other-owner"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"credential")
    permitted = tmp_path / "owner"
    permitted.mkdir()
    (permitted / "leaf").symlink_to(outside / "secret.txt")
    (permitted / "swapped").symlink_to(outside, target_is_directory=True)
    for path in (permitted / "leaf", permitted / "swapped" / "secret.txt"):
        with pytest.raises(OSError), open_evidence_file(path):
            pytest.fail("must not open another owner file")


def test_hash_budget_does_not_produce_verified_digest(tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"12345")
    with pytest.raises(CaptureBudgetError):
        current_hashes(path, byte_limit=4)
    with pytest.raises(CaptureBudgetError):
        current_hashes(path, deadline=0)
    size, sha, _ = current_hashes(path, byte_limit=5)
    assert size == 5 and sha == hashlib.sha256(b"12345").hexdigest()


@pytest.mark.asyncio
async def test_phase0_snapshot_without_optional_display_name_keeps_digest(
    synthetic_rna: SyntheticRNA,
) -> None:
    from cygnusx.application.schemas.report_snapshot import ReportSnapshot

    snapshot = await synthetic_rna.build()
    data = snapshot.model_dump(mode="json")
    for artifact in data["artifacts"]:
        artifact.pop("display_name", None)
    data["snapshot_digest"] = None
    old = freeze_snapshot(ReportSnapshot.model_validate(data))
    encoded = old.model_dump(mode="json")
    for artifact in encoded["artifacts"]:
        artifact.pop("display_name", None)
    assert ReportSnapshot.model_validate(encoded).snapshot_digest == old.snapshot_digest


@pytest.mark.parametrize("locked", [True, False])
@pytest.mark.asyncio
async def test_worker_connection_lock_fences_duplicate_deliveries(
    monkeypatch: pytest.MonkeyPatch,
    locked: bool,
) -> None:
    from unittest.mock import MagicMock

    from cygnusx.infrastructure.celery_app.tasks.reports import _run

    db = AsyncMock()
    job = SimpleNamespace(task_id=uuid4(), status="queued", attempt_count=0)
    db.get.return_value = job
    db.scalar.return_value = locked
    db.__aenter__.return_value = db
    connection = AsyncMock()
    engine = MagicMock()
    engine.connect.return_value = connection
    engine.dispose = AsyncMock()
    run = AsyncMock()
    monkeypatch.setattr(
        "cygnusx.infrastructure.database.session.create_unpooled_engine", lambda: engine
    )
    monkeypatch.setattr(
        "cygnusx.infrastructure.celery_app.tasks.reports.AsyncSession", lambda **kwargs: db
    )
    monkeypatch.setattr(
        "cygnusx.application.services.reproducible_report_service.run_reproducible_report", run
    )
    result = await _run(uuid4())
    assert "pg_try_advisory_lock" in str(db.scalar.await_args.args[0])
    if locked:
        run.assert_awaited_once()
        assert "pg_advisory_unlock" in str(db.execute.await_args.args[0])
    else:
        run.assert_not_awaited()
        db.execute.assert_not_awaited()
        assert result["status"] == "busy"
    engine.dispose.assert_awaited_once()


def test_migration_sql_matches_immutable_model_contract() -> None:
    import importlib.util
    import io

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path("alembic/versions/reportauditphase1_add_reproducible_report_tables.py")
    spec = importlib.util.spec_from_file_location("report_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    assert "CREATE TRIGGER report_snapshots_immutable" in sql
    assert "BEFORE UPDATE ON report_snapshots" in sql
    assert "uq_report_generation_jobs_active" in sql
    assert "uq_reports_snapshot_template" in sql
    assert "RESTRICT" in sql and "sha256" in sql


def test_local_archive_atomic_write_refuses_redirected_parent(tmp_path: Path) -> None:
    from cygnusx.application.services.report_archive import _atomic_local_write, read_local_archive

    owner = tmp_path / "owner"
    owner.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    outside = other / "index.html"
    outside.write_bytes(b"private")
    (owner / "redirected").symlink_to(other, target_is_directory=True)
    with pytest.raises(OSError):
        _atomic_local_write(owner / "redirected" / "index.html", b"new")
    assert outside.read_bytes() == b"private"
    target = owner / "index.html"
    _atomic_local_write(target, b"<html>complete</html>")
    assert read_local_archive(target) == b"<html>complete</html>"
    assert not list(owner.glob(".*.publishing"))


@pytest.mark.asyncio
async def test_object_archive_uses_completed_stream_and_verifies_bytes(
    synthetic_rna: SyntheticRNA,
) -> None:
    from unittest.mock import MagicMock

    from cygnusx.application.services.report_archive import publish_archive, read_archive

    stored = {}
    backend = MagicMock()
    backend.name = "s3"

    async def write_stream(key, chunks):
        stored[key] = b"".join([chunk async for chunk in chunks])

    async def read(key):
        return stored[key]

    backend.write_stream = write_stream
    backend.read = read
    await publish_archive(backend, synthetic_rna.factory, "authorized/key.html", b"offline html")
    assert (
        await read_archive(backend, synthetic_rna.factory, "authorized/key.html") == b"offline html"
    )


@pytest.mark.asyncio
async def test_unicode_task_name_and_redaction_policy_are_explicit(synthetic_rna: SyntheticRNA) -> None:
    from cygnusx.application.services.report_snapshot_manifest import safe_display_label

    synthetic_rna.records.task.name = '水稻 转录组分析 (实验组 A)'
    snapshot = await synthetic_rna.build()
    assert snapshot.redaction_policy_version == 'owner_allowlist.v2'
    assert '水稻 转录组分析 (实验组 A)' in render_audit_report(snapshot)
    for label in ('/internal/private', 'api_key-supersecret', 'eyJabc123', 'a' * 64, '<script>alert(1)</script>'):
        assert safe_display_label(label) is None


@pytest.mark.asyncio
async def test_object_storage_errors_are_safely_retryable(synthetic_rna: SyntheticRNA) -> None:
    from unittest.mock import MagicMock

    from cygnusx.application.services.report_archive import publish_archive, read_archive
    from cygnusx.core.exceptions import BusinessError

    backend = MagicMock()
    backend.name = 's3'
    backend.write_stream = AsyncMock(side_effect=BusinessError('secret object storage failure'))
    backend.read = AsyncMock(side_effect=NotFoundError('private object storage path'))
    with pytest.raises(OSError) as failure:
        await publish_archive(backend, synthetic_rna.factory, 'authorized/key', b'html')
    assert failure_details(failure.value)[2]
    assert 'secret' not in failure_details(failure.value)[1]
    with pytest.raises(OSError):
        await read_archive(backend, synthetic_rna.factory, 'authorized/key')


@pytest.mark.asyncio
async def test_retry_budget_is_terminal_without_recollecting() -> None:
    from cygnusx.core.config import get_settings

    db = AsyncMock()
    job = SimpleNamespace(
        id=uuid4(), task_id=uuid4(), user_id=uuid4(), status='queued',
        attempt_count=get_settings().report_generation_max_attempts,
    )
    db.get.return_value = job
    db.scalar.return_value = job.task_id
    await run_reproducible_report(db, job.id)
    assert job.status == 'failed' and not job.retryable
    assert job.error_code == 'retry_exhausted' and job.finished_at
    db.execute.assert_not_awaited()


def test_celery_registration_routes_only_report_work() -> None:
    from cygnusx.infrastructure.celery_app.celery import celery_app
    from cygnusx.infrastructure.celery_app.tasks.reports import generate_reproducible_report

    name = 'cygnusx.infrastructure.celery_app.tasks.reports.generate_reproducible_report'
    assert generate_reproducible_report.name == name
    assert generate_reproducible_report.acks_late
    assert generate_reproducible_report.reject_on_worker_lost
    assert generate_reproducible_report.time_limit == 1950
    assert celery_app.conf.task_routes['cygnusx.infrastructure.celery_app.tasks.reports.*'] == {'queue': 'analysis'}
    assert celery_app.conf.beat_schedule['reproducible-report-reconcile']['task'].endswith('.reports.reconcile_report_jobs')
