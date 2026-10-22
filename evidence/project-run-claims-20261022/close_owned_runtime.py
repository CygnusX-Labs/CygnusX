"""Stop only the processes/containers recorded for this isolated evidence run."""
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

out=Path(__file__).resolve().parent
handle=json.loads((out/'runtime-handle.json').read_text());wt=Path(handle['worktree']);private=Path(handle['private_root'])
terminated=[]
final=json.loads((out/'final-api-handle.json').read_text())
for folder in Path('/proc').iterdir():
 if not folder.name.isdecimal():continue
 try:
  cmd=(folder/'cmdline').read_bytes();cwd=(folder/'cwd').resolve();pid=int(folder.name)
  is_final=pid==final['pid'] and b'uvicorn' in cmd and b'18026' in cmd
  is_preview=str(out/'preview.py').encode() in cmd.split(b'\0')
  if (is_final or is_preview) and cwd==wt:
   os.kill(pid,signal.SIGTERM);terminated.append(pid)
 except (FileNotFoundError,ProcessLookupError,PermissionError):pass
(private/'stop').write_text('All source/runtime evidence captured. Stop owned services only.\n')
ports=[18022,18023,18024,18026,55446,16393]
for _ in range(250):
 open_ports=[]
 for port in ports:
  with socket.socket() as probe:
   if probe.connect_ex(('127.0.0.1',port))==0:open_ports.append(port)
 if not open_ports:break
 time.sleep(.1)
else:raise RuntimeError(f'Owned ports still open: {open_ports}')
states={name:subprocess.check_output(['docker','inspect',name,'--format','{{.State.Status}}'],text=True).strip() for name in (handle['postgres'],handle['redis'])}
assert all(value=='exited' for value in states.values()),states
closure={'dedicated_services_stopped':True,'verified_closed_ports':ports,'terminated_final_api_and_preview_pids':terminated,'retained_container_states':states,'containers_and_data_retained':True,'private_root':str(private),'private_credentials_mode':oct((private/'environment.json').stat().st_mode&0o777),'production_modified':False,'committed':False,'pushed':False,'deployed':False}
(out/'closure.json').write_text(json.dumps(closure,indent=2)+'\n')
print('Owned services stopped; all six ports closed; containers/data retained.')
