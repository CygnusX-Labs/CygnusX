"""Actual R/DESeq2 and Snakemake on synthetic inputs; no platform queue/Worker."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml

from cygnusx.application.services.flow_service import FlowService
from cygnusx.core.exceptions import NotFoundError
from cygnusx.domain.flow.entities import FlowConfig

pytestmark = pytest.mark.unit
SCRIPT = Path("pipelines/CountsDEGFlow/scripts/counts_deg.R").resolve()


@pytest.fixture
def counts_fixture(tmp_path):
    rscript = shutil.which("Rscript")
    if not rscript:
        pytest.skip("Rscript unavailable: real statistical execution BLOCKED")
    counts = tmp_path / "counts.tsv"
    metadata = tmp_path / "samples.tsv"
    params = tmp_path / "parameters.json"
    rng = np.random.default_rng(123)
    values = rng.negative_binomial(20, 0.2, size=(200, 6))
    values[:20, 3:] *= 4
    values[-1, :] = 0
    with counts.open("w") as stream:
        stream.write("gene_id\t" + "\t".join(f"s{i}" for i in range(6)) + "\n")
        for i, row in enumerate(values):
            stream.write(f"ENSG{i}.1\t" + "\t".join(map(str, row)) + "\n")
    metadata.write_text(
        "sample_id\tgroup\tbatch\n"
        + "".join(
            f"s{i}\t{'control' if i < 3 else 'treated'}\t{'a' if i % 2 == 0 else 'b'}\n"
            for i in range(6)
        )
    )
    parameters = dict(
        input_type="raw_integer_counts",
        source_reviewed=True,
        design="~ group",
        reference="control",
        treatment="treated",
        alpha=0.05,
        fit_type="mean",
    )
    params.write_text(json.dumps(parameters))
    return rscript, counts, metadata, params, parameters, tmp_path / "results"


def run_r(fixture):
    rscript, counts, metadata, params, _, output = fixture
    return subprocess.run(
        [rscript, "--vanilla", str(SCRIPT), str(counts), str(metadata), str(params), str(output)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_counts_declared_contract_hidden_by_default():
    config = FlowConfig.model_validate(yaml.safe_load(Path("flows/counts_deg.yaml").read_text()))
    assert config.meta.id == "counts_deg"
    assert "counts_deg" not in {f.id for f in FlowService().list_flows().items}
    with pytest.raises(NotFoundError):
        FlowService().get_flow_config("counts_deg")


def test_actual_deseq2_reference_regression(counts_fixture):
    rscript, counts, metadata, params, _, output = counts_fixture
    completed = run_r(counts_fixture)
    assert completed.returncode == 0, completed.stderr
    reference = output.parent / "reference.R"
    expected = output.parent / "reference.tsv"
    # Independent direct library invocation with an explicit contrast and same declared fit.
    reference.write_text("""suppressPackageStartupMessages(library(DESeq2))
