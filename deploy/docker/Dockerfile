# ============================================
# OmicHub 后端 Dockerfile
# 多阶段构建：uv 安装依赖 + slim 运行
# ============================================

# ----- 阶段 1: 构建依赖 -----
FROM python:3.11-slim AS builder

# 构建期切换清华 apt 源，加速 apt-get（兼容 debian.sources 与旧版 sources.list）
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's@//deb.debian.org@//mirrors.tuna.tsinghua.edu.cn@g; s@//security.debian.org@//mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list.d/debian.sources; \
    else \
        sed -i 's@//deb.debian.org@//mirrors.tuna.tsinghua.edu.cn@g; s@//security.debian.org@//mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list; \
    fi

# Git is required to install the Snakemake logger plugin from the JZ_Tools
# repository subdirectory during image build.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && rm -rf /var/lib/apt/lists/*

# 安装 uv（从 PyPI 而非 GHCR——GHCR 在国内常被墙，与 Dockerfile.worker 同路线）
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    -i https://pypi.tuna.tsinghua.edu.cn/simple "uv==0.6.14"

# uv 不读 /etc/pip.conf，必须显式指定 index（tuna 主源 + 阿里云兜底）
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    UV_EXTRA_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

# 先复制依赖文件（利用 Docker 层缓存）
COPY pyproject.toml uv.lock* README.md ./

# 安装依赖到虚拟环境
RUN uv sync --frozen --no-dev --extra workflow --no-install-project

# 复制源代码
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
# 工具箱配置（tools_setting.yaml + 各工具子目录 YAML）；prod 不挂源码，须打进镜像
COPY tool_configs/ ./tool_configs/

# 安装项目本身
RUN uv sync --frozen --no-dev --extra workflow

# Snakemake logger plugin used by the workflow monitor.
RUN uv pip install --python /app/.venv/bin/python --no-cache "snakemake-logger-plugin-rich-loguru>=0.3.0"

# ----- 阶段 2: 运行 -----
FROM python:3.11-slim AS runtime

# 构建期切换清华 apt 源，加速 apt-get（兼容 debian.sources 与旧版 sources.list）
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's@//deb.debian.org@//mirrors.tuna.tsinghua.edu.cn@g; s@//security.debian.org@//mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list.d/debian.sources; \
    else \
        sed -i 's@//deb.debian.org@//mirrors.tuna.tsinghua.edu.cn@g; s@//security.debian.org@//mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list; \
    fi

# 安装运行时系统依赖
# nodejs/npm：stdio 传输的 node/npx 型 MCP server 由 web 进程内 spawn，
# validate_stdio_command 走 shutil.which，容器内必须有 node 运行时（python:3.11-slim 默认不带）。
# bookworm apt 源（已切清华镜像）提供 nodejs 18 / npm 9，满足绝大多数 MCP server。
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 从 builder 复制虚拟环境和源代码
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/tool_configs /app/tool_configs

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV APP_ENV=production

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# 默认启动命令（可被 docker-compose 覆盖）
CMD ["uvicorn", "omichub.main:app", "--host", "0.0.0.0", "--port", "8000"]
