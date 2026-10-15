"""Phase 2 delivery contracts; no scientific computation is executed."""

import asyncio
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, TypeVar
from uuid import uuid4

import pytest

from cygnusx.application.services.research_delivery_service import (
    DeliveryInput,
    ResearchDeliveryBuilder,
)
from tests.unit.test_report_snapshot import synthetic_rna as snapshot_synthetic_rna

pytestmark = pytest.mark.unit
P = ParamSpec("P")
T = TypeVar("T")


@pytest.fixture(autouse=True)
def inline_file_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    async def inline(function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline)


@pytest.fixture
def synthetic_rna(tmp_path: Path):
    return snapshot_synthetic_rna.__wrapped__(tmp_path)


@pytest.mark.asyncio
async def test_delivery_package_is_offline_and_partial_when_a_format_is_missing(
    synthetic_rna,
    tmp_path: Path,
) -> None:
    snapshot = await synthetic_rna.build()
    build = ResearchDeliveryBuilder().build(
        snapshot=snapshot,
        snapshot_id=uuid4(),
        output_root=tmp_path,
        inputs=(
            DeliveryInput(
                "Scientific_Report.html", "<html>中文</html>".encode(), "html", "report-1"
            ),
            DeliveryInput("Scientific_Report.pdf", None, "pdf", "report-2"),
            DeliveryInput("ReportSnapshot.json", b'{"snapshot":true}', "json", "snapshot"),
        ),
    )
    assert build.manifest.evidence_status == "partial"
    assert "Scientific_Report.pdf" in build.manifest.missing_files
    assert (build.directory / "README.md").exists()
    assert (build.directory / "ReportSnapshot.json").exists()
    with zipfile.ZipFile(build.zip_path) as archive:
        names = set(archive.namelist())
        assert "Scientific_Report.html" in names
        assert "Scientific_Report.pdf" not in names
        assert "ReportSnapshot.json" in names
        assert "EvidenceManifest.json" in names
        assert "checksums.sha256" in names
        assert ".." not in {part for name in names for part in Path(name).parts}
    verified = ResearchDeliveryBuilder.verify_package(build.zip_path)
    assert verified.package_id == build.package_id


@pytest.mark.asyncio
async def test_delivery_rejects_zip_slip_name(tmp_path: Path, synthetic_rna) -> None:
    snapshot = await synthetic_rna.build()
    with pytest.raises(ValueError, match="文件名非法"):
        ResearchDeliveryBuilder().build(
            snapshot=snapshot,
            snapshot_id=uuid4(),
            output_root=tmp_path,
            inputs=(DeliveryInput("../secret.txt", b"x", "txt", "bad"),),
        )


@pytest.mark.asyncio
async def test_manifest_is_machine_readable(tmp_path: Path, synthetic_rna) -> None:
    snapshot = await synthetic_rna.build()
    build = ResearchDeliveryBuilder().build(
        snapshot=snapshot,
        snapshot_id=uuid4(),
        output_root=tmp_path,
        inputs=(DeliveryInput("README-source.txt", b"source", "txt", "source"),),
    )
    manifest = json.loads((build.directory / "EvidenceManifest.json").read_text())
    assert manifest["manifest_schema_version"] == "cygnusx.evidence_manifest.v1"
    assert manifest["snapshot_digest"] == snapshot.snapshot_digest
    assert manifest["validation_status"] == "validated"


@pytest.mark.asyncio
async def test_tampered_delivery_is_rejected(tmp_path: Path, synthetic_rna) -> None:
    snapshot = await synthetic_rna.build()
    build = ResearchDeliveryBuilder().build(
        snapshot=snapshot,
        snapshot_id=uuid4(),
        output_root=tmp_path,
        inputs=(DeliveryInput("source.txt", b"source", "txt", "source"),),
    )
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(build.zip_path) as source, zipfile.ZipFile(tampered, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "source.txt":
                data = b"tampered"
            target.writestr(item, data)
    with pytest.raises(ValueError, match="完整性校验失败"):
        ResearchDeliveryBuilder.verify_package(tampered)