a <- commandArgs(TRUE)
c <- read.delim(a[1],row.names=1,check.names=FALSE)
m <- read.delim(a[2],row.names=1,check.names=FALSE)
m$group <- relevel(factor(m$group),ref="control")
d <- DESeqDataSetFromMatrix(as.matrix(c[rowSums(c)>0,]),m,~group)
d <- DESeq(d,fitType="mean",quiet=TRUE,parallel=FALSE)
r <- results(d,contrast=c("group","treated","control"),alpha=0.05)
write.table(data.frame(gene_id=rownames(r),as.data.frame(r)),a[3],sep="\\t",quote=FALSE,row.names=FALSE,na="NA")
""")
    result = subprocess.run(
        [rscript, "--vanilla", str(reference), str(counts), str(metadata), str(expected)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    with (output / "deg.tsv").open() as stream:
        actual = list(csv.DictReader(stream, delimiter="\t"))
    with expected.open() as stream:
        ref = list(csv.DictReader(stream, delimiter="\t"))
    assert len(actual) == len(ref) == 199
    for observed, truth in zip(actual, ref, strict=True):
        assert observed["gene_id"] == truth["gene_id"]
        for column in ("baseMean", "log2FoldChange", "lfcSE", "stat", "pvalue", "padj"):
            if truth[column] == "NA":
                assert observed[column] == "NA"
            else:
                assert float(observed[column]) == pytest.approx(
                    float(truth[column]), rel=1e-8, abs=1e-10
                )
    manifest = json.loads((output / "result_manifest.json").read_text())
    assert manifest["qc"]["all_zero_features"] == 1
    assert manifest["versions"]["DESeq2"] == "1.48.2"
    assert (output / "qc.pdf").stat().st_size > 0
    assert (output / "session_info.txt").is_file()


@pytest.mark.parametrize(
    "change,error",
    [
        ({"input_type": "TPM"}, "RAW_INTEGER_COUNTS_REQUIRED"),
        ({"source_reviewed": False}, "SOURCE_AND_SAMPLE_REVIEW_REQUIRED"),
        ({"design": "~ batch * group"}, "DESIGN_NOT_SUPPORTED"),
        ({"reference": "missing"}, "EXPLICIT_CONTRAST_REQUIRED"),
    ],
)
def test_counts_statistical_contract_negative(counts_fixture, change, error):
    *_, params, parameters, output = counts_fixture
    params.write_text(json.dumps({**parameters, **change}))
    completed = run_r(counts_fixture)
    assert completed.returncode != 0 and error in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "case,error",
    [
        ("fraction", "NON_INTEGER_OR_INVALID_COUNTS"),
        ("unreplicated", "BIOLOGICAL_REPLICATION_REQUIRED"),
        ("confounded", "DESIGN_NOT_ESTIMABLE"),
        ("duplicate", "DUPLICATE_OR_MISSING_IDS"),
    ],
)
def test_bad_counts_and_design_never_run_deseq2(counts_fixture, case, error):
    _, counts, metadata, params, parameters, output = counts_fixture
    if case == "fraction":
        lines = counts.read_text().splitlines()
        parts = lines[1].split("\t")
        parts[1] = "2.5"
        lines[1] = "\t".join(parts)
        counts.write_text("\n".join(lines) + "\n")
    elif case == "duplicate":
        lines = counts.read_text().splitlines()
        lines[2] = lines[1]
        counts.write_text("\n".join(lines) + "\n")
    elif case == "unreplicated":
        metadata.write_text(
            metadata.read_text()
            .replace("s1\tcontrol", "s1\ttreated")
            .replace("s2\tcontrol", "s2\ttreated")
        )
    else:
        metadata.write_text(
            "sample_id\tgroup\tbatch\n"
            + "".join(
                f"s{i}\t{'control' if i < 3 else 'treated'}\t{'a' if i < 3 else 'b'}\n"
                for i in range(6)
            )
        )
        params.write_text(json.dumps({**parameters, "design": "~ batch + group"}))
    completed = run_r(counts_fixture)
    assert completed.returncode != 0 and error in completed.stderr
    assert not output.exists()


def test_actual_snakemake_synthetic_counts_flow(counts_fixture):
    binary = shutil.which("snakemake")
    if not binary:
        pytest.skip("Snakemake unavailable: Flow execution BLOCKED")
    _, counts, metadata, _, parameters, output = counts_fixture
    analysis = output.parent / "analysis.yaml"
    work = output.parent / "flow-work"
    analysis.write_text(
        yaml.safe_dump(
            {
                **parameters,
                "workflow": str(work),
                "count_matrix": str(counts),
                "sample_metadata": str(metadata),
            }
        )
    )
    completed = subprocess.run(
        [
            binary,
            "--snakefile",
            str(Path("pipelines/CountsDEGFlow/snakefile").resolve()),
            "--cores",
            "1",
            "--config",
            f"analysisyaml={analysis}",
            "--directory",
            str(output.parent),
            "--nolock",
            "--conda-prefix",
            str(output.parent / "conda-cache"),
            "--runtime-source-cache-path",
            str(output.parent / "source-cache"),
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    input_manifest = json.loads((work / "input_manifest.json").read_text())
    assert len(input_manifest["assets"]) == 2
    assert all(len(a["sha256"]) == 64 for a in input_manifest["assets"])
    assert (work / "results" / "deg.tsv").is_file()
    assert (work / "counts_deg.log").is_file()
