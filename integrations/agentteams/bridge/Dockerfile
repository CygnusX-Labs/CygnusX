FROM python:3.11-slim

# 部署版本可观测：构建时经 --build-arg 注入，/healthz 的 build_sha/build_time 由此取值。
ARG BRIDGE_BUILD_SHA=unknown
ARG BRIDGE_BUILD_TIME=unknown
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV BRIDGE_BUILD_SHA=${BRIDGE_BUILD_SHA} \
    BRIDGE_BUILD_TIME=${BRIDGE_BUILD_TIME} \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    UV_INDEX_URL=${PIP_INDEX_URL} \
    UV_HTTP_TIMEOUT=120 \
    UV_HTTP_RETRIES=5 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Keep the Bridge image reproducible. The lock file prevents a mirror's partial
# metadata sync from selecting a newer dependency that is not downloadable yet.
RUN python -m pip install \
    --no-cache-dir \
    --index-url "${PIP_INDEX_URL}" \
    --timeout 60 \
    --retries 5 \
    uv==0.9.25 \
    && uv sync --frozen --no-dev --no-install-project \
        --index-url "${PIP_INDEX_URL}"
COPY cygnusx_agentteams_bridge ./cygnusx_agentteams_bridge
ENV PATH="/app/.venv/bin:${PATH}"
RUN useradd --create-home --uid 10001 bridge
RUN mkdir -p /var/lib/cygnusx-agentteams-bridge && chown bridge:bridge /var/lib/cygnusx-agentteams-bridge
USER bridge
EXPOSE 8080
