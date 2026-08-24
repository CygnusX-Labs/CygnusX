#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STUDIO_DIR="${ROOT_DIR}/deploy/studio"
RUNTIME_DIR="${ROOT_DIR}/deploy/runtime-images"
TAG="${CYGNUSX_IMAGE_TAG:-v0.0.2dev}"

docker build -t "cygnusx-analysis:core-${TAG}" \
  -f "${RUNTIME_DIR}/core.Dockerfile" "${STUDIO_DIR}"
docker build -t "cygnusx-analysis:plot-${TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  -f "${RUNTIME_DIR}/plot.Dockerfile" "${ROOT_DIR}"
docker build -t "cygnusx-analysis:scrna-${TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  -f "${RUNTIME_DIR}/scrna.Dockerfile" "${ROOT_DIR}"

printf '%s\n' "Built CygnusX independent analysis runtimes: core, plot, scrna (tag: ${TAG})"
