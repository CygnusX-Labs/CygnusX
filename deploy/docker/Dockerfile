# ============================================
# OmicHub 后端 Dockerfile
# 多阶段构建：uv 安装依赖 + slim 运行
# ============================================

# ----- 阶段 1: 构建依赖 -----
FROM python:3.11-slim AS builder

# Git is required to install the Snakemake logger plugin from the JZ_Tools
# repository subdirectory during image build.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 先复制依赖文件（利用 Docker 层缓存）
COPY pyproject.toml uv.lock* README.md ./

# 安装依赖到虚拟环境
RUN uv sync --frozen --no-dev --no-install-project

# 复制源代码
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
# 工具箱配置（tools_setting.yaml + 各工具子目录 YAML）；prod 不挂源码，须打进镜像
COPY tool_configs/ ./tool_configs/

# 安装项目本身
RUN uv sync --frozen --no-dev

# Snakemake logger plugin used by the workflow monitor.
# The plugin must be installed in the same venv that provides the snakemake CLI.
ARG SNAKEMAKE_LOGGER_PLUGIN_REF=main
RUN /app/.venv/bin/python -m pip install --no-cache-dir "snakemake-logger-plugin-rich-loguru @ git+https://github.com/xsx123123/JZ_Tools.git@${SNAKEMAKE_LOGGER_PLUGIN_REF}#subdirectory=src/logger_plugin" && /app/.venv/bin/python -c "import re; from importlib.metadata import version; v = version('snakemake-logger-plugin-rich-loguru'); m = re.match(r'^(\d+)\.(\d+)\.(\d+)', v); assert m and tuple(map(int, m.groups())) >= (0, 2, 1), f'snakemake-logger-plugin-rich-loguru >=0.2.1 required, got {v}'; import snakemake_logger_plugin_rich_loguru; print(f'snakemake-logger-plugin-rich-loguru {v} installed')"

# ----- 阶段 2: 运行 -----
FROM python:3.11-slim AS runtime

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
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
