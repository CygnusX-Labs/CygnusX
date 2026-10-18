"""The host probe reports visible prerequisites without certifying runtime safety."""

import json
import sys

import pytest
from scripts.check_download_execution_boundary import (
    _capability_report,
    inspect_dependencies,
    main,
)

pytestmark = pytest.mark.unit


def test_capability_report_decodes_effective_and_bounding_masks() -> None:
    report = _capability_report({"CapEff": "0000000000001000", "CapBnd": "0000000000001000"})
    assert report["CapEff"]["CAP_NET_ADMIN"] is True
    assert report["CapEff"]["CAP_SYS_ADMIN"] is False
    assert report["CapBnd"]["CAP_NET_ADMIN"] is True


def test_capability_report_fails_closed_on_malformed_masks() -> None:
    report = _capability_report({"CapEff": "not-hex", "CapBnd": ""})
    assert not any(report["CapEff"].values())
    assert not any(report["CapBnd"].values())


def test_host_probe_marks_visible_prerequisites_missing_without_certifying_runtime(
    tmp_path,
) -> None:
    report = inspect_dependencies(workdir_root=tmp_path)

    assert report["runtime_certified"] is False
    assert report["status"] == "VISIBLE_PREREQUISITES_MISSING"
    assert report["visible_preflight"]["checks"]["workdir_exists_and_writable"] is True
    assert report["visible_preflight"]["missing"]
    assert report["network_enforcement"] == "NOT_TESTED_BY_READ_ONLY_PROBE"


def test_visible_prerequisite_shape_never_claims_runtime_enforcement(tmp_path) -> None:
    report = inspect_dependencies(workdir_root=tmp_path)

    assert report["visible_preflight"]["limits"]
    assert "cgroup.kill behavior" in report["visible_preflight"]["limits"][0]
    assert report["atomic_rx_accounting"] == "NOT_TESTED"
    assert report["filesystem_quota"] == "NOT_TESTED_BY_READ_ONLY_PROBE"


def test_strict_cli_writes_diagnostics_then_exits_two_on_missing_prerequisites(
    tmp_path, monkeypatch
) -> None:
    output = tmp_path / "preflight.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_download_execution_boundary.py",
            "--workdir-root",
            str(tmp_path),
            "--cgroup-root",
            str(tmp_path / "missing-cgroup"),
            "--output",
            str(output),
            "--require-visible-prerequisites",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    report = json.loads(output.read_text())
    assert report["status"] == "VISIBLE_PREREQUISITES_MISSING"
    assert report["visible_preflight"]["missing"]
    assert report["runtime_certified"] is False
