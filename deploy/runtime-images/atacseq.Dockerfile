# syntax=docker/dockerfile:1.7
ARG CYGNUSX_IMAGE_TAG=v0.0.2dev
FROM cygnusx-analysis:core-${CYGNUSX_IMAGE_TAG}

ARG TOOLS_MANIFEST_DIGEST=unknown
LABEL org.cygnusx.runtime.profile="analysis-atacseq"
LABEL org.cygnusx.tools-manifest.path="/opt/agent-tools.json"
LABEL org.cygnusx.tools-manifest.digest="${TOOLS_MANIFEST_DIGEST}"

USER mambauser
RUN --mount=type=cache,target=/opt/conda/pkgs,uid=10001,gid=10001,sharing=locked \
    micromamba install -y -n base -c bioconda -c conda-forge \
      bowtie2 chromap macs3 samtools bedtools deeptools fastp multiqc \
    && ln -sf /opt/conda/bin/macs3 /opt/conda/bin/macs2

RUN micromamba run -n base sh -c ' \
    for t in bowtie2 chromap macs2 samtools bedtools bamCoverage fastp multiqc; do \
      command -v "$t" >/dev/null || { echo "MISSING: $t"; exit 1; }; \
    done; \
    echo "atacseq runtime OK"'

COPY deploy/runtime-images/scripts/render_tools_manifest.py /opt/cygnusx/render_tools_manifest.py
COPY deploy/runtime-images/scripts/validate_manifest.py /opt/cygnusx/validate_manifest.py
COPY data/ai/runtime_images.yaml /opt/cygnusx/runtime_images.yaml
USER root
RUN micromamba run -n base python /opt/cygnusx/render_tools_manifest.py \
      --profile analysis-atacseq \
      --image cygnusx-analysis:atacseq-v0.0.1dev \
      --base /opt/agent-tools.json \
      --output /opt/agent-tools.json \
      --tool bowtie2:bowtie2 \
      --tool chromap:chromap \
      --tool macs2:macs2 \
      --tool samtools:samtools \
      --tool bedtools:bedtools \
      --tool deeptools:bamCoverage \
      --tool fastp:fastp \
      --tool multiqc:multiqc
RUN micromamba run -n base python /opt/cygnusx/validate_manifest.py \
      --profile analysis-atacseq \
      --manifest /opt/agent-tools.json \
      --registry /opt/cygnusx/runtime_images.yaml
USER mambauser
