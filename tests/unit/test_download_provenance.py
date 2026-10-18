"""Source manifests and synthetic operator evidence, not Docker/Worker attestation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from cygnusx.infrastructure.download import provenance as module
from cygnusx.tools.download.config import DownloadBinariesConfig, DownloadConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    cargo = root / "pipelines/EBIDownload/crates/ebidownload-cli/Cargo.toml"
    cargo.parent.mkdir(parents=True)
    cargo.write_text('[package]\nversion="1.4.0"\n')
    for name in [
        "uv.lock",
        "pipelines/EBIDownload/Cargo.lock",
        "deploy/docker/Dockerfile.worker",
        "deploy/docker/docker-compose.worker.yml",
        "src/cygnusx/infrastructure/celery_app/tasks/download.py",
    ]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source fixture\n")
    monkeypatch.setattr(
        module, "_git", lambda path, *args: "a" * 40 if args[0] == "rev-parse" else ""
    )
    storage = tmp_path / "data"
    paths = {
        name: str(storage / "bin" / name)
        for name in ["ebi", "ebi_config", "aria2c", "ossutil", "tosutil", "obsutil"]
    }
    config = DownloadConfig(binaries=DownloadBinariesConfig(**paths))
    return root, config, SimpleNamespace(storage_path=str(storage)), storage


def observation(source):
    root, config, settings, storage = source
    binaries = []
    for name, path in config.binaries.model_dump().items():
        if name == "ebi_config":
            continue
        binaries.append(
            dict(
                name=name,
                path=path,
                version="ebidownload-cli 1.4.0" if name == "ebi" else "1.0.0",
                sha256="b" * 64,
                help_sha256="c" * 64,
                download_methods=["aws", "ftp", "auto", "prefetch"] if name == "ebi" else [],
            )
        )
    for name in ["wget", "fasterq_dump"]:
        binaries.append(
            dict(
                name=name,
                path="/usr/bin/" + name,
                version="1.0.0",
                sha256="b" * 64,
                help_sha256="c" * 64,
            )
        )
    return dict(
        source_sha="a" * 40,
        downloader_sha="a" * 40,
        image_digest="sha256:" + "d" * 64,
        uid=1000,
        gid=1000,
        rust_toolchain="rustc 1.90.0",
        worker_code_sha256=hashlib.sha256(
            (root / "src/cygnusx/infrastructure/celery_app/tasks/download.py").read_bytes()
        ).hexdigest(),
        mounts=[
            dict(source_path=str(storage), target_path=str(storage), read_only=False),
            dict(
                source_path=str(storage / "bin"), target_path=str(storage / "bin"), read_only=True
            ),
        ],
        binaries=binaries,
    )


def test_source_manifest_never_claims_host_or_worker_pass(source):
    root, config, settings, storage = source
    result = module.build_source_manifest(root, config, settings, storage)
    assert result["scope"] == "SOURCE_ONLY"
    assert result["runtime_status"] == "BLOCKED" and result["release_ready"] is False
    assert result["worker_observation"] is None
    assert "WORKER_OBSERVATION_MISSING" in result["reason_codes"]
    assert "download_method" not in json.dumps(result["source"])


@pytest.mark.parametrize(
    "change,reason",
    [
        ("method", "EBI_CLI_METHOD_DRIFT"),
        ("version", "EBI_VERSION_DRIFT"),
        ("binary_path", "BINARY_PATH_DRIFT"),
        ("source", "WORKER_SOURCE_DRIFT"),
        ("code", "WORKER_CODE_DRIFT"),
        ("mount", "WORKER_STORAGE_MOUNT_UNVERIFIED"),
        ("writable_bin", "BINARY_MOUNT_NOT_READONLY"),
        ("missing_binary", "BINARY_OBSERVATION_MISSING"),
    ],
)
def test_runtime_drift_is_explicit_and_cannot_open_execution(source, change, reason):
    root, config, settings, storage = source
    data = observation(source)
    if change == "method":
        data["binaries"][0]["download_methods"] = ["auto"]
    elif change == "version":
        data["binaries"][0]["version"] = "polariseq 1.4.3"
    elif change == "binary_path":
        data["binaries"][0]["path"] = "/different/ebi"
    elif change == "source":
        data["downloader_sha"] = "f" * 40
    elif change == "code":
        data["worker_code_sha256"] = "f" * 64
    elif change == "writable_bin":
        data["mounts"][1]["read_only"] = False
    elif change == "missing_binary":
        data["binaries"] = data["binaries"][:-1]
    else:
        data["mounts"] = []
    result = module.build_source_manifest(
        root, config, settings, storage, module.WorkerObservation.model_validate(data)
    )
    assert result["worker_provenance_state"] == "CONFLICT"
    assert reason in result["reason_codes"]
    assert result["runtime_status"] == "BLOCKED" and result["release_ready"] is False


def test_even_consistent_operator_observation_is_not_protocol_certification(source):
    root, config, settings, storage = source
    result = module.build_source_manifest(
        root,
        config,
        settings,
        storage,
        module.WorkerObservation.model_validate(observation(source)),
    )
    assert result["worker_provenance_state"] == "CONSISTENT_OBSERVATION"
    assert result["runtime_status"] == "BLOCKED" and result["release_ready"] is False
    assert "PROTOCOL_RUNTIME_NOT_TESTED" in result["reason_codes"]


def test_root_drift_and_no_secret_configuration_dump(source, monkeypatch):
    root, config, settings, storage = source
    settings.api_key = "must-not-be-exported"
    result = module.build_source_manifest(root, config, settings, storage / "different")
    assert "STORAGE_ROOT_MISMATCH" in result["reason_codes"]
    assert "must-not-be-exported" not in json.dumps(result)


def test_invalid_operator_record_is_not_echoed_by_cli(tmp_path):
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"secret_token": "must-not-appear-in-output"}))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/inspect_download_runtime.py",
            "--output",
            str(tmp_path / "out.json"),
            "--worker-observation",
            str(record),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "DOWNLOAD_MANIFEST_INVALID" in result.stderr
    assert "must-not-appear-in-output" not in result.stderr + result.stdout
    assert not (tmp_path / "out.json").exists()


def test_yaml_binary_paths_override_specific_env_then_storage_defaults(monkeypatch, tmp_path):
    from cygnusx.tools.download import config as config_module

    settings = SimpleNamespace(
        storage_path=str(tmp_path),
        ebi_download_binary="/explicit-env/EBIDownload",
        ebi_download_yaml="",
        direct_download_binary="/explicit-env/aria2c",
        cloud_ossutil_binary="",
        cloud_tosutil_binary="",
        cloud_obsutil_binary="",
    )
    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    defaults = DownloadBinariesConfig()
    assert defaults.ebi == "/explicit-env/EBIDownload"
    assert defaults.aria2c == "/explicit-env/aria2c"
    assert defaults.ossutil == str(tmp_path / "bin/ossutil")
    assert (
        DownloadBinariesConfig(ebi="/explicit-yaml/EBIDownload").ebi == "/explicit-yaml/EBIDownload"
    )
