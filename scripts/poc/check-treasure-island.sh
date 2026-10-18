#!/usr/bin/env bash
set -euo pipefail
cygnus_repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$cygnus_repo_root"
(
  cd pipelines/Treasure-Seeking_Mouse
  ./node_modules/.bin/tsc --noEmit
  ./node_modules/.bin/tsc --noEmit -p tsconfig.island.json
  ./node_modules/.bin/vite build --config vite.island.config.ts
  ./node_modules/.bin/vite build --config vite.island-reference.config.ts
)
(
  cd frontend
  ./node_modules/.bin/vue-tsc --noEmit -p poc/treasure-island/tsconfig.json
  ./node_modules/.bin/vitest run --config poc/treasure-island/vitest.config.ts
  ./node_modules/.bin/vite build --config poc/treasure-island/vite.config.ts
)
if [[ -n "${TREASURE_POC_PLAYWRIGHT_PATH:-}" ]]; then
  node scripts/poc/treasure-island-browser.mjs
else
  echo 'Browser evidence not run: set TREASURE_POC_PLAYWRIGHT_PATH to an installed playwright-core module.'
  echo 'G-P1A remains pending until real browser checks and human visual review pass.'
fi
