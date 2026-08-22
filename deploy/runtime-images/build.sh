#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STUDIO_DIR="${ROOT_DIR}/deploy/studio"
RUNTIME_DIR="${ROOT_DIR}/deploy/runtime-images"
TAG="${OMICHUB_IMAGE_TAG:-v0.0.2dev}"

docker build -t "omichub-analysis:core-${TAG}" \
  -f "${RUNTIME_DIR}/core.Dockerfile" "${STUDIO_DIR}"
docker build -t "omichub-analysis:plot-${TAG}" \
  --build-arg "OMICHUB_IMAGE_TAG=${TAG}" \
  -f "${RUNTIME_DIR}/plot.Dockerfile" "${ROOT_DIR}"
docker build -t "omichub-analysis:scrna-${TAG}" \
  --build-arg "OMICHUB_IMAGE_TAG=${TAG}" \
  -f "${RUNTIME_DIR}/scrna.Dockerfile" "${ROOT_DIR}"

printf '%s\n' "Built OmicHub independent analysis runtimes: core, plot, scrna (tag: ${TAG})"
