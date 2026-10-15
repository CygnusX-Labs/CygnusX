"""Bounded, local, read-only RNA ARDP projection. Unknown extensions never enter snapshots."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from cygnusx.application.schemas.report_snapshot import (
    ArtifactEvidence,
    EvidenceSource,
    EvidenceStatus,
    ExecutionStepEvidence,
    FactEvidence,
    FileFingerprint,
    SourceWatermark,
)
from cygnusx.application.services.report_snapshot_sources import TaskEvidenceRecords
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import AuthorizationError, ConflictError
from cygnusx.infrastructure.database.models.file import FileRecordModel
from cygnusx.infrastructure.storage.path_factory import StoragePathFactory

MANIFEST_BYTE_LIMIT = 4 * 1024 * 1024
MANIFEST_FILE_LIMIT = 2000
HASH_CHUNK_BYTES = 1024 * 1024


class ManifestFile(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    type: str = "other"
    category: str = "other"
    size_bytes: StrictInt | None = Field(default=None, ge=0)
    md5: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ManifestPlatform(BaseModel):
    task_id: str | None = None
    user_id: str | None = None
    flow_id: str | None = None


class ManifestPipeline(BaseModel):
    version: str | None = None


class ManifestRun(BaseModel):
    status: Literal["completed", "completed_no_report", "failed", "aborted"]
    pipeline: ManifestPipeline = Field(default_factory=ManifestPipeline)
    started_at: datetime | None = None
    duration_seconds: StrictInt | None = Field(default=None, ge=0)


class RNAResultManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    manifest_version: Literal["1.0"]
    kind: Literal["omichub.analysis.result"]
    platform: ManifestPlatform = Field(default_factory=ManifestPlatform)
    run: ManifestRun
    files: tuple[ManifestFile, ...] = Field(default=(), max_length=MANIFEST_FILE_LIMIT)


@dataclass(frozen=True)
class ManifestProjection:
    source: EvidenceSource
    artifacts: tuple[ArtifactEvidence, ...] = ()
    facts: tuple[FactEvidence, ...] = ()
    steps: tuple[ExecutionStepEvidence, ...] = ()
    watermarks: tuple[SourceWatermark, ...] = ()
    warnings: tuple[str, ...] = ()


def evidence(
    source_type: Literal["task", "run", "run_event", "result_manifest", "file_record", "gap"],
    source_id: str,
    now: datetime,
    status: EvidenceStatus,
    details: str,
    *,
    observed_at: datetime | None = None,
    method: Literal[
        "database_read", "manifest_read", "file_hash", "gap_annotation"
    ] = "database_read",
) -> EvidenceSource:
    return EvidenceSource(
        source_type=source_type,
        source_id=source_id,
        captured_at=now,
        observed_at=observed_at,
        capture_method=method,
        verification_status=status,
        verification_details=details,
    )


def safe_label(value: str | None) -> str | None:
    """Only bounded identifiers; no URLs, commands, free text or credential-like strings."""
    if value is None or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        return None
    if re.search(r"token|secret|password|credential|api.?key|^sk-|eyJ", value, re.I):
        return None
    return value


def safe_display_label(value: str | None) -> str | None:
    """Owner label projection v2: bounded Unicode names, no paths or credential-like text."""
    if not value:
        return None
    label = " ".join(value.split())
    if not any(char.isalnum() for char in label) or len(label) > 120 or not re.fullmatch(r"[\w .()（）-]+", label, re.UNICODE):
        return None
    if re.search(r"token|secret|password|credential|api.?key|sk-|eyJ|[A-Za-z0-9_=-]{40,}", label, re.I):
        return None
    return label


def within(root: Path, target: Path) -> Path:
    resolved = target.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise AuthorizationError(
            "Evidence path outside authorized boundary", code="snapshot_path_forbidden"
        )
    return resolved


def manifest_target(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or "\\" in value:
        raise AuthorizationError("Unsafe manifest path", code="snapshot_path_forbidden")
    return within(root, root / relative)


class CaptureBudgetError(OSError):
    """A partial observation, never a verified hash."""


@contextmanager
def pinned_directory(path: Path) -> Iterator[int]:
    """Walk parents without following symlinks and keep the final directory pinned."""
    absolute = path.absolute()
    directory_fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for segment in absolute.parts[1:]:
            next_fd = os.open(
                segment,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        yield directory_fd
    finally:
        os.close(directory_fd)


@contextmanager
def open_evidence_file(path: Path) -> Iterator[BinaryIO]:
    """Pin directory FDs and refuse links/special files at open time, closing TOCTOU."""
    with pinned_directory(path.parent) as parent_fd:
        fd = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_fd,
        )
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("Evidence must be a regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                yield stream
        finally:
            os.close(fd)


def current_hashes(
    path: Path,
    *,
    deadline: float | None = None,
    byte_limit: int | None = None,
) -> tuple[int, str, str]:
    """Stream pinned bytes; detect rewrites and stop at the worker capture budget."""
    sha = hashlib.sha256()
    md5 = hashlib.md5()  # noqa: S324 - legacy ARDP comparison, not authentication
    with open_evidence_file(path) as stream:
        before = os.fstat(stream.fileno())
        if byte_limit is not None and before.st_size > byte_limit:
            raise CaptureBudgetError("Capture byte budget reached")
        size = 0
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise CaptureBudgetError("Capture time budget reached")
            chunk = stream.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            if byte_limit is not None and size > byte_limit:
                raise CaptureBudgetError("Capture byte budget reached")
            sha.update(chunk)
            md5.update(chunk)
        after = os.fstat(stream.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or size != after.st_size:
        raise OSError("File changed during capture")
    return size, sha.hexdigest(), md5.hexdigest()


class RNAResultManifestAdapter:
    def __init__(self, factory: StoragePathFactory):
        self._factory = factory
        self._deadline: float | None = None
        self._remaining_bytes: int | None = None

    def read(self, records: TaskEvidenceRecords, now: datetime) -> ManifestProjection:
        settings = get_settings()
        self._deadline = time.monotonic() + settings.report_generation_timeout_seconds
        self._remaining_bytes = settings.report_capture_max_bytes
        task = records.task
        owner_root = self._factory.user_root(str(task.user_id)).absolute()
        # A symlinked owner root must not redirect the whole authorization boundary.
        if owner_root.resolve() != owner_root:
            raise AuthorizationError("Symlinked owner boundary")
        if not task.work_dir:
            return self._with_registered(
                records,
                evidence(
                    "gap",
                    "result_manifest",
                    now,
                    EvidenceStatus.NOT_RECORDED,
                    "Task has no recorded work directory",
                    method="gap_annotation",
                ),
                now,
            )
        work = within(owner_root, Path(task.work_dir))
        roots = [work]
        if work.name == "work":
            roots.append(within(owner_root, work.parent / "data_deliver"))
        roots.append(within(owner_root, work / "data_deliver"))
        found: list[tuple[Path, Path]] = []
        for root in roots:
            path = manifest_target(root, "result_manifest.json")
            if path.exists():
                found.append((root, path))
        if len(found) > 1:
            raise ConflictError("Multiple result manifests; explicit source selection required")
        if not found:
            source = evidence(
                "gap",
                "result_manifest",
                now,
                EvidenceStatus.NOT_RECORDED,
                "No ARDP result_manifest; no legacy HTML fallback",
                method="gap_annotation",
            )
            return self._with_registered(records, source, now)
        root, path = found[0]
        try:
            with open_evidence_file(path) as stream:
                raw = stream.read(MANIFEST_BYTE_LIMIT + 1)
            if len(raw) > MANIFEST_BYTE_LIMIT:
                raise ValueError("Manifest exceeds capture budget")
            manifest = RNAResultManifest.model_validate_json(raw)
        except (OSError, ValueError, ValidationError):
            source = evidence(
                "result_manifest",
                "result_manifest",
                now,
                EvidenceStatus.VERIFICATION_FAILED,
                "Manifest unreadable, malformed or unsupported; raw text omitted",
                method="manifest_read",
            )
            return self._with_registered(records, source, now)
        platform = manifest.platform
        for declared, actual in (
            (platform.task_id, str(task.id)),
            (platform.user_id, str(task.user_id)),
            (platform.flow_id, task.flow_id),
        ):
            if declared is not None and declared != actual:
                raise ConflictError("Manifest execution identity conflict")
        bound = platform.task_id is not None and platform.user_id is not None
        digest = hashlib.sha256(raw).hexdigest()
        source = evidence(
            "result_manifest",
            digest,
            now,
            EvidenceStatus.VERIFIED if bound else EvidenceStatus.ESTIMATED,
            "Manifest identity matches Task/owner; declarations are not runtime probes"
            if bound
            else "Manifest in recorded work area lacks explicit execution identity",
            method="manifest_read",
        )
        registered: dict[Path, FileRecordModel] = {}
        for file in records.files:
            target = self._registered_path(file.storage_path, owner_root)
            registered[target] = file
        artifacts: list[ArtifactEvidence] = []
        for index, entry in enumerate(manifest.files):
            target = manifest_target(root, entry.path)
            record = registered.pop(target, None)
            origin = evidence(
                "file_record" if record else "result_manifest",
                str(record.id) if record else digest,
                now,
                EvidenceStatus.VERIFIED if record or bound else EvidenceStatus.NOT_RECORDED,
                "Explicit Task file/manifest association"
                if record or bound
                else "File exists but execution association and original origin are unknown",
                method="database_read" if record else "manifest_read",
            )
            artifacts.append(
                self._artifact(
                    target, entry, f"manifest:{digest}:{index}", source, origin, now, record
                )
            )
        # Registered task artifacts are independently useful even if absent from files[].
        for target, record in registered.items():
            origin = evidence(
                "file_record",
                str(record.id),
                now,
                EvidenceStatus.VERIFIED,
                "Explicit owner and Task foreign reference",
            )
            artifacts.append(
                self._artifact(
                    target,
                    ManifestFile(path="registered"),
                    f"file:{record.id}",
                    origin,
                    origin,
                    now,
                    record,
                )
            )
        facts: list[FactEvidence] = []
        declaration = evidence(
            "result_manifest",
            digest,
            now,
            EvidenceStatus.ESTIMATED,
            "Recorded workflow declaration; actual software/runtime not observed",
            method="manifest_read",
        )
        if version := safe_label(manifest.run.pipeline.version):
            facts.append(
                FactEvidence(field="pipeline_declared_version", value=version, source=declaration)
            )
        steps: tuple[ExecutionStepEvidence, ...] = ()
        if manifest.run.duration_seconds is not None:
            # RNAFlow estimates these from mtime; never promote them to observed timing.
            steps = (
                ExecutionStepEvidence(
                    sequence=0,
                    phase="manifest_timing_estimate",
                    status=manifest.run.status,
                    duration_seconds=manifest.run.duration_seconds,
                    source=declaration,
                ),
            )
        return ManifestProjection(
            source=source,
            artifacts=tuple(artifacts),
            facts=tuple(facts),
            steps=steps,
            watermarks=(
                SourceWatermark(
                    source_type="result_manifest", source_id=str(task.id), revision=digest
                ),
            ),
        )

    def _registered_path(self, value: str, owner_root: Path) -> Path:
        return within(owner_root, self._factory.data_root / value)

    def _with_registered(
        self, records: TaskEvidenceRecords, source: EvidenceSource, now: datetime
    ) -> ManifestProjection:
        artifacts: list[ArtifactEvidence] = []
        owner_root = self._factory.user_root(str(records.task.user_id))
        for file in records.files:
            target = self._registered_path(file.storage_path, owner_root)
            origin = evidence(
                "file_record",
                str(file.id),
                now,
                EvidenceStatus.VERIFIED,
                "Explicit owner and Task foreign reference",
            )
            artifacts.append(
                self._artifact(
                    target,
                    ManifestFile(path="registered"),
                    f"file:{file.id}",
                    origin,
                    origin,
                    now,
                    file,
                )
            )
        return ManifestProjection(source, tuple(artifacts))

    def _artifact(
        self,
        path: Path,
        entry: ManifestFile,
        reference: str,
        source: EvidenceSource,
        origin: EvidenceSource,
        now: datetime,
        file: FileRecordModel | None,
    ) -> ArtifactEvidence:
        fingerprints: list[FileFingerprint] = []
        for algorithm, value in (("md5", entry.md5), ("sha256", entry.sha256)):
            if value:
                fingerprints.append(
                    FileFingerprint(algorithm=algorithm, value=value, scope="manifest_declared")
                )
        status = EvidenceStatus.UNAVAILABLE
        detail = "Artifact absent or inaccessible at capture"
        size: int | None = None
        kind: Literal["file", "directory"] = "directory" if entry.type == "dir" else "file"
        try:
            if file and (
                file.storage_backend != "local" or file.status not in {"active", "archived"}
            ):
                detail = "Registered artifact not locally available; no remote fallback"
            elif kind == "directory" and path.is_dir():
                status = EvidenceStatus.ESTIMATED
                detail = "Directory exists; contents not recursively captured or verified"
            elif kind == "file" and path.is_file():
                size, sha, md5 = current_hashes(
                    path,
                    deadline=self._deadline,
                    byte_limit=self._remaining_bytes,
                )
                if self._remaining_bytes is not None:
                    self._remaining_bytes -= size
                mismatch = (
                    (entry.size_bytes is not None and entry.size_bytes != size)
                    or (entry.sha256 is not None and entry.sha256 != sha)
                    or (entry.md5 is not None and entry.md5 != md5)
                )
                status = EvidenceStatus.VERIFICATION_FAILED if mismatch else EvidenceStatus.VERIFIED
                detail = (
                    "Manifest size/hash mismatch"
                    if mismatch
                    else (
                        "Current bytes captured; this does not attest execution-time bytes or scientific validity"
                    )
                )
                fingerprints.append(
                    FileFingerprint(
                        algorithm="sha256", value=sha, scope="capture_bytes", verified_at=now
                    )
                )
                if not mismatch:
                    fingerprints = [
                        fp.model_copy(update={"verified_at": now})
                        if fp.scope == "manifest_declared"
                        else fp
                        for fp in fingerprints
                    ]
        except CaptureBudgetError:
            detail = "Capture byte/time budget reached; bytes not verified"
            status = EvidenceStatus.UNAVAILABLE
        except OSError:
            detail = "Artifact unreadable or changed during capture; bytes not verified"
            status = EvidenceStatus.VERIFICATION_FAILED
        checked = evidence(
            source.source_type, source.source_id, now, status, detail, method="file_hash"
        )
        category: Literal["report", "qc", "expression", "deg", "log", "other"] = "other"
        categories: dict[str, Literal["report", "qc", "expression", "deg", "log", "other"]] = {
            "report": "report",
            "qc": "qc",
            "expression": "expression",
            "deg": "deg",
            "log": "log",
        }
        category = categories.get(entry.category, "other")
        return ArtifactEvidence(
            artifact_reference=reference,
            display_name=safe_display_label(file.original_name if file else Path(entry.path).name),
            file_record_id=file.id if file else None,
            category=category,
            kind=kind,
            size_bytes=size,
            fingerprints=tuple(fingerprints),
            source=checked,
            origin=origin,
        )
