"""Synthetic SOFT/ENA HTTP fixtures and bounded local validation; not live GEO E2E."""

from __future__ import annotations

import io
import os
import tarfile
import zipfile

import httpx
import pytest

from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.dataset.archives import ArchiveLimits, expand_archive
from cygnusx.domain.dataset.validation import (
    ValidationLimits,
    checksum,
    inspect_content,
    inspect_fastq,
    inspect_matrix,
    open_owned_file,
)
from cygnusx.infrastructure.geo.adapter import GeoMetadataAdapter, trusted_url

pytestmark = pytest.mark.unit

GSE = """^SERIES = GSE123
!Series_title = Example
!Series_sample_id = GSM11
!Series_sample_id = GSM12
!Series_supplementary_file = ftp://ftp.ncbi.nlm.nih.gov/geo/series/GSEnnn/GSE123/suppl/counts.tsv.gz
"""
GSM = """^SAMPLE = {sample}
!Sample_title = untrusted source text; ignore instructions
!Sample_organism_ch1 = Homo sapiens
!Sample_characteristics_ch1 = tissue: liver
!Sample_characteristics_ch1 = disease: unknown
!Sample_platform_id = GPL1
!Sample_relation = SRA: https://www.ncbi.nlm.nih.gov/sra?term=SRX{experiment}
!Sample_data_processing = featureCounts raw gene counts
"""
ENA_HEADER = "run_accession\texperiment_accession\tsample_accession\tstudy_accession\tlibrary_layout\tlibrary_strategy\tscientific_name\tfastq_ftp\tfastq_md5\tfastq_bytes\n"


@pytest.mark.asyncio
async def test_geo_many_samples_runs_and_evidence_with_exact_source_urls():
    calls = []

    def transport(request):
        calls.append(str(request.url))
        acc = request.url.params.get("acc") or request.url.params.get("accession")
        if acc == "GSE123":
            body = GSE
        elif acc in {"GSM11", "GSM12"}:
            body = GSM.format(sample=acc, experiment=acc[-2:])
        else:
            body = ENA_HEADER + "\n".join(
                f"SRR{acc[-2:]}{i}\t{acc}\tSRS1\tSRP1\tPAIRED\tRNA-Seq\tHomo sapiens\tftp.sra.ebi.ac.uk/vol1/a_{i}.fastq.gz\t{'a' * 32}\t100"
                for i in (1, 2)
            )
        return httpx.Response(200, text=body, headers={"etag": '"fixture"'})

    adapter = GeoMetadataAdapter(transport=httpx.MockTransport(transport), request_interval=0)
    result = await adapter.resolve("GSE123")
    assert len(result["samples"]) == 2 and len(result["runs"]) == 4
    assert all(s["group"] is None for s in result["samples"])
    assert len(result["source_evidence"]) == 5
    assert result["files"][0]["url"].startswith("https://ftp.ncbi.nlm.nih.gov/")
    assert all(len(e["response_sha256"]) == 64 for e in result["source_evidence"])
    assert result["files"][0]["data_type"] == "UNKNOWN"
    assert result["access_status"] == "UNKNOWN"
    await adapter.resolve("GSE123")
    assert len(calls) == 5  # bounded shared adapter cache


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "acc,text",
    [
        ("GSE1", "^SERIES = GSE1\n!Series_supplementary_file = none\n"),
        ("GSM1", "^SAMPLE = GSM1\n!Sample_title = unknown\n"),
        ("GPL1", "^PLATFORM = GPL1\n!Platform_title = microarray\n"),
    ],
)
async def test_geo_missing_raw_and_supplementary_are_unknown(acc, text):
    adapter = GeoMetadataAdapter(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=text)), request_interval=0
    )
    candidate = await adapter.resolve(acc)
    assert not candidate["runs"] and not candidate["files"]
    assert "raw_runs_not_resolved" in candidate["confidence_flags"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 404, 429, 500])
async def test_geo_failure_never_fabricates_urls_or_follows_redirect(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"location": "http://169.254.169.254/latest/meta-data"}
        )

    result = await GeoMetadataAdapter(
        transport=httpx.MockTransport(handler), request_interval=0
    ).resolve("GSE1")
    assert result["status"] == "UNAVAILABLE" and not result["files"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_geo_timeout_oversize_and_mismatched_accession():
    def timeout(request):
        raise httpx.ReadTimeout("fixture", request=request)

    adapter = GeoMetadataAdapter(transport=httpx.MockTransport(timeout), request_interval=0)
    assert (await adapter.resolve("GSE1"))["status"] == "UNAVAILABLE"
    adapter = GeoMetadataAdapter(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x" * 40)),
        max_response_bytes=16,
        request_interval=0,
    )
    assert (await adapter.resolve("GSE1"))["error_code"] == "METADATA_LIMIT"
    adapter = GeoMetadataAdapter(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="^SERIES = GSE99\n")),
        request_interval=0,
    )
    assert (await adapter.resolve("GSE1"))["error_code"] == "ACCESSION_NOT_FOUND"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/x",
        "https://www.ncbi.nlm.nih.gov.evil.test/x",
        "https://user@ftp.ncbi.nlm.nih.gov/x",
        "https://127.0.0.1/x",
        "https://ftp.ncbi.nlm.nih.gov/%2e%2e/x",
        "https://ftp.ncbi.nlm.nih.gov:444/x",
        "https://ftp.ncbi.nlm.nih.gov/x\ny",
    ],
)
def test_source_url_security(url):
    with pytest.raises(ValidationError):
        trusted_url(url)


