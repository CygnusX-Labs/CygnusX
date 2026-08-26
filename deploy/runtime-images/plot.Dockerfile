ARG CYGNUSX_IMAGE_TAG=v0.0.2dev
FROM cygnusx-analysis:core-${CYGNUSX_IMAGE_TAG}

LABEL org.opencontainers.image.title="CygnusX Analysis Plot"
LABEL org.cygnusx.runtime.profile="analysis-plot"

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
    && chown $MAMBA_USER:$MAMBA_USER /home/mambauser/.condarc

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
