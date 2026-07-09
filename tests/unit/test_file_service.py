from pathlib import Path

from omichub.application.services.file_service import (
    FileService,
    _append_dedupe_suffix,
    canonical_original_name,
)


def test_canonical_original_name_strips_service_dedupe_suffix() -> None:
    assert canonical_original_name("sample_1a2b3c4d.fastq.gz") == "sample.fastq.gz"
    assert canonical_original_name("sample.fastq_1a2b3c4d.gz") == "sample.fastq.gz"


def test_canonical_original_name_keeps_common_lane_numbers() -> None:
    assert canonical_original_name("sample_001.fastq.gz") == "sample_001.fastq.gz"


def test_append_dedupe_suffix_preserves_compound_suffix() -> None:
    result = _append_dedupe_suffix(Path("/tmp/sample.fastq.gz"), "1a2b3c4d")

    assert result.name == "sample_1a2b3c4d.fastq.gz"


def test_derive_directory_matches_upload_and_download_layouts() -> None:
    assert FileService._derive_directory(Path("raw/projectA/sample.fastq.gz")) == "projectA"
    assert FileService._derive_directory(Path("raw_data/PRJNA1/SRR1.fastq.gz")) == "raw_data/PRJNA1"
    assert FileService._derive_directory(Path("sample.fastq.gz")) == ""
