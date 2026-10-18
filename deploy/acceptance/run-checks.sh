#!/bin/sh
# Offline checks only. Deliberately does not start services or enable writes.
set -eu
cd "$(dirname "$0")/../.."
.venv/bin/ruff check deploy/acceptance
.venv/bin/ruff format --check deploy/acceptance
.venv/bin/python deploy/acceptance/checks.py
node --check deploy/acceptance/browser-preflight.cjs
.venv/bin/python deploy/acceptance/summarize.py
