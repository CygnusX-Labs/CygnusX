"""Start the latest source beside the owned comparison runtime, sharing isolated services."""
import json
import socket
import os
import signal
import sys
import subprocess
import time
from pathlib import Path

import httpx

out=Path(__file__).resolve().parent
handle=json.loads((out/'runtime-handle.json').read_text());private=Path(handle['private_root'])
wt=Path(handle['worktree']);env=json.loads((private/'environment.json').read_text())
target=out/'final-api-handle.json'
if target.exists() and '--restart' in sys.argv:
 old=json.loads(target.read_text());pid=old['pid']
 assert Path(f'/proc/{pid}/cwd').resolve()==wt
 command=Path(f'/proc/{pid}/cmdline').read_bytes()
 assert b'uvicorn' in command and b'18026' in command
 os.kill(pid,signal.SIGTERM)
 for _ in range(80):
  if not Path(f'/proc/{pid}').exists() or Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z':break
  time.sleep(.1)
 target.unlink()
if target.exists():
 prior=json.loads(target.read_text())
 assert Path(f"/proc/{prior['pid']}/cwd").resolve()==wt
 process_id=prior['pid']
else:
 with socket.socket() as probe:assert probe.connect_ex(('127.0.0.1',18026))!=0
 log=(private/'api-final.log').open('w')
 process=subprocess.Popen([str(wt/'.venv/bin/uvicorn'),'cygnusx.main:app','--lifespan','off','--host','127.0.0.1','--port','18026'],cwd=wt,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 process_id=process.pid
 target.write_text(json.dumps({'pid':process_id,'port':18026,'worktree':str(wt)},indent=2))
for _ in range(120):
 assert Path(f'/proc/{process_id}').exists(),'Owned final API exited'
 try:httpx.get('http://127.0.0.1:18026/health',timeout=1);break
 except httpx.ConnectError:time.sleep(.2)
else:raise RuntimeError('Final API readiness timeout')
print('Final isolated API ready:',process_id)
