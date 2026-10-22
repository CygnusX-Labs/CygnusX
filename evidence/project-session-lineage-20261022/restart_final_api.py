"""Restart only the owned isolated API after source changes, retaining test gates."""
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import httpx

out = Path(__file__).resolve().parent
handle = json.loads((out / 'runtime-handle.json').read_text())
private = Path(handle['private_root'])
env = json.loads((private / 'environment.json').read_text())
wt = Path(handle['worktree'])
old = json.loads((out / 'final-api-handle.json').read_text())
pid = old['pid']
assert Path(f'/proc/{pid}/cwd').resolve() == wt
os.kill(pid, signal.SIGTERM)
for _ in range(50):
    if not Path(f'/proc/{pid}').exists() or Path(f'/proc/{pid}/stat').read_text().split()[2] == 'Z':
        break
    time.sleep(.1)
log = (private / 'api-final-current.log').open('w')
process = subprocess.Popen([str(wt / '.venv/bin/uvicorn'), 'cygnusx.main:app', '--lifespan', 'off',
    '--host', '127.0.0.1', '--port', '18014'], cwd=wt, env=env, stdout=log,
    stderr=subprocess.STDOUT, start_new_session=True)
old['previous_pid'], old['pid'] = pid, process.pid
(out / 'final-api-handle.json').write_text(json.dumps(old, indent=2))
for _ in range(90):
    assert process.poll() is None, 'Isolated API exited'
    try:
        httpx.get('http://127.0.0.1:18014/health', timeout=1)
        break
    except httpx.ConnectError:
        time.sleep(.2)
else:
    raise RuntimeError('Isolated API not ready')
print('Final isolated API ready:', process.pid)