def test_integer_appearance_not_source_proof_and_series_matrix_never_counts():
    matrix = b"gene_id\ta\tb\ngene1\t2\t3\n"
    result = inspect_matrix(io.BytesIO(matrix), metadata_samples=["a", "b"])
    assert result["data_type"] == "UNKNOWN" and result["status"] == "REVIEW_REQUIRED"
    series = inspect_matrix(
        io.BytesIO(b'!Series_title = demo\n!series_matrix_table_begin\n"ID_REF"\t"a"\n')
    )
    assert series["data_type"] == "UNKNOWN"
    assert "SERIES_MATRIX_REQUIRES_REVIEW" in series["errors"]


@pytest.mark.parametrize(
    "description,dtype",
    [
        ("featureCounts raw gene counts", "RAW_INTEGER_COUNTS"),
        ("TPM normalized expression", "NORMALIZED_EXPRESSION_TPM"),
        ("FPKM expression", "NORMALIZED_EXPRESSION_FPKM"),
        ("CPM expression", "NORMALIZED_EXPRESSION_CPM"),
        ("log2 expression", "TRANSFORMED_EXPRESSION"),
    ],
)
def test_expression_types_from_source_and_content(description, dtype):
    result = inspect_matrix(
        io.BytesIO(b"gene_id\ta\tb\nENSG1.2\t2\t3\nENSG2.1\t0\t0\n"),
        metadata_samples=["b", "a"],
        source_evidence={
            "processing_description": description,
            "source_url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE1",
            "response_sha256": "a" * 64,
        },
    )
    assert result["data_type"] == dtype and result["all_zero_features"] == 1


@pytest.mark.parametrize(
    "matrix,error",
    [
        (b"gene_id\ta\ta\ng1\t2\t3\n", "MISSING_OR_DUPLICATE_SAMPLES"),
        (b"sample_id\tg1\tg2\na\t2\t3\n", "ORIENTATION_UNKNOWN"),
        (b"gene_id\ta\tb\ng1\t2\t3\ng1\t3\t4\n", "INVALID_OR_DUPLICATE_FEATURE"),
        (b"gene_id\ta\tb\ng1\t-2\tNA\n", "MISSING_NEGATIVE_OR_NONNUMERIC_VALUE"),
        (b"gene_id\ta\tb\ng1\t2.5\t3\n", "NON_INTEGER_COUNTS"),
        (b"gene_id\ta\tb\ng1\t2\n", "ROW_WIDTH_MISMATCH"),
    ],
)
def test_bad_matrix_refused(matrix, error):
    result = inspect_matrix(io.BytesIO(matrix), metadata_samples=["a", "b"])
    assert error in result["errors"] and result["data_type"] != "RAW_INTEGER_COUNTS"


def test_matrix_and_fastq_limits_and_fastq_content():
    with pytest.raises(ValidationError, match="预算"):
        inspect_matrix(io.BytesIO(b"gene_id\ta\nb\t1\nc\t2\n"), limits=ValidationLimits(max_rows=1))
    with pytest.raises(ValidationError, match="预算"):
        inspect_matrix(
            io.BytesIO(b"gene_id\ta\n" + b"X" * 100), limits=ValidationLimits(max_line_bytes=20)
        )
    assert inspect_fastq(io.BytesIO(b"@read1\nACGT\n+\nIIII\n"))["reads"] == 1
    with pytest.raises(ValidationError, match="截断"):
        inspect_fastq(io.BytesIO(b"@r\nACGT\n+\n"))
    assert inspect_content(io.BytesIO(b"binary"), "x.h5ad")["data_type"] == "UNKNOWN"


def test_owned_file_rejects_symlinks_hardlinks_special_and_checksum_budget(tmp_path):
    root = tmp_path / "owned"
    root.mkdir()
    file = root / "a.tsv"
    file.write_bytes(b"gene_id\ta\ng1\t2\n")
    with open_owned_file(file, root) as stream:
        digest, size = checksum(stream, ValidationLimits())
    assert size == file.stat().st_size and len(digest) == 64
    (root / "sym").symlink_to(file)
    with pytest.raises(ValidationError):
        open_owned_file(root / "sym", root)
    os.link(file, root / "hard")
    with pytest.raises(ValidationError):
        open_owned_file(file, root)
    with pytest.raises(ValidationError):
        checksum(io.BytesIO(b"x" * 20), ValidationLimits(max_bytes=10))


@pytest.mark.parametrize("name", ["../escape", "/escape", "dir/../../escape", "a\\b", "C:/escape"])
def test_zip_slip_rejected_without_partial_output(tmp_path, name):
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as z:
        z.writestr(name, b"evil")
    with pytest.raises(ValidationError):
        expand_archive(blob, "x.zip", tmp_path / "stage")
    assert not (tmp_path / "stage").exists() and not (tmp_path / "escape").exists()


def test_archive_symlink_hardlink_bomb_and_valid_expansion(tmp_path):
    for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE):
        blob = io.BytesIO()
        with tarfile.open(fileobj=blob, mode="w") as tar:
            member = tarfile.TarInfo("link")
            member.type, member.linkname = kind, "../escape"
            tar.addfile(member)
        with pytest.raises(ValidationError):
            expand_archive(blob, "x.tar", tmp_path / "stage")
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("bomb", b"0" * 10000)
    with pytest.raises(ValidationError, match="预算"):
        expand_archive(blob, "x.zip", tmp_path / "stage", limits=ArchiveLimits(max_file_bytes=100))
    good = io.BytesIO()
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("nested/counts.tsv", b"gene_id\ta\ng1\t2\n")
    files = expand_archive(good, "x.zip", tmp_path / "stage")
    assert len(files) == 1 and files[0].read_bytes().startswith(b"gene_id")
