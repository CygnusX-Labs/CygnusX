# OmicHub 生信分析沙盒镜像
# 构建：docker build -t omichub/sandbox-base:latest -f deploy/sandbox/Dockerfile deploy/sandbox
#
# 设计（符合 1 人运维 / 单机部署原则）：
# - 基于 condaforge/mambaforge，通过 bioconda 预装 scanpy + R/Seurat 交互式分析栈
# - 工具链聚焦"交互式单细胞分析"（UMAP/聚类/差异），NGS 比对类重工具由 Snakemake 流程单独承载
# - sitecustomize.py 在 Python 启动时注入 sc/np/pd/show_echarts/show_image，配合后端池的 `python -` 执行协议
# - matplotlib 无头（Agg），图表通过 %%ECHARTS%% / %%IMAGE%% 标记行回传
FROM condaforge/mambaforge:24.3.0-0

LABEL maintainer="OmicHub"
LABEL description="Bioinformatics sandbox for OmicHub AI Copilot (scanpy + Seurat)"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    MAMBA_NO_BANNER=1

# 系统依赖（R 编译需要 build-essential；hdf5/lapack 为数值栈运行时依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libhdf5-dev \
        libpng-dev \
        libfreetype6-dev \
        liblapack-dev \
        libopenblas-dev \
        libxml2-dev \
        libxslt1-dev \
        libcurl4-openssl-dev \
        libssl-dev \
        procps \
        && rm -rf /var/lib/apt/lists/*

# conda 渠道：bioconda 优先于 conda-forge（生信包冲突最少）
RUN conda config --add channels bioconda \
    && conda config --add channels conda-forge \
    && conda config --set channel_priority strict

# 创建 omichub 环境（Python 3.11），预装核心生信 Python 栈
RUN mamba create -n omichub python=3.11 -y \
    && mamba install -n omichub -y \
        scanpy=1.10.2 \
        anndata=0.10.8 \
        muon=0.1.7 \
        leidenalg \
        python-igraph \
        harmonypy \
        scikit-learn=1.5.0 \
        statsmodels=0.14.0 \
        seaborn=0.13.2 \
        matplotlib=3.9.0 \
        matplotlib-venn \
        numpy=1.26.4 \
        pandas=2.2.2 \
        scipy=1.13.0 \
        plotly=5.22.0 \
        ipykernel=6.29 \
        openpyxl=3.1 \
        tqdm \
        requests \
    && mamba clean --all -y

# conda 缺少的较新单细胞工具走 pip
SHELL ["conda", "run", "-n", "omichub", "/bin/bash", "-c"]
RUN pip install --no-cache-dir \
        "squidpy>=1.4.0" \
        "scvi-tools>=1.1.0" \
        "celltypist>=1.6.0" \
        "decoupler>=1.6.0" \
        "kaleido>=0.2.1"

# R + Seurat + IRkernel（按文档启用，原 Dockerfile 此段被注释）
RUN mamba install -n omichub -c conda-forge -c bioconda -y \
        r-base=4.3 \
        r-irkernel \
        r-seurat \
        r-seuratobject \
        r-tidyverse \
        bioconductor-singlecellexperiment \
        bioconductor-scater \
        bioconductor-scran \
        bioconductor-complexheatmap \
    && mamba clean --all -y

# 注册 IRkernel（R 代码可在同一环境执行）
RUN conda run -n omichub R -e "IRkernel::installspec(user = FALSE)"

# sitecustomize.py：Python 启动时自动注入 sc/np/pd + 图表回传 helper
# 后端池通过 `docker exec -i <c> python -` 投递用户代码，sitecustomize 对所有启动方式生效
# 放入 site-packages 目录，Python 启动时自动加载（无需手动 PYTHONPATH）
COPY sitecustomize.py /opt/conda/envs/omichub/lib/python3.11/site-packages/sitecustomize.py

ENV PATH=/opt/conda/envs/omichub/bin:$PATH \
    CONDA_DEFAULT_ENV=omichub \
    MPLBACKEND=Agg

# 工作目录与数据挂载点（后端池挂载 /data/omichub -> /data）
WORKDIR /workspace
RUN mkdir -p /workspace/data /workspace/output

# 健康检查：验证核心生信栈可导入
HEALTHCHECK --interval=60s --timeout=15s --start-period=120s --retries=3 \
    CMD python -c "import scanpy, numpy, pandas, anndata; print('sandbox OK')" || exit 1

# 容器保持存活（由池通过 sleep infinity 接管，此处兜底）
CMD ["sleep", "infinity"]
