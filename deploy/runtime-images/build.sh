#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STUDIO_DIR="${ROOT_DIR}/deploy/studio"
RUNTIME_DIR="${ROOT_DIR}/deploy/runtime-images"
TAG="${CYGNUSX_IMAGE_TAG:-v0.0.2dev}"
# The scrna profile is versioned independently because v0.0.3dev is the tag
# registered in data/ai/runtime_images.yaml and data/ai/studio.yaml.
SCRNA_TAG="${CYGNUSX_SCRNA_IMAGE_TAG:-v0.0.3dev}"
RNASEQ_TAG="${CYGNUSX_RNASEQ_IMAGE_TAG:-v0.0.1dev}"
ATACSEQ_TAG="${CYGNUSX_ATACSEQ_IMAGE_TAG:-v0.0.1dev}"
QC_TAG="${CYGNUSX_QC_IMAGE_TAG:-v0.0.1dev}"
TOOLS_MANIFEST_DIGEST="${CYGNUSX_TOOLS_MANIFEST_DIGEST:-unknown}"
SANDBOX_UID="${SANDBOX_UID:-10001}"
SANDBOX_GID="${SANDBOX_GID:-10001}"
SANDBOX_GROUP="${SANDBOX_GROUP:-cygnusx-sandbox}"

COMMON_BUILD_ARGS=(
  --build-arg "SANDBOX_UID=${SANDBOX_UID}"
  --build-arg "SANDBOX_GID=${SANDBOX_GID}"
  --build-arg "SANDBOX_GROUP=${SANDBOX_GROUP}"
  --build-arg "TOOLS_MANIFEST_DIGEST=${TOOLS_MANIFEST_DIGEST}"
)
CHILD_BUILD_ARGS=(
  --build-arg "SANDBOX_GID=${SANDBOX_GID}"
  --build-arg "TOOLS_MANIFEST_DIGEST=${TOOLS_MANIFEST_DIGEST}"
)

docker build -t "cygnusx-analysis:core-${TAG}" \
  "${COMMON_BUILD_ARGS[@]}" \
  -f "${RUNTIME_DIR}/core.Dockerfile" "${ROOT_DIR}"
docker build -t "cygnusx-analysis:plot-${TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  "${CHILD_BUILD_ARGS[@]}" \
  -f "${RUNTIME_DIR}/plot.Dockerfile" "${ROOT_DIR}"
docker build -t "cygnusx-analysis:scrna-${SCRNA_TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  "${CHILD_BUILD_ARGS[@]}" \
  -f "${RUNTIME_DIR}/scrna.Dockerfile" "${ROOT_DIR}"
docker build -t "cygnusx-analysis:rnaseq-${RNASEQ_TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  "${CHILD_BUILD_ARGS[@]}" \
  -f "${RUNTIME_DIR}/rnaseq.Dockerfile" "${ROOT_DIR}"
docker build -t "cygnusx-analysis:atacseq-${ATACSEQ_TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  "${CHILD_BUILD_ARGS[@]}" \
  -f "${RUNTIME_DIR}/atacseq.Dockerfile" "${ROOT_DIR}"
docker build -t "cygnusx-analysis:qc-${QC_TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  "${CHILD_BUILD_ARGS[@]}" \
  -f "${RUNTIME_DIR}/qc.Dockerfile" "${ROOT_DIR}"

printf '%s\n' "Built CygnusX independent analysis runtimes: core/plot=${TAG}, scrna=${SCRNA_TAG}, rnaseq=${RNASEQ_TAG}, atacseq=${ATACSEQ_TAG}, qc=${QC_TAG}"
