#!/usr/bin/env bash
# 构建 OmicStudio 沙盒镜像：base -> bio（full 镜像待后续阶段）
# 用法：deploy/studio/build.sh [--push]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="${OMICHUB_IMAGE_TAG:-v0.0.2dev}"

echo "==> 构建 omichub-sandbox-base:${TAG}"
docker build -t "omichub-sandbox-base:${TAG}" \
  -f "${SCRIPT_DIR}/base.Dockerfile" "${SCRIPT_DIR}"

echo "==> 构建 omichub-sandbox-bio:${TAG}"
docker build -t "omichub-sandbox-bio:${TAG}" \
  --build-arg "OMICHUB_IMAGE_TAG=${TAG}" \
  -f "${SCRIPT_DIR}/bio.Dockerfile" "${SCRIPT_DIR}"

echo "==> 构建 omichub-sandbox-browser-office:${TAG}"
docker build -t "omichub-sandbox-browser-office:${TAG}" \
  --build-arg "OMICHUB_IMAGE_TAG=${TAG}" \
  -f "${SCRIPT_DIR}/browser-office.Dockerfile" "${SCRIPT_DIR}"

echo "==> 完成：omichub-sandbox-base:${TAG} / omichub-sandbox-bio:${TAG} / omichub-sandbox-browser-office:${TAG}"
