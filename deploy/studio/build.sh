#!/usr/bin/env bash
# 构建 OmicStudio 沙盒镜像：base -> bio（full 镜像待后续阶段）
# 用法：deploy/studio/build.sh [--push]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="${CYGNUSX_IMAGE_TAG:-v0.0.2dev}"

echo "==> 构建 cygnusx-sandbox-base:${TAG}"
docker build -t "cygnusx-sandbox-base:${TAG}" \
  -f "${SCRIPT_DIR}/base.Dockerfile" "${SCRIPT_DIR}"

echo "==> 构建 cygnusx-sandbox-bio:${TAG}"
docker build -t "cygnusx-sandbox-bio:${TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  -f "${SCRIPT_DIR}/bio.Dockerfile" "${SCRIPT_DIR}"

echo "==> 构建 cygnusx-sandbox-browser-office:${TAG}"
docker build -t "cygnusx-sandbox-browser-office:${TAG}" \
  --build-arg "CYGNUSX_IMAGE_TAG=${TAG}" \
  -f "${SCRIPT_DIR}/browser-office.Dockerfile" "${SCRIPT_DIR}"

echo "==> 完成：cygnusx-sandbox-base:${TAG} / cygnusx-sandbox-bio:${TAG} / cygnusx-sandbox-browser-office:${TAG}"
