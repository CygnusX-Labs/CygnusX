# Reuse approved existing Worker/application base; no package installation.
# Build context is repository root. Base must be reviewed and digest pinned.
ARG ACCEPTANCE_BASE_IMAGE
FROM ${ACCEPTANCE_BASE_IMAGE}
WORKDIR /app
COPY --chown=10001:10001 data/ /app/data/
# Docker initializes an empty named volume from this UID-owned image directory.
COPY --chown=10001:10001 deploy/acceptance/private-storage/ /acceptance-storage/
USER 10001:10001
