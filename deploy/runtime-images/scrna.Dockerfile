ARG CYGNUSX_IMAGE_TAG=v0.0.2dev
FROM cygnusx-analysis:plot-${CYGNUSX_IMAGE_TAG}

LABEL org.opencontainers.image.title="CygnusX Analysis Single Cell"
LABEL org.cygnusx.runtime.profile="analysis-scrna"

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
    && chown $MAMBA_USER:$MAMBA_USER /home/mambauser/.condarc

USER "$MAMBA_USER"
RUN micromamba install -y -n base -c conda-forge -c bioconda \
      scanpy=1.10.4 \
      anndata=0.11.1 \
      leidenalg=0.10.2 \
      python-igraph=0.11.8 \
      h5py=3.12.1 \
      r-seurat=5.1.0 \
      bioconductor-singlecellexperiment=1.28.0 \
    && micromamba clean --all --yes
