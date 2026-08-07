#!/bin/sh
set -eu

case "${AGENTTEAMS_WORKER_MODE:-production}" in
  production) exec python /app/production_runner.py "$@" ;;
  acceptance) exec python /app/worker_runner.py "$@" ;;
  *) echo "Unsupported AGENTTEAMS_WORKER_MODE: ${AGENTTEAMS_WORKER_MODE}" >&2; exit 2 ;;
esac
