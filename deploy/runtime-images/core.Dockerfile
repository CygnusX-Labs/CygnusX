# syntax=docker/dockerfile:1.7
FROM mambaorg/micromamba:2.0.5

ARG SANDBOX_UID=10001
ARG SANDBOX_GID=10001
ARG SANDBOX_GROUP=cygnusx-sandbox
ARG TOOLS_MANIFEST_DIGEST=unknown

LABEL org.opencontainers.image.title="CygnusX Analysis Core"
LABEL org.opencontainers.image.description="Independent micromamba Python/R task runtime for OmicStudio and toolbox executors"
LABEL org.cygnusx.runtime.family="cygnusx-analysis"
LABEL org.cygnusx.runtime.profile="analysis-core"
LABEL org.cygnusx.tools-manifest.path="/opt/agent-tools.json"
LABEL org.cygnusx.tools-manifest.digest="${TOOLS_MANIFEST_DIGEST}"

USER root
COPY deploy/studio/requirements-agent.txt /tmp/requirements-agent.txt
RUN usermod --uid "$SANDBOX_UID" "$MAMBA_USER" \
    && groupmod --gid "$SANDBOX_GID" "$MAMBA_USER" \
    && groupmod --new-name "$SANDBOX_GROUP" "$MAMBA_USER" \
    && chown -R "$SANDBOX_UID:$SANDBOX_GID" /home/"$MAMBA_USER" /opt/conda \
    && mkdir -p /opt/cygnusx \
    && chown -R "$SANDBOX_UID:$SANDBOX_GID" /opt/cygnusx /tmp/requirements-agent.txt \
    && mkdir -p /workspace/.logs \
    && chown -R "$SANDBOX_UID:$SANDBOX_GID" /workspace \
    && printf '%s\n' \
      '[global]' \
      'index-url = https://pypi.mirrors.ustc.edu.cn/simple' \
      'timeout = 60' \
      'retries = 3' \
      > /etc/pip.conf
# 构建期切换中科大 apt 源，加速 apt-get（兼容 debian.sources 与旧版 sources.list）
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's@//deb.debian.org@//mirrors.ustc.edu.cn@g; s@//security.debian.org@//mirrors.ustc.edu.cn@g' /etc/apt/sources.list.d/debian.sources; \
    else \
        sed -i 's@//deb.debian.org@//mirrors.ustc.edu.cn@g; s@//security.debian.org@//mirrors.ustc.edu.cn@g' /etc/apt/sources.list; \
    fi

USER "$MAMBA_USER"
# 预置中科大镜像源，加速容器内 micromamba/conda 环境安装
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
      '  pytorch: https://mirrors.ustc.edu.cn/anaconda/cloud' \
      'channel_priority: flexible' \
      'channels:' \
      '  - conda-forge' \
      '  - bioconda' \
      '  - menpo' \
      '  - defaults' \
      > ~/.condarc
RUN --mount=type=cache,target=/opt/conda/pkgs,uid=10001,gid=10001,sharing=locked \
    micromamba install -y -n base -c conda-forge -c bioconda \
      python=3.12 \
      r-base=4.4 \
      pip=24.3 \
      uv=0.5 \
      pandas=2.2.3 \
      numpy=2.1.3 \
      scipy=1.14.1 \
      scikit-learn=1.5.2 \
      statsmodels=0.14.4 \
      pyyaml=6.0.2 \
      openpyxl=3.1.5 \
      pyarrow=18.1.0 \
      bioconductor-deseq2=1.46.0 \
      bioconductor-edger=4.4.0 \
      bioconductor-limma=3.62.1 \
    && micromamba run -n base python -m pip install --prefer-binary -r /tmp/requirements-agent.txt

# agent 脚本变动频繁，放在重型依赖层之后，改动时不触发 micromamba 重装
COPY --chown=10001:10001 deploy/studio/sandbox_agent.py /opt/cygnusx/sandbox_agent.py

# sitecustomize.py：Python 启动时自动注入 show_plotly 图表回传 helper，
# 与聊天轻量沙盒（deploy/sandbox/sitecustomize.py）同一 %%PLOTLY%% 标记协议；
# plot/scrna 派生镜像自动继承本层
COPY --chown=10001:10001 deploy/studio/sitecustomize.py /opt/conda/lib/python3.12/site-packages/sitecustomize.py

# 终端体验工具（独立层，与科学生态栈解耦）：btop / zsh / oh-my-posh / oh-my-zsh
# 参考 tool_configs/terminal/docker/Dockerfile；plot/scrna 派生镜像自动继承本层
RUN --mount=type=cache,target=/opt/conda/pkgs,uid=10001,gid=10001,sharing=locked \
    micromamba install -y -n base -c conda-forge \
      btop \
      zsh \
      git \
      oh-my-posh \
    && micromamba run -n base git clone --depth 1 https://github.com/ohmyzsh/ohmyzsh.git /opt/cygnusx/oh-my-zsh
COPY --chown=10001:10001 deploy/studio/studio-zshrc /opt/cygnusx/zdotdir/.zshrc
COPY --chown=10001:10001 deploy/studio/studio.omp.json /opt/cygnusx/themes/studio.omp.json

# 构建期清单必须由当前镜像实际探测生成，不能只复制注册表声明。
COPY deploy/runtime-images/scripts/render_tools_manifest.py /opt/cygnusx/render_tools_manifest.py
COPY deploy/runtime-images/scripts/validate_manifest.py /opt/cygnusx/validate_manifest.py
COPY data/ai/runtime_images.yaml /opt/cygnusx/runtime_images.yaml
RUN micromamba run -n base python /opt/cygnusx/render_tools_manifest.py \
      --profile analysis-core \
      --image cygnusx-analysis:core-v0.0.2dev \
      --output /tmp/agent-tools.json \
      --tool python:python \
      --tool micromamba:micromamba \
      --tool Rscript:Rscript \
      --tool btop:btop \
      --tool zsh:zsh \
      --tool git:git \
      --tool oh-my-posh:oh-my-posh \
      --python-import pandas:pandas \
      --python-import numpy:numpy \
      --python-import scipy:scipy \
      --python-import scikit-learn:sklearn \
      --python-import statsmodels:statsmodels \
      --python-import pyyaml:yaml \
      --python-import openpyxl:openpyxl \
      --python-import pyarrow:pyarrow \
      --r-library bioconductor-deseq2:DESeq2 \
      --r-library r-edgeR:edgeR \
      --r-library r-limma:limma
RUN micromamba run -n base python /opt/cygnusx/validate_manifest.py \
      --profile analysis-core \
      --manifest /tmp/agent-tools.json \
      --registry /opt/cygnusx/runtime_images.yaml

USER root
RUN install -o 10001 -g 10001 -m 0644 /tmp/agent-tools.json /opt/agent-tools.json \
    && rm -f /tmp/agent-tools.json
USER "$MAMBA_USER"

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg SANDBOX_WORKSPACE=/workspace
WORKDIR /workspace
CMD ["micromamba", "run", "-n", "base", "sh", "-c", "rm -f /workspace/.agent.sock && exec uvicorn --app-dir /opt/cygnusx sandbox_agent:app --uds /workspace/.agent.sock"]
