# syntax=docker/dockerfile:1.7
ARG CYGNUSX_IMAGE_TAG=v0.0.2dev
FROM cygnusx-analysis:core-${CYGNUSX_IMAGE_TAG}

ARG SANDBOX_GID=10001
ARG TOOLS_MANIFEST_DIGEST=unknown

LABEL org.opencontainers.image.title="CygnusX Analysis Plot"
LABEL org.cygnusx.runtime.profile="analysis-plot"
LABEL org.cygnusx.tools-manifest.path="/opt/agent-tools.json"
LABEL org.cygnusx.tools-manifest.digest="${TOOLS_MANIFEST_DIGEST}"

USER root

# 构建期切换中科大 apt 源，加速 apt-get（兼容 debian.sources 与旧版 sources.list）
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's@//deb.debian.org@//mirrors.ustc.edu.cn@g; s@//security.debian.org@//mirrors.ustc.edu.cn@g' /etc/apt/sources.list.d/debian.sources; \
    else \
        sed -i 's@//deb.debian.org@//mirrors.ustc.edu.cn@g; s@//security.debian.org@//mirrors.ustc.edu.cn@g' /etc/apt/sources.list; \
    fi

# 预置中科大镜像源，加速 bioconda 包下载（见 Protocol/镜像构建国内加速规范_v1.md §4）；
# 安装以 mambauser 执行，condarc 必须落在其 HOME。
RUN printf '%s\n' \
      'show_channel_urls: true' \
      'default_channels:' \
      '  - https://mirrors.ustc.edu.cn/anaconda/pkgs/main' \
      '  - https://mirrors.ustc.edu.cn/anaconda/pkgs/free' \
      '  - https://mirrors.ustc.edu.cn/anaconda/pkgs/r' \
      '  - https://mirrors.ustc.edu.cn/anaconda/pkgs/msys2' \
      'custom_channels:' \
      '  conda-forge: https://mirrors.ustc.edu.cn/anaconda/cloud' \
      '  bioconda: https://mirrors.ustc.edu.cn/anaconda/cloud' \
      '  menpo: https://mirrors.ustc.edu.cn/anaconda/cloud' \
      'channel_priority: flexible' \
      'channels:' \
      '  - conda-forge' \
      '  - bioconda' \
      '  - menpo' \
      '  - defaults' \
      > /home/mambauser/.condarc \
    && chown "$MAMBA_USER:$SANDBOX_GID" /home/mambauser/.condarc

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

USER "$MAMBA_USER"
RUN --mount=type=cache,target=/opt/conda/pkgs,uid=10001,gid=10001,sharing=locked \
    micromamba install -y -n base -c conda-forge -c bioconda \
      matplotlib=3.9.2 \
      seaborn=0.13.2 \
      plotly=5.24.1 \
      r-ggplot2=3.5.1 \
      r-dplyr \
      r-stringr \
      r-ggrepel \
      r-ggpubr=0.6.0 \
      r-patchwork=1.3.0 \
      r-plotly=4.10.4 \
      r-cairo=1.6_2 \
      r-ape \
      r-phytools \
      bioconductor-ggtree \
      bioconductor-treeio

# 强制校验绘图栈必需包可加载（library 级，与 deploy/docker/Dockerfile.deg 同口径）；
# 可视化提示词约定 ggpubr::theme_pubclean() 为 R 出图默认主题
# （data/ai/prompts/visualization.md），缺包直接构建失败。
RUN micromamba run -n base R -q -e '\
      required <- c("ggplot2", "ggrepel", "ggpubr", "patchwork", "scales", "dplyr", "stringr"); \
      failed <- character(0); \
      for (p in required) { \
        ok <- tryCatch({ suppressPackageStartupMessages(library(p, character.only = TRUE)); TRUE }, \
                       error = function(e) { cat("LOAD FAIL", p, ":", conditionMessage(e), "\n"); FALSE }); \
        if (!ok) failed <- c(failed, p); \
      }; \
      if (length(failed)) stop("plot image missing required R packages: ", paste(failed, collapse = ", ")); \
      cat("plot runtime OK: all", length(required), "packages loadable, ", R.version.string, "\n")'

COPY deploy/runtime-images/scripts/render_tools_manifest.py /opt/cygnusx/render_tools_manifest.py
COPY deploy/runtime-images/scripts/validate_manifest.py /opt/cygnusx/validate_manifest.py
USER root
RUN micromamba run -n base python /opt/cygnusx/render_tools_manifest.py \
      --profile analysis-plot \
      --image cygnusx-analysis:plot-v0.0.2dev \
      --base /opt/agent-tools.json \
      --output /opt/agent-tools.json \
      --python-import matplotlib:matplotlib \
      --python-import seaborn:seaborn \
      --python-import plotly:plotly \
      --r-library r-ggplot2:ggplot2 \
      --r-library r-dplyr:dplyr \
      --r-library r-stringr:stringr \
      --r-library r-ggrepel:ggrepel \
      --r-library r-ggpubr:ggpubr \
      --r-library bioconductor-ggtree:ggtree \
      --r-library bioconductor-treeio:treeio \
      --r-library r-ape:ape \
      --r-library r-patchwork:patchwork \
      --r-library r-plotly:plotly \
      --r-library r-cairo:Cairo \
      --r-library r-phytools:phytools
RUN micromamba run -n base python /opt/cygnusx/validate_manifest.py \
      --profile analysis-plot \
      --manifest /opt/agent-tools.json
USER mambauser
