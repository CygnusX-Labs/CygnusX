import pytest

from cygnusx.api.v1.files import _validate_chat_upload_filename
from cygnusx.core.exceptions import ValidationError


@pytest.mark.parametrize(
    "filename",
    [
        "sample.bam",
        "sample.cram",
        "cells.h5ad",
        "object.rds",
        "integration_harmony.qs",
        "bundle.zip",
        "matrix.parquet",
        "values.npy",
        "flow.fcs",
        "spectra.mzML",
        "peaks.mzXML",
        "library.mgf",
        "instrument.raw",
        "signal.bw",
        "signal.bigwig",
        "calls.bcf",
        "variants.maf",
        "array.idat",
        "array.cel",
        "qiime.qza",
        "qiime.qzv",
    ],
)
def test_chat_upload_routes_managed_data_files_to_file_management(filename: str) -> None:
    with pytest.raises(ValidationError, match="文件管理"):
        _validate_chat_upload_filename(filename)


@pytest.mark.parametrize(
    "filename",
    [
        "plot.png",
        "metadata.csv",
        "report.pdf",
        "genes.fasta",
        "counts.xlsx",
        "counts.xlsm",
        "legacy.xls",
        "slides.pptx",
        "legacy.ppt",
        "table.ods",
        "notes.odt",
        "analysis.ipynb",
        "refs.bib",
        "refs.ris",
        "genes.gmt",
        "ranked.rnk",
        "analysis.Rmd",
        "analysis.qmd",
        "pipeline.sh",
        "query.sql",
        "config.toml",
        "protein.pdb",
        "structure.cif",
        "ligand.sdf",
        "ligand.xyz",
        "mail.eml",
        "table.biom",
        "data.h5",
        "data.hdf5",
        "data.mat",
        "figure.tif",
        "figure.tiff",
        "legacy.xlsb",
        "counts.csv.gz",
    ],
)
def test_chat_upload_keeps_lightweight_files_available(filename: str) -> None:
    _validate_chat_upload_filename(filename)
