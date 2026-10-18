/** Build only the original display island with its own locked dependencies. */
import { spawnSync } from 'node:child_process';
import { access, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
const frontend = fileURLToPath(new URL('..', import.meta.url));
const source = resolve(frontend, '../pipelines/Treasure-Seeking_Mouse');
const vite = resolve(source, 'node_modules/vite/bin/vite.js');
try { await access(vite); }
catch { throw new Error('Missing Treasure Mouse build dependencies. Install the child repository dependencies with its frozen lockfile before building the frontend.'); }
const output = resolve(frontend, 'public/treasure-island');
const result = spawnSync(process.execPath, [vite, 'build', '--config', 'vite.island.config.ts', '--outDir', output], {
  cwd: source, stdio: 'inherit',
});
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status || 1);
// The diagnostic inventory contains local filesystem paths; never serve it publicly.
await rm(resolve(output, 'module-inventory.json'), { force: true });
