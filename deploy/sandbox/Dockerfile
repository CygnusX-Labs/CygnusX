# OmicHub 沙盒基础镜像（轻量版）
# 构建：docker build -t omichub/sandbox-base:latest -f deploy/sandbox/Dockerfile .
# 包含 Python 生信栈（scanpy/anndata/plotly）；R+Seurat 按需启用（注释段）
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        libopenblas-base \
        liblapacke \
        libxml2-dev \
        && rm -rf /var/lib/apt/lists/*

# Python 生信栈
RUN pip install --no-cache-dir \
        scanpy==1.10.2 \
        anndata==0.10.8 \
        pandas==2.2.2 \
        numpy==1.26.4 \
        matplotlib==3.9.0 \
        seaborn==0.13.2 \
        plotly==5.22.0 \
        scikit-learn==1.5.0 \
        umap-learn==0.5.5

# 工作目录
WORKDIR /workspace
RUN mkdir -p /workspace/data /workspace/output

# 容器保持存活（由池通过 sleep infinity 接管，此处兜底）
CMD ["sleep", "infinity"]

# ----- 可选：R + Seurat（按需取消注释）-----
# FROM r-base:4.4.0 AS r-deps
# RUN apt-get update && apt-get install -y libxml2-dev libcurl4-openssl-dev libssl-dev
# RUN R -e "install.packages('Seurat')"
