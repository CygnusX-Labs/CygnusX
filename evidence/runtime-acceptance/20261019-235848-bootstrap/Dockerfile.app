FROM 127.0.0.1:5000/ri095-app-pdf@sha256:aa87d0329fb60f2a19ceb422f89706038b722339a6da13bb9a761e409542f7e4
USER 10001:10001
WORKDIR /app
COPY --chown=10001:10001 src/ /app/src/
COPY --chown=10001:10001 alembic/ /app/alembic/
COPY --chown=10001:10001 data/ /app/data/
COPY --chown=10001:10001 flows/ /app/flows/
COPY --chown=10001:10001 tool_configs/ /app/tool_configs/
COPY --chown=10001:10001 scripts/ /app/scripts/
COPY --chown=10001:10001 pyproject.toml uv.lock alembic.ini /app/
COPY --chown=10001:10001 private-storage/ /acceptance-storage/
LABEL org.opencontainers.image.revision="ac2cdca399d0fdb4b5e777a234b55e24ffbbeb79" cygnusx.dirty-source-sha256="ebef48335434468665135aa37424fccdc3f7c5b0f83882879a8eb6aad0e27bc6"
