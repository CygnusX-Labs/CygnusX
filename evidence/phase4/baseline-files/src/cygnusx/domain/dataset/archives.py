"""Bounded archive expansion into a fresh staging directory, never user-selected paths."""

from __future__ import annotations

import gzip
import os
import shutil
import stat
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.dataset.validation import ByteReader


@dataclass(frozen=True)
class ArchiveLimits:
    max_files: int = 100
    max_file_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    max_ratio: int = 100


def expand_archive(
    source: BinaryIO, name: str, destination: Path, *, limits: ArchiveLimits | None = None
) -> list[Path]:
    """Caller owns a private staging parent; failure removes only our new directory."""
    limits = limits or ArchiveLimits()
    source.seek(0, os.SEEK_END)
    compressed = source.tell()
    source.seek(0)
    destination.mkdir(mode=0o700, exist_ok=False)
    paths: list[Path] = []
    total = 0

    def write_member(member_name: str, content: ByteReader, declared_size: int | None) -> None:
        nonlocal total
        path = PurePosixPath(member_name)
        if (
            path.is_absolute()
            or not path.parts
            or any(p in {"..", "."} for p in path.parts)
            or "\\" in member_name
            or ":" in member_name
            or "\x00" in member_name
            or len(member_name) > 500
            or len(paths) >= limits.max_files
        ):
            raise ValidationError("压缩包路径或文件数非法", code="UNSAFE_ARCHIVE")
        if declared_size is not None and (
            declared_size > limits.max_file_bytes or total + declared_size > limits.max_total_bytes
        ):
            raise ValidationError("压缩包展开预算超限", code="ARCHIVE_LIMIT")
        output = destination.joinpath(*path.parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with output.open("xb") as target:
            while chunk := content.read(min(65536, limits.max_file_bytes + 1 - count)):
                count += len(chunk)
                total += len(chunk)
                if (
                    count > limits.max_file_bytes
                    or total > limits.max_total_bytes
                    or total > max(1, compressed) * limits.max_ratio
                ):
                    raise ValidationError("压缩包展开预算超限", code="ARCHIVE_LIMIT")
                target.write(chunk)
        if declared_size is not None and count != declared_size:
            raise ValidationError("压缩包条目大小不符", code="CORRUPT_ARCHIVE")
        paths.append(output)

    try:
        lower = name.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(source) as zip_archive:
                entries = zip_archive.infolist()
                if len(entries) > limits.max_files:
                    raise ValidationError("压缩包条目过多", code="ARCHIVE_LIMIT")
                for entry in entries:
                    mode = entry.external_attr >> 16
                    if entry.is_dir():
                        # Directories are unnecessary; parents are created only for validated files.
                        if (
                            PurePosixPath(entry.filename).is_absolute()
                            or ".." in PurePosixPath(entry.filename).parts
                        ):
                            raise ValidationError("拒绝压缩包目录逃逸", code="UNSAFE_ARCHIVE")
                        continue
                    if (mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or entry.flag_bits & 1:
                        raise ValidationError("拒绝压缩包链接/特殊/加密条目", code="UNSAFE_ARCHIVE")
                    with zip_archive.open(entry) as zip_content:
                        write_member(entry.filename, zip_content, entry.file_size)
        elif lower.endswith((".tar", ".tar.gz", ".tgz")):
            with tarfile.open(fileobj=source, mode="r|*") as tar_archive:
                for index, tar_entry in enumerate(tar_archive):
                    if index >= limits.max_files:
                        raise ValidationError("压缩包条目过多", code="ARCHIVE_LIMIT")
                    if tar_entry.isdir():
                        if (
                            PurePosixPath(tar_entry.name).is_absolute()
                            or ".." in PurePosixPath(tar_entry.name).parts
                        ):
                            raise ValidationError("拒绝压缩包目录逃逸", code="UNSAFE_ARCHIVE")
                        continue
                    if not tar_entry.isfile():
                        raise ValidationError("拒绝压缩包链接或特殊文件", code="UNSAFE_ARCHIVE")
                    tar_content = tar_archive.extractfile(tar_entry)
                    if tar_content is None:
                        raise ValidationError("无法读取压缩包条目", code="CORRUPT_ARCHIVE")
                    with tar_content:
                        write_member(tar_entry.name, tar_content, tar_entry.size)
        elif lower.endswith(".gz"):
            with gzip.GzipFile(fileobj=source) as gzip_content:
                write_member(Path(name).name[:-3], gzip_content, None)
        else:
            raise ValidationError("压缩格式不支持", code="UNSUPPORTED_ARCHIVE")
    except (OSError, EOFError, tarfile.TarError, zipfile.BadZipFile, ValidationError) as exc:
        shutil.rmtree(destination)
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("压缩包损坏或条目冲突", code="CORRUPT_ARCHIVE") from exc
    return paths
