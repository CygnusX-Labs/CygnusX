# syntax=docker/dockerfile:1.7
ARG CYGNUSX_IMAGE_TAG=v0.0.2dev
FROM cygnusx-analysis:core-${CYGNUSX_IMAGE_TAG}

ARG TOOLS_MANIFEST_DIGEST=unknown
LABEL org.cygnusx.runtime.profile="analysis-rnaseq"
LABEL org.cygnusx.tools-manifest.path="/opt/agent-tools.json"
LABEL org.cygnusx.tools-manifest.digest="${TOOLS_MANIFEST_DIGEST}"

USER mambauser
RUN --mount=type=cache,target=/opt/conda/pkgs,uid=10001,gid=10001,sharing=locked \
    micromamba install -y -n base -c bioconda -c conda-forge \
      star salmon rsem samtools fastp multiqc subread \
    && micromamba clean -a -y

RUN micromamba run -n base sh -c ' \
    for t in STAR salmon rsem-calculate-expression samtools fastp multiqc featureCounts; do \
      command -v "$t" >/dev/null || { echo "MISSING: $t"; exit 1; }; \
    done; \
    echo "rnaseq runtime OK"'

COPY deploy/runtime-images/scripts/render_tools_manifest.py /opt/cygnusx/render_tools_manifest.py
COPY deploy/runtime-images/scripts/validate_manifest.py /opt/cygnusx/validate_manifest.py
USER root
RUN micromamba run -n base python /opt/cygnusx/render_tools_manifest.py \
      --profile analysis-rnaseq \
      --image cygnusx-analysis:rnaseq-v0.0.1dev \
      --base /opt/agent-tools.json \
      --output /opt/agent-tools.json \
      --tool star:STAR \
      --tool salmon:salmon \
      --tool rsem:rsem-calculate-expression \
      --tool samtools:samtools \
      --tool fastp:fastp \
      --tool multiqc:multiqc \
      --tool subread:featureCounts
RUN micromamba run -n base python /opt/cygnusx/validate_manifest.py \
      --profile analysis-rnaseq \
      --manifest /opt/agent-tools.json
USER mambauser
