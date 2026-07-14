#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
config_path=${OMICHUB_WORKER_CONFIG:-"${repository_root}/data/worker_config.yaml"}
rendered_env="${repository_root}/data/.worker-config.env"

cd "${repository_root}"
python3 scripts/render_worker_config.py --config "${config_path}" --output "${rendered_env}"

set -a
# shellcheck disable=SC1090
. "${rendered_env}"
set +a

exec docker compose -f deploy/docker/docker-compose.worker.yml "$@"
