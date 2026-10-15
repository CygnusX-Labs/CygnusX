#!/usr/bin/env Rscript
# Gene x sample raw integer counts only. No rounding, normalization inversion or code eval.
suppressPackageStartupMessages(library(jsonlite))
args <- commandArgs(trailingOnly=TRUE)
if (length(args) != 4L) stop("usage: counts_deg.R counts.tsv metadata.tsv parameters.json output_dir")
counts_path <- args[[1]]; metadata_path <- args[[2]]; params_path <- args[[3]]; output <- args[[4]]
params <- fromJSON(params_path, simplifyVector=TRUE)
if (!identical(params$input_type, "raw_integer_counts")) stop("RAW_INTEGER_COUNTS_REQUIRED")
if (!isTRUE(params$source_reviewed)) stop("SOURCE_AND_SAMPLE_REVIEW_REQUIRED")
if (dir.exists(output) && length(list.files(output, all.files=TRUE, no..=TRUE))>0L) stop("OUTPUT_EXISTS_NO_OVERWRITE")
if (file.info(counts_path)$size > 64*1024^2 || file.info(metadata_path)$size > 4*1024^2) stop("INPUT_BUDGET_EXCEEDED")
counts <- read.delim(counts_path, check.names=FALSE, stringsAsFactors=FALSE)
metadata <- read.delim(metadata_path, check.names=FALSE, stringsAsFactors=FALSE)
if (ncol(counts)<3L || !identical(names(counts)[[1]], "gene_id")) stop("GENE_BY_SAMPLE_REQUIRED")
if (anyDuplicated(names(counts)) || anyDuplicated(counts[[1]]) || anyNA(counts[[1]]) || any(!nzchar(counts[[1]]))) stop("DUPLICATE_OR_MISSING_IDS")
if (!all(c("sample_id", "group") %in% names(metadata)) || anyDuplicated(metadata$sample_id)) stop("UNIQUE_SAMPLE_METADATA_REQUIRED")
if (!setequal(names(counts)[-1], metadata$sample_id)) stop("METADATA_SAMPLE_MISMATCH")
metadata <- metadata[match(names(counts)[-1], metadata$sample_id),,drop=FALSE]
rownames(metadata) <- metadata$sample_id
mat <- as.matrix(counts[,-1,drop=FALSE])
if (!is.numeric(mat) || anyNA(mat) || any(!is.finite(mat)) || any(mat<0) || any(mat!=floor(mat)) || any(mat>.Machine$integer.max)) stop("NON_INTEGER_OR_INVALID_COUNTS")
rownames(mat) <- counts[[1]]; storage.mode(mat) <- "integer"
if (nrow(mat)>200000L || ncol(mat)>1000L) stop("MATRIX_BUDGET_EXCEEDED")
if (anyNA(metadata$group) || any(!nzchar(metadata$group)) || length(unique(metadata$group))<2L) stop("TWO_GROUPS_REQUIRED")
reference <- params$reference; treatment <- params$treatment
if (length(reference)!=1L || length(treatment)!=1L || identical(reference,treatment) || !all(c(reference,treatment) %in% metadata$group)) stop("EXPLICIT_CONTRAST_REQUIRED")
metadata$group <- relevel(factor(metadata$group), ref=reference)
if (any(table(metadata$group)<2L)) stop("BIOLOGICAL_REPLICATION_REQUIRED")
# Deliberately restrict designs rather than eval(parse()) on user formulas.
if (identical(params$design, "~ group")) {
    design <- ~ group
} else if (identical(params$design, "~ batch + group")) {
    if (!"batch" %in% names(metadata) || anyNA(metadata$batch) || any(!nzchar(metadata$batch))) stop("BATCH_METADATA_REQUIRED")
    metadata$batch <- factor(metadata$batch)
    design <- ~ batch + group
} else stop("DESIGN_NOT_SUPPORTED")
mm <- model.matrix(design, metadata)
if (qr(mm)$rank < ncol(mm) || nrow(mm)<=ncol(mm)) stop("DESIGN_NOT_ESTIMABLE")
keep <- rowSums(mat)>0L
if (!any(keep)) stop("ALL_FEATURES_ZERO")
alpha <- params$alpha
if (length(alpha)!=1L || !is.numeric(alpha) || alpha<=0 || alpha>=1) stop("INVALID_ALPHA")
fit_type <- if (is.null(params$fit_type)) "parametric" else params$fit_type
if (!fit_type %in% c("parametric", "local", "mean")) stop("INVALID_FIT_TYPE")
suppressPackageStartupMessages(library(DESeq2))
set.seed(1)
dds <- DESeqDataSetFromMatrix(countData=mat[keep,,drop=FALSE], colData=metadata, design=design)
dds <- DESeq(dds, fitType=fit_type, quiet=TRUE, parallel=FALSE)
res <- results(dds, contrast=c("group", treatment, reference), alpha=alpha)
# No LFC shrinkage is claimed. Report DESeq2's explicit unshrunken Wald result.
result <- data.frame(gene_id=rownames(res), as.data.frame(res), check.names=FALSE)
if (!dir.exists(output)) dir.create(output, recursive=FALSE)
write.table(result, file.path(output,"deg.tsv"), sep="\t", quote=FALSE, row.names=FALSE, na="NA")
write.table(data.frame(sample_id=colnames(dds), size_factor=sizeFactors(dds), library_size=colSums(mat)), file.path(output,"sample_qc.tsv"), sep="\t", quote=FALSE, row.names=FALSE)
pdf(file.path(output,"qc.pdf"))
plotMA(res, alpha=alpha, main=paste(treatment,"vs",reference))
plotDispEsts(dds)
dev.off()
write_json(list(schema_version="1.0", parameters=params, versions=list(R=R.version.string, DESeq2=as.character(packageVersion("DESeq2")), jsonlite=as.character(packageVersion("jsonlite"))),
    input=list(count_matrix=basename(counts_path), sample_metadata=basename(metadata_path)),
    qc=list(samples=ncol(mat), features=nrow(mat), all_zero_features=sum(!keep), design_rank=qr(mm)$rank, residual_df=nrow(mm)-ncol(mm), group_sizes=as.list(table(metadata$group))),
    limitations=c("unshrunken_Wald_effects", "source_review_is_required_not_inferred_from_integer_values", if(any(table(metadata$group)<3L)) "two_replicates_exploratory" else "replication_does_not_prove_design_validity"),
    outputs=c("deg.tsv","sample_qc.tsv","qc.pdf","session_info.txt")), file.path(output,"result_manifest.json"), auto_unbox=TRUE, pretty=TRUE)
writeLines(capture.output(sessionInfo()), file.path(output,"session_info.txt"))
