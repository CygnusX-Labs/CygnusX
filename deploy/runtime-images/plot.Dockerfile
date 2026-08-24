ARG CYGNUSX_IMAGE_TAG=v0.0.2dev
FROM cygnusx-analysis:core-${CYGNUSX_IMAGE_TAG}

LABEL org.opencontainers.image.title="CygnusX Analysis Plot"
LABEL org.cygnusx.runtime.profile="analysis-plot"

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

USER "$MAMBA_USER"
RUN micromamba install -y -n base -c conda-forge -c bioconda \
      matplotlib=3.9.2 \
      seaborn=0.13.2 \
      plotly=5.24.1 \
      r-ggplot2=3.5.1 \
      r-dplyr \
      r-stringr \
      r-ggrepel \
      r-patchwork=1.3.0 \
      r-plotly=4.10.4 \
      r-cairo=1.6_2 \
      r-ape \
      r-phytools \
      bioconductor-ggtree \
      bioconductor-treeio \
    && micromamba clean --all --yes
