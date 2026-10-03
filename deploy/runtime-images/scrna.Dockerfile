# syntax=docker/dockerfile:1.7
# The single-cell image extends the plotting runtime.  Using ``scrna-*`` here
# would make the image inherit from itself and force Docker to pull a
# non-existent registry repository when the tag is not already present.
ARG CYGNUSX_IMAGE_TAG=v0.0.2dev
FROM cygnusx-analysis:plot-${CYGNUSX_IMAGE_TAG}

ARG SANDBOX_GID=10001
ARG TOOLS_MANIFEST_DIGEST=unknown

LABEL org.opencontainers.image.title="CygnusX Analysis Single Cell"
LABEL org.cygnusx.runtime.profile="analysis-scrna"
LABEL org.cygnusx.tools-manifest.path="/opt/agent-tools.json"
LABEL org.cygnusx.tools-manifest.digest="${TOOLS_MANIFEST_DIGEST}"

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

USER "$MAMBA_USER"
RUN --mount=type=cache,target=/opt/conda/pkgs,uid=10001,gid=10001,sharing=locked \
    micromamba install -y -n base -c conda-forge -c bioconda \
      r-data.table=1.18.6.1 \
      r-ggpubr=0.6.0 \
      r-ggsci=5.2.0 \
      r-patchwork=1.3.0 \
      r-scales=1.4.0

# 单细胞栈：Python（Scanpy/AnnData/Leiden）+ R（Seurat 5.5 / SingleCellExperiment），
# 与 data/ai/runtime_images.yaml analysis-scrna.software 声明一一对应。
RUN --mount=type=cache,target=/opt/conda/pkgs,uid=10001,gid=10001,sharing=locked \
    micromamba install -y -n base -c conda-forge -c bioconda \
      scanpy=1.10.4 \
      anndata=0.11.1 \
      leidenalg=0.10.2 \
      python-igraph=0.11.8 \
      r-seurat=5.5.1 \
      bioconductor-singlecellexperiment=1.28.0 \
      bioconductor-genomeinfodbdata

# micromamba 不执行 conda post-link 脚本：bioconductor 数据包（GenomeInfoDbData）
# 随包 tarball 是 0 字节占位符，必须运行官方 post-link 助手按 dataURLs.json 下载
# 真实 tarball 并 R CMD INSTALL；curl/yq 随该包安装，PREFIX 是 post-link 约定变量。
RUN PREFIX=/opt/conda micromamba run -n base installBiocDataPackage.sh genomeinfodbdata-1.2.13

# 强制校验单细胞栈可加载（import/library 级，与 plot.Dockerfile 同口径）；
# 缺包直接构建失败，避免运行时才发现声明与镜像不符。
RUN micromamba run -n base python -c 'import scanpy, anndata, leidenalg, igraph; print("scrna python stack OK: scanpy", scanpy.__version__, "anndata", anndata.__version__)' \
    && micromamba run -n base R -q -e '\
      required <- c("Seurat", "SingleCellExperiment"); \
      failed <- character(0); \
      for (p in required) { \
        ok <- tryCatch({ suppressPackageStartupMessages(library(p, character.only = TRUE)); TRUE }, \
                       error = function(e) { cat("LOAD FAIL", p, ":", conditionMessage(e), "\n"); FALSE }); \
        if (!ok) failed <- c(failed, p); \
      }; \
      if (length(failed)) stop("scrna image missing required R packages: ", paste(failed, collapse = ", ")); \
      cat("scrna R stack OK\n")'

COPY deploy/runtime-images/scripts/render_tools_manifest.py /opt/cygnusx/render_tools_manifest.py
COPY deploy/runtime-images/scripts/validate_manifest.py /opt/cygnusx/validate_manifest.py
USER root
RUN micromamba run -n base python /opt/cygnusx/render_tools_manifest.py \
      --profile analysis-scrna \
      --image cygnusx-analysis:scrna-v0.0.3dev \
      --base /opt/agent-tools.json \
      --output /opt/agent-tools.json \
      --python-import scanpy:scanpy \
      --python-import anndata:anndata \
      --python-import leidenalg:leidenalg \
      --python-import python-igraph:igraph \
      --r-library r-seurat:Seurat \
      --r-library r-ggpubr:ggpubr \
      --r-library bioconductor-singlecellexperiment:SingleCellExperiment
RUN micromamba run -n base python /opt/cygnusx/validate_manifest.py \
      --profile analysis-scrna \
      --manifest /opt/agent-tools.json
USER mambauser
# 注意：r-qs 因与 RcppParallel/Seurat 存在 ABI 冲突，暂不预装
# 如需使用 .qs 格式，可在沙盒内手动安装：
#   micromamba install r-qs=0.25.7 --force-reinstall
#   # 或升级 Seurat 到兼容版本后安装最新 r-qs
