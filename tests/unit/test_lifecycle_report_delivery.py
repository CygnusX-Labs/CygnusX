"""RI04 real SQLite + real ReportService + archive bytes, no research execution."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cygnusx.application.services.report_service import ReportService
from cygnusx.application.services.research_delivery_service import ResearchDeliveryBuilder
from cygnusx.core.exceptions import ConflictError, NotFoundError
from cygnusx.infrastructure.database.models.report import (
    ReportFileModel,
    ReportModel,
    ReportSnapshotModel,
)
from tests.integration.test_reproducible_report_isolated import (
    as_async,
)
from tests.integration.test_reproducible_report_isolated import (
    isolated_db as isolated_db,
)
from tests.unit.test_report_snapshot import (
    inline_file_capture as inline_file_capture,
)
from tests.unit.test_report_snapshot import (
    synthetic_rna as synthetic_rna,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
async def delivery(isolated_db, synthetic_rna, monkeypatch):
    db = as_async(isolated_db)

    async def scalar(query):
        return isolated_db.session.scalar(query)

    monkeypatch.setattr(db, "scalar", scalar, raising=False)
    snapshot = await synthetic_rna.build()
    now = datetime.now(UTC)
    frozen = ReportSnapshotModel(
        id=uuid4(),
        user_id=synthetic_rna.owner,
        task_id=synthetic_rna.records.task.id,
        run_id=snapshot.source_execution.run_id,
        schema_version=snapshot.schema_version,
        snapshot_digest=snapshot.snapshot_digest,
        payload=snapshot.model_dump(mode="json"),
        captured_at=now,
    )
    db.add(frozen)
    root = synthetic_rna.factory.user_root(str(synthetic_rna.owner)) / "report-test"
    root.mkdir(parents=True, exist_ok=True)
    reports = {}
    for kind, text in [
        ("scientific", b"<html>ACTUAL SCIENCE</html>"),
        ("reproducibility", b"<html>ACTUAL EVIDENCE</html>"),
    ]:
        path = root / f"{kind}.html"
        path.write_bytes(text)
        report = ReportModel(
            id=uuid4(),
            user_id=synthetic_rna.owner,
            task_id=synthetic_rna.records.task.id,
            flow_id="rna_seq",
            status="completed",
            report_kind=kind,
            snapshot_id=frozen.id if kind == "reproducibility" else None,
            created_at=now - timedelta(seconds=10),
            completed_at=now - timedelta(seconds=5),
            version=1,
            files=[
                ReportFileModel(
                    id=uuid4(),
                    name=path.name,
                    type="html",
                    size=len(text),
                    path=str(path),
                    is_primary=True,
                    sha256=hashlib.sha256(text).hexdigest(),
                )
            ],
        )
        reports[kind] = report
        db.add(report)
    await db.flush()
    service = ReportService(db)
    return SimpleNamespace(
        db=db,
        sql=isolated_db.session,
        owner=synthetic_rna.owner,
        reports=reports,
        snapshot=frozen,
        service=service,
    )


def archive(report):
    path = next(f.path for f in report.files if f.type == "zip")
    return zipfile.ZipFile(path)


@pytest.mark.parametrize("entry", ["scientific", "reproducibility"])
async def test_ri04_01_02_both_real_service_entry_roles(delivery, entry):
    env = delivery
    result = await env.service.build_delivery_package(env.reports[entry].id, str(env.owner))
    with archive(result) as z:
        assert z.read("Scientific_Report.html") == b"<html>ACTUAL SCIENCE</html>"
        assert z.read("Reproducibility_Record.html") == b"<html>ACTUAL EVIDENCE</html>"
    again = await env.service.build_delivery_package(env.reports[entry].id, str(env.owner))
    assert again.id == result.id
    ResearchDeliveryBuilder.verify_package(
        next(Path(f.path) for f in result.files if f.type == "zip")
    )


@pytest.mark.parametrize("missing", ["scientific", "reproducibility"])
async def test_ri04_03_04_missing_reports_are_partial_not_fabricated(delivery, missing):
    env = delivery
    await env.db.delete(env.reports[missing])
    await env.db.flush()
    entry = "scientific" if missing == "reproducibility" else "reproducibility"
    result = await env.service.build_delivery_package(env.reports[entry].id, str(env.owner))
    with archive(result) as z:
        manifest = json.loads(z.read("EvidenceManifest.json"))
        assert manifest["evidence_status"] == "partial"
        assert (
            "Scientific_Report.html" if missing == "scientific" else "Reproducibility_Record.html"
        ) not in z.namelist()
        if missing == "reproducibility":
            assert manifest["snapshot_id"] is None
            assert "ReportSnapshot.json" not in z.namelist()


async def test_ri04_05_wrong_owner(delivery):
    with pytest.raises(NotFoundError):
        await delivery.service.build_delivery_package(
            delivery.reports["scientific"].id, str(uuid4())
        )


@pytest.mark.parametrize("mutation", ["owner", "task", "newer", "snapshot"])
async def test_ri04_06_07_inapplicable_peer_not_used(delivery, mutation):
    env = delivery
    science = env.reports["scientific"]
    if mutation == "owner":
        science.user_id = uuid4()
    if mutation == "task":
        science.task_id = uuid4()
    if mutation == "newer":
        science.completed_at = datetime.now(UTC) + timedelta(days=1)
    if mutation == "snapshot":
        science.result_observation_id = uuid4()
    await env.db.flush()
    result = await env.service.build_delivery_package(
        env.reports["reproducibility"].id, str(env.owner)
    )
    with archive(result) as z:
        assert "Scientific_Report.html" not in z.namelist()


async def test_ri04_08_wrong_snapshot_task_rejected(delivery):
    env = delivery
    # Corrupt source association rather than updating immutable snapshot payload.
    env.reports["reproducibility"].snapshot_id = uuid4()
    await env.db.flush()
    with pytest.raises(ConflictError):
        await env.service.build_delivery_package(env.reports["reproducibility"].id, str(env.owner))


async def test_ri04_09_tampered_scientific_file_rejected(delivery):
    from pathlib import Path

    env = delivery
    await __import__("asyncio").to_thread(
        Path(env.reports["scientific"].files[0].path).write_bytes, b"changed"
    )
    with pytest.raises(ConflictError):
        await env.service.build_delivery_package(env.reports["scientific"].id, str(env.owner))


@pytest.mark.parametrize(
    "mode", ["duplicate", "extra", "traversal", "absolute", "symlink", "checksum", "oversized"]
)
async def test_ri04_10_11_12_zip_members_and_checksums(delivery, tmp_path, monkeypatch, mode):
    import stat
    import warnings

    env = delivery
    report = await env.service.build_delivery_package(env.reports["scientific"].id, str(env.owner))
    with archive(report) as original:
        members = [(info, original.read(info.filename)) for info in original.infolist()]
    target = tmp_path / "changed.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(target, "w") as z:
            for info, content in members:
                if mode == "checksum" and info.filename == "checksums.sha256":
                    content = b"broken"
                z.writestr(info, content)
            if mode == "duplicate":
                z.writestr(members[0][0].filename, members[0][1])
            if mode == "extra":
                z.writestr("unlisted.txt", b"x")
            if mode == "traversal":
                z.writestr("../x", b"x")
            if mode == "absolute":
                z.writestr("/x", b"x")
            if mode == "symlink":
                info = zipfile.ZipInfo("link")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, b"outside")
    if mode == "oversized":
        monkeypatch.setattr(ResearchDeliveryBuilder, "MAX_TOTAL_BYTES", 1)
    with pytest.raises(ValueError):
        ResearchDeliveryBuilder.verify_package(target)


async def test_delivery_never_submits_compute_and_reuses_cross_entry(delivery, monkeypatch):
    from unittest.mock import AsyncMock

    from cygnusx.application.services.task_service import TaskService

    forbidden = AsyncMock(side_effect=AssertionError("report must not execute research"))
    monkeypatch.setattr(TaskService, "submit", forbidden)
    first = await delivery.service.build_delivery_package(
        delivery.reports["scientific"].id, str(delivery.owner)
    )
    second = await delivery.service.build_delivery_package(
        delivery.reports["reproducibility"].id, str(delivery.owner)
    )
    assert first.id == second.id
    forbidden.assert_not_called()


async def test_scientific_explicit_different_snapshot_refused(delivery):
    delivery.reports["scientific"].snapshot_id = uuid4()
    await delivery.db.flush()
    with pytest.raises(ConflictError):
        await delivery.service.build_delivery_package(
            delivery.reports["reproducibility"].id, str(delivery.owner)
        )


async def test_applicable_older_scientific_version_selected(delivery):
    env = delivery
    newer = ReportModel(
        id=uuid4(),
        user_id=env.owner,
        task_id=env.reports["scientific"].task_id,
        flow_id="rna_seq",
        report_kind="scientific",
        status="completed",
        version=2,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC) + timedelta(days=1),
        files=[],
    )
    env.db.add(newer)
    await env.db.flush()
    result = await env.service.build_delivery_package(
        env.reports["reproducibility"].id, str(env.owner)
    )
    with archive(result) as z:
        assert z.read("Scientific_Report.html") == b"<html>ACTUAL SCIENCE</html>"
