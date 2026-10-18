"""Read-only operational provenance views; never a release authority or Agent tool."""

from __future__ import annotations

import hashlib
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cygnusx.core.config import Settings
from cygnusx.domain.download_contract import CLOUD_SCHEMES, DIRECT_SCHEMES, SRA_METHODS
from cygnusx.tools.download.config import DownloadConfig


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MountObservation(EvidenceModel):
    source_path: str
    target_path: str
    read_only: bool


class BinaryObservation(EvidenceModel):
    name: Literal[
        "ebi", "aria2c", "ossutil", "tosutil", "obsutil", "wget", "fasterq_dump", "prefetch"
    ]
    path: str
    version: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9 ._+()/-]+$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    help_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    download_methods: list[Literal["ftp", "aws", "prefetch", "auto"]] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def absolute_executable(cls, value: str) -> str:
        return operational_path(value)


class WorkerObservation(EvidenceModel):
    """Only trusted operators may supply this offline record; not accepted via REST/LLM."""

    source_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    downloader_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    worker_code_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    image_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    uid: int = Field(ge=1)
    gid: int = Field(ge=1)
    rust_toolchain: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9 ._+()/-]+$")
    binaries: list[BinaryObservation]
    mounts: list[MountObservation]


def operational_path(value: str) -> str:
    """Allow only filesystem locations, not credential/URL strings from misconfiguration."""
    if not Path(value).is_absolute() or any(c in value for c in ("://", "?", "#", "\n", "\r")):
        raise ValueError("runtime manifest requires absolute filesystem paths, not URLs")
    return value


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL, timeout=5
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_source_manifest(
    root: Path,
    config: DownloadConfig,
    settings: Settings,
    storage_root: Path,
    observed: WorkerObservation | None = None,
) -> dict[str, object]:
    """Inspect source/config only. No CLI execution, environment dump, socket or DB access."""
    downloader = root / "pipelines/EBIDownload"
    cargo = downloader / "crates/ebidownload-cli/Cargo.toml"
    version = tomllib.loads(cargo.read_text())["package"]["version"] if cargo.is_file() else None
    binaries = {k: operational_path(v) for k, v in config.binaries.model_dump().items()}
    settings_root = operational_path(settings.storage_path)
    factory_root = operational_path(str(storage_root))
    source_sha = _git(root, "rev-parse", "HEAD")
    downloader_sha = _git(downloader, "rev-parse", "HEAD")
    reasons = {"PROTOCOL_RUNTIME_NOT_TESTED", "AGENT_WRITE_GATE_CLOSED"}
    if Path(settings_root).resolve() != storage_root.resolve():
        reasons.add("STORAGE_ROOT_MISMATCH")
    evidence_state = "UNKNOWN"
    if observed is None:
        reasons.add("WORKER_OBSERVATION_MISSING")
    else:
        evidence_state = "CONSISTENT_OBSERVATION"
        if observed.source_sha != source_sha or observed.downloader_sha != downloader_sha:
            reasons.add("WORKER_SOURCE_DRIFT")
        if observed.worker_code_sha256 != _sha(
            root / "src/cygnusx/infrastructure/celery_app/tasks/download.py"
        ):
            reasons.add("WORKER_CODE_DRIFT")
        seen = {b.name: b for b in observed.binaries}
        if len(seen) != len(observed.binaries):
            reasons.add("BINARY_OBSERVATION_DUPLICATE")
        for name in ("ebi", "aria2c", "ossutil", "tosutil", "obsutil", "wget", "fasterq_dump"):
            if name not in seen:
                reasons.add("BINARY_OBSERVATION_MISSING")
        for name, binary in seen.items():
            if name in binaries and binary.path != binaries[name]:
                reasons.add("BINARY_PATH_DRIFT")
        ebi = seen.get("ebi")
        if ebi:
            if version is None or version not in ebi.version.split():
                reasons.add("EBI_VERSION_DRIFT")
            if not set(ebi.download_methods) >= SRA_METHODS:
                reasons.add("EBI_CLI_METHOD_DRIFT")
        for mount in observed.mounts:
            operational_path(mount.source_path)
            operational_path(mount.target_path)
        for name in ("ebi", "ossutil", "tosutil", "obsutil"):
            binary_path = Path(binaries[name])
            matching = [
                m for m in observed.mounts if binary_path.is_relative_to(Path(m.target_path))
            ]
            if not matching or not max(matching, key=lambda m: len(m.target_path)).read_only:
                reasons.add("BINARY_MOUNT_NOT_READONLY")
        if not any(m.target_path == factory_root for m in observed.mounts):
            reasons.add("WORKER_STORAGE_MOUNT_UNVERIFIED")
        if any(
            "DRIFT" in r or "MISSING" in r or "UNVERIFIED" in r or "NOT_READONLY" in r
            for r in reasons
        ):
            evidence_state = "CONFLICT"
    return {
        "schema_version": "cygnusx.download_runtime_manifest.v1",
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "SOURCE_WITH_OPERATOR_OBSERVATION" if observed else "SOURCE_ONLY",
        "source": {
            "main_sha": source_sha,
            "main_dirty": bool(_git(root, "status", "--porcelain")),
            "downloader_sha": downloader_sha,
            "downloader_dirty": bool(_git(downloader, "status", "--porcelain")),
            "downloader_version": version,
            "downloader_cargo_lock_sha256": _sha(downloader / "Cargo.lock"),
            "python_uv_lock_sha256": _sha(root / "uv.lock"),
            "worker_dockerfile_sha256": _sha(root / "deploy/docker/Dockerfile.worker"),
            "download_worker_sha256": _sha(
                root / "src/cygnusx/infrastructure/celery_app/tasks/download.py"
            ),
            "download_contract_sha256": _sha(root / "src/cygnusx/domain/download_contract.py"),
            "download_config_sha256": _sha(root / "src/cygnusx/tools/download/config.py"),
            "worker_compose_sha256": _sha(root / "deploy/docker/docker-compose.worker.yml"),
        },
        "declared": {
            "sra_methods": sorted(SRA_METHODS),
            "direct_schemes": sorted(DIRECT_SCHEMES),
            "effective_direct_schemes": sorted(config.validation.allowed_schemes),
            "cloud_schemes": CLOUD_SCHEMES,
            "unsupported": ["aspera", "ftps", "s3", "cos", "cloud_drive", "advanced_filters"],
            "required_programs": {
                "sra.aws": ["EBIDownload", "fasterq-dump", "Rust built-in compression"],
                "sra.ftp": ["EBIDownload", "wget"],
                "direct_link": ["aria2c"],
                "ftp_directory": ["Python ftplib", "aria2c"],
                "aliyun": ["ossutil"],
                "volc": ["tosutil"],
                "huawei": ["obsutil"],
            },
        },
        "configuration": {
            "binary_paths": binaries,
            "settings_storage_root": settings_root,
            "path_factory_storage_root": factory_root,
            "binary_priority": "explicit download YAML > binary-specific Settings/env > storage_path-derived defaults",
            "switch_policy": "download YAML feature OR Settings environment feature",
            "web_mount_source": "CYGNUSX_DATA_ROOT",
            "worker_mount_source": "WORKER_SHARED_DATA_DIR",
            "worker_uid_declared_default": 1000,
            "worker_uid_observed": observed.uid if observed else None,
        },
        "worker_observation": observed.model_dump(mode="json") if observed else None,
        "worker_provenance_state": evidence_state,
        "runtime_status": "BLOCKED",
        "release_ready": False,
        "reason_codes": sorted(reasons),
    }
