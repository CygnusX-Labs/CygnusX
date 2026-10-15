"""Bounded scientific input inspection. Integer appearance is never counts proof."""

from __future__ import annotations

import csv
import gzip
import hashlib
import os
import re
import stat
from collections.abc import Iterator
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from cygnusx.application.schemas.dataset import DataType
from cygnusx.core.exceptions import ValidationError


class ByteReader(Protocol):
    def read(self, size: int = -1) -> bytes: ...
    def readline(self, size: int = -1) -> bytes: ...
    def seek(self, offset: int, whence: int = 0) -> int: ...


@dataclass(frozen=True)
class ValidationLimits:
    max_expansion_ratio: int = 100
    max_bytes: int = 64 * 1024 * 1024
    max_rows: int = 200_000
    max_columns: int = 1000
    max_line_bytes: int = 1024 * 1024


def open_owned_file(path: Path, owner_root: Path) -> BinaryIO:
    """Walk root-relative components with openat/O_NOFOLLOW, reject hard/special links."""
    root = owner_root.resolve(strict=True)
    if root != owner_root.absolute():
        raise ValidationError("存储根含未经验证的符号链接", code="UNSAFE_FILE")
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as exc:
        raise ValidationError("文件超出用户存储根", code="PATH_ESCAPE") from exc
    if not relative.parts or any(p in {"..", "."} for p in relative.parts):
        raise ValidationError("文件路径非法", code="PATH_ESCAPE")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative.parts[:-1]:
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        fd = os.open(
            relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            raise ValidationError("拒绝特殊文件或硬链接", code="UNSAFE_FILE")
        return os.fdopen(fd, "rb")
    except OSError as exc:
        raise ValidationError("文件不可用或路径含符号链接", code="UNSAFE_FILE") from exc
    finally:
        os.close(directory)


def checksum(stream: ByteReader, limits: ValidationLimits) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    while chunk := stream.read(min(1024 * 1024, limits.max_bytes + 1 - total)):
        total += len(chunk)
        if total > limits.max_bytes:
            raise ValidationError("文件超出校验预算", code="VALIDATION_LIMIT")
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest(), total


def _lines(stream: ByteReader, limits: ValidationLimits) -> Iterator[str]:
    total = 0
    while True:
        line = stream.readline(limits.max_line_bytes + 1)
        if not line:
            break
        total += len(line)
        if len(line) > limits.max_line_bytes or total > limits.max_bytes:
            raise ValidationError("展开文本超过校验预算", code="VALIDATION_LIMIT")
        try:
            yield line.decode("utf-8-sig").rstrip("\r\n")
        except UnicodeDecodeError as exc:
            raise ValidationError("文本编码无法安全识别", code="UNKNOWN_ENCODING") from exc


def inspect_matrix(
    stream: ByteReader,
    *,
    metadata_samples: list[str] | None = None,
    source_evidence: dict[str, Any] | None = None,
    limits: ValidationLimits | None = None,
) -> dict[str, Any]:
    limits = limits or ValidationLimits()
    evidence = source_evidence or {}
    result: dict[str, Any] = {
        "data_type": DataType.UNKNOWN.value,
        "status": "REVIEW_REQUIRED",
        "classification_source": "bounded_content_and_source",
        "evidence": evidence,
        "inference": [],
        "reviewer_override": None,
        "errors": [],
        "samples": [],
        "rows": 0,
        "orientation": "unknown",
        "all_zero_features": 0,
    }
    lines = iter(_lines(stream, limits))
    try:
        first = next(lines)
    except StopIteration:
        result["errors"].append("EMPTY_MATRIX")
        return result
    # Series Matrix is not raw counts, even if its data table happens to be integers.
    if first.startswith(("!", "^")):
        result["errors"].append("SERIES_MATRIX_REQUIRES_REVIEW")
        return result
    delimiter = "\t" if "\t" in first else ","
    header = next(csv.reader([first], delimiter=delimiter))
    columns = header[1:]
    if len(columns) > limits.max_columns:
        raise ValidationError("矩阵列数超过预算", code="VALIDATION_LIMIT")
    result["samples"] = columns
    errors: list[str] = result["errors"]
    if not columns or any(not c.strip() for c in columns) or len(set(columns)) != len(columns):
        errors.append("MISSING_OR_DUPLICATE_SAMPLES")
    if header[0].strip().lower() not in {
        "gene",
        "gene_id",
        "geneid",
        "feature",
        "feature_id",
        "ensembl_id",
        "gene_symbol",
        "entrez_id",
    }:
        errors.append("ORIENTATION_UNKNOWN")
    else:
        result["orientation"] = "gene_by_sample"
    if (
        metadata_samples is None
        or set(columns) != set(metadata_samples)
        or len(metadata_samples) != len(set(metadata_samples))
    ):
        errors.append("METADATA_SAMPLE_MISMATCH")
    features: set[str] = set()
    integer = True
    for index, line in enumerate(lines):
        if index >= limits.max_rows:
            raise ValidationError("矩阵行数超过预算", code="VALIDATION_LIMIT")
        row = next(csv.reader([line], delimiter=delimiter))
        result["rows"] += 1
        if len(row) != len(header):
            if "ROW_WIDTH_MISMATCH" not in errors:
                errors.append("ROW_WIDTH_MISMATCH")
            continue
        feature = row[0]
        if (
            not feature or not re.fullmatch(r"[A-Za-z0-9_.:\-]+", feature) or feature in features
        ) and "INVALID_OR_DUPLICATE_FEATURE" not in errors:
            errors.append("INVALID_OR_DUPLICATE_FEATURE")
        features.add(feature)
        all_zero = True
        for value in row[1:]:
            try:
                number = Decimal(value)
                if not number.is_finite() or number < 0:
                    raise InvalidOperation
                integer = integer and number == number.to_integral_value()
                all_zero = all_zero and number == 0
            except InvalidOperation:
                if "MISSING_NEGATIVE_OR_NONNUMERIC_VALUE" not in errors:
                    errors.append("MISSING_NEGATIVE_OR_NONNUMERIC_VALUE")
        if all_zero:
            result["all_zero_features"] += 1
    if not result["rows"]:
        errors.append("EMPTY_MATRIX")
    description = str(evidence.get("processing_description", "")).lower()
    normalized = (
        (r"\btpm\b", DataType.NORMALIZED_EXPRESSION_TPM),
        (r"\bfpkm\b|\brpkm\b", DataType.NORMALIZED_EXPRESSION_FPKM),
        (r"\bcpm\b", DataType.NORMALIZED_EXPRESSION_CPM),
        (r"\blog(?:2|10)?\b|z[ -]?score|transformed", DataType.TRANSFORMED_EXPRESSION),
    )
    for pattern, dtype in normalized:
        if re.search(pattern, description):
            result["data_type"] = dtype.value
            result["status"] = "VALIDATED" if not errors else "REVIEW_REQUIRED"
            return result
    if evidence.get("assay_type") == "microarray":
        result["data_type"] = DataType.MICROARRAY_EXPRESSION.value
        return result
    if not integer:
        errors.append("NON_INTEGER_COUNTS")
    provenance = evidence.get("source_url") and re.fullmatch(
        r"[a-f0-9]{64}", str(evidence.get("response_sha256", ""))
    )
    raw_method = re.search(
        r"featurecounts|htseq[ -]?count|raw (?:integer )?(?:gene )?counts|un?normalized counts",
        description,
    )
    # Even a trusted source description remains conditional on all matrix/sample checks.
    if provenance and raw_method and integer and not errors:
        result["data_type"] = DataType.RAW_INTEGER_COUNTS.value
        result["status"] = "VALIDATED"
    elif "SOURCE_COUNTS_NOT_PROVEN" not in errors:
        errors.append("SOURCE_COUNTS_NOT_PROVEN")
    return result


def inspect_fastq(stream: ByteReader, *, limits: ValidationLimits | None = None) -> dict[str, Any]:
    limits = limits or ValidationLimits()
    iterator = iter(_lines(stream, limits))
    reads = 0
    while True:
        try:
            name = next(iterator)
        except StopIteration:
            break
        try:
            sequence, plus, quality = next(iterator), next(iterator), next(iterator)
        except StopIteration as exc:
            raise ValidationError("FASTQ 记录截断", code="INVALID_FASTQ") from exc
        if (
            not name.startswith("@")
            or not plus.startswith("+")
            or not sequence
            or len(sequence) != len(quality)
            or not re.fullmatch("[ACGTNacgtn.]+", sequence)
            or any(ord(q) < 33 or ord(q) > 126 for q in quality)
        ):
            raise ValidationError("FASTQ 内容校验失败", code="INVALID_FASTQ")
        reads += 1
        if reads > limits.max_rows:
            raise ValidationError("FASTQ 记录超过校验预算", code="VALIDATION_LIMIT")
    if reads == 0:
        raise ValidationError("FASTQ 为空", code="INVALID_FASTQ")
    return {
        "data_type": DataType.RAW_FASTQ.value,
        "status": "VALIDATED",
        "reads": reads,
        "classification_source": "full_bounded_fastq_validation",
        "errors": [],
    }


def inspect_content(
    stream: BinaryIO,
    name: str,
    *,
    metadata_samples: list[str] | None = None,
    source_evidence: dict[str, Any] | None = None,
    limits: ValidationLimits | None = None,
) -> dict[str, Any]:
    limits = limits or ValidationLimits()
    lower = name.lower()
    if lower.endswith(".gz"):
        stream.seek(0, os.SEEK_END)
        compressed_size = stream.tell()
        stream.seek(0)
        limits = replace(
            limits,
            max_bytes=min(limits.max_bytes, max(1, compressed_size) * limits.max_expansion_ratio),
        )
    decoded = gzip.GzipFile(fileobj=stream) if lower.endswith(".gz") else stream
    try:
        if lower.endswith((".fastq", ".fq", ".fastq.gz", ".fq.gz")):
            return inspect_fastq(decoded, limits=limits)
        if lower.endswith((".tsv", ".txt", ".csv", ".tsv.gz", ".txt.gz", ".csv.gz")):
            return inspect_matrix(
                decoded,
                metadata_samples=metadata_samples,
                source_evidence=source_evidence,
                limits=limits,
            )
        return {
            "data_type": "UNKNOWN",
            "status": "REVIEW_REQUIRED",
            "errors": ["FORMAT_NOT_SUPPORTED"],
            "classification_source": "unparsed_asset",
            "evidence": [],
            "inference": [],
        }
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise ValidationError("压缩文件损坏", code="CORRUPT_COMPRESSION") from exc
    finally:
        if decoded is not stream:
            decoded.close()


def inspect_sample_metadata(
    stream: ByteReader, sample_keys: list[str], *, limits: ValidationLimits | None = None
) -> dict[str, Any]:
    limits = limits or ValidationLimits()
    reader = csv.DictReader(_lines(stream, limits), delimiter="\t")
    errors = []
    header = reader.fieldnames or []
    if not {"sample_id", "group"}.issubset(header) or len(header) != len(set(header)):
        errors.append("SAMPLE_METADATA_COLUMNS_REQUIRED")
    rows = []
    for index, row in enumerate(reader):
        if index >= limits.max_rows:
            raise ValidationError("样本表超过预算", code="VALIDATION_LIMIT")
        if None in row or any(value is None for value in row.values()):
            errors.append("METADATA_ROW_WIDTH_MISMATCH")
            break
        rows.append(
            {key: value for key, value in row.items() if key in {"sample_id", "group", "batch"}}
        )
    keys = [row.get("sample_id", "") for row in rows]
    if not keys or len(set(keys)) != len(keys) or set(keys) != set(sample_keys):
        errors.append("METADATA_SAMPLE_MISMATCH")
    if any(not row.get("group") for row in rows):
        errors.append("SAMPLE_GROUP_MISSING")
    return {
        "data_type": "SAMPLE_METADATA",
        "status": "VALIDATED" if not errors else "REVIEW_REQUIRED",
        "classification_source": "bounded_metadata_content",
        "errors": sorted(set(errors)),
        "rows": rows,
    }
