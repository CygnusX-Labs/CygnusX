"""Phase 2 renderer contract tests; no RNA computation or network access."""

from pathlib import Path
from uuid import UUID

import pytest

from cygnusx.application.schemas.report_delivery import BioReportRenderRequest
from cygnusx.application.services.bioreport_adapter import BioReportAdapter
from cygnusx.application.services.report_audit_pdf_renderer import render_audit_pdf

pytestmark = pytest.mark.unit


def test_audit_pdf_renderer_emits_pdf_bytes() -> None:
    pdf = render_audit_pdf(b"<h1>Evidence</h1><p>not_run</p>")
    assert pdf.startswith(b"%PDF")


def test_bioreport_rejects_remote_html_assets(tmp_path: Path) -> None:
    source = tmp_path / "report.html"
    source.write_text('<html><script src="https://cdn.example.invalid/x.js"></script></html>')
    with pytest.raises(ValueError, match="外部资源"):
        BioReportAdapter.validate_html_dependencies(source)


def test_bioreport_accepts_embedded_html_assets(tmp_path: Path) -> None:
    source = tmp_path / "report.html"
    source.write_text('<html><script src="data:text/javascript,1"></script></html>')
    assert BioReportAdapter.validate_html_dependencies(source) == ()


def test_bioreport_rejects_symlinked_config_and_html(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}")
    config_link = tmp_path / "config.json"
    config_link.symlink_to(target)
    with pytest.raises(ValueError, match="配置不可用"):
        BioReportAdapter._safe_config(str(config_link), "pdf")

    html_target = tmp_path / "target.html"
    html_target.write_text("<html></html>")
    html_link = tmp_path / "report.html"
    html_link.symlink_to(html_target)
    with pytest.raises(ValueError, match="HTML 不可用"):
        BioReportAdapter.validate_html_dependencies(html_link)


def test_bioreport_adapter_uses_sanitized_config_without_ai(tmp_path: Path) -> None:
    config = tmp_path / "report.json"
    config.write_text('{"report":{"modules":["about","ai"]},"ai":{"enabled":true}}')
    executable = tmp_path / "fake-bioreport"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'report.pdf').write_bytes(b'%PDF-fake')\n"
    )
    executable.chmod(0o700)
    request = BioReportRenderRequest(
        task_id=UUID("00000000-0000-0000-0000-000000000001"),
        report_snapshot_id=UUID("00000000-0000-0000-0000-000000000002"),
        report_snapshot_digest="0" * 64,
        scientific_report_source=str(tmp_path / "missing.html"),
        report_config=str(config),
        output_format="pdf",
        renderer_version="bioreport-2.0.0",
        template_version="bioreport-v2",
    )
    result = BioReportAdapter(executable=str(executable)).render(request, tmp_path / "out")
    assert result.output.read_bytes() == b"%PDF-fake"
