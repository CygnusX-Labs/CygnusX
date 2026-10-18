"""Bounded output inspection for the existing download Worker and FileRegistry.

This is registration validation, not a transport engine or a transfer-byte limit.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.dataset.validation import ValidationLimits, checksum, open_owned_file


@dataclass(frozen=True)
class DownloadOutput:
    path: Path
    sha256: str
    size: int


def controlled_paths(work_dir: Path, owner_root: Path, max_entries: int) -> list[Path]:
    """Enumerate without following links; reject special entries, including link directories."""
    if work_dir.absolute() != work_dir.resolve() or not work_dir.is_relative_to(owner_root):
        raise ValidationError("下载目录含链接或超出用户根", code="UNSAFE_DOWNLOAD_OUTPUT")
    if work_dir == owner_root or not work_dir.is_dir():
        raise ValidationError("下载目录缺失或不是任务子目录", code="DOWNLOAD_OUTPUT_MISSING")

    def open_directory(path: Path) -> int:
        fd = os.open(owner_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in path.relative_to(owner_root).parts:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
        except BaseException:
            os.close(fd)
            raise
        return fd

    result: list[Path] = []
    pending = [work_dir]
    entries = 0
    try:
        while pending:
            current = pending.pop()
            fd = open_directory(current)
            try:
                with os.scandir(fd) as children:
                    for entry in children:
                        entries += 1
                        if entries > max_entries:
                            raise ValidationError(
                                "下载登记条目超限", code="DOWNLOAD_REGISTRATION_LIMIT"
                            )
                        info = entry.stat(follow_symlinks=False)
                        path = current / entry.name
                        if stat.S_ISDIR(info.st_mode):
                            pending.append(path)
                        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                            result.append(path)
                        else:
                            raise ValidationError(
                                "下载输出含链接或特殊文件", code="UNSAFE_DOWNLOAD_OUTPUT"
                            )
            finally:
                os.close(fd)
    except OSError as exc:
        raise ValidationError("下载目录不可安全读取", code="UNSAFE_DOWNLOAD_OUTPUT") from exc
    return sorted(result)


def is_control_file(path: Path, work_dir: Path) -> bool:
    parts = path.relative_to(work_dir).parts
    return any(
        part.startswith(".")
        or part.lower() in {"checkpoint", "checkpoints", "progress.key", "progress.json"}
        or part.lower().endswith(("_metadata", ".aria2", ".checkpoint", ".log", ".part", ".tmp"))
        for part in parts
    )


def inspect_output(path: Path, owner_root: Path, max_bytes: int) -> DownloadOutput:
    """Hash a stable, owned, non-linked regular file using existing Dataset validators."""
    with open_owned_file(path, owner_root) as stream:
        before = os.fstat(stream.fileno())
        sha, size = checksum(stream, ValidationLimits(max_bytes=max_bytes))
        after = os.fstat(stream.fileno())
        current = path.stat(follow_symlinks=False)
        signatures = {
            (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
            for s in (before, after, current)
        }
        if len(signatures) != 1 or size != before.st_size or size == 0:
            raise ValidationError("下载文件为空或校验期间发生变化", code="DOWNLOAD_OUTPUT_CHANGED")
    return DownloadOutput(path=path, sha256=sha, size=size)
