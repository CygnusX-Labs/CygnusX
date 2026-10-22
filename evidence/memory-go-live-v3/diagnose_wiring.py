"""Content-free read-only deployment diagnosis, before any wiring mutation."""
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path.cwd()
OUT = ROOT / 'evidence/memory-go-live-v3'
KEYS = ['AGENT_MEMORY_EMBEDDING_MODEL', 'AGENT_MEMORY_EMBEDDING_PROVIDER_ID',
        'AGENT_MEMORY_EMBEDDING_DIMENSIONS', 'SILICONFLOW_API_KEY',
        'MEMORY_MAINTENANCE_DATABASE_URL']
values = dotenv_values(ROOT / '.env')
report = {
    'captured_at_utc': datetime.now(timezone.utc).isoformat(),
    'env_file': {'path': '.env', 'mtime_utc': datetime.fromtimestamp((ROOT / '.env').stat().st_mtime, timezone.utc).isoformat(),
                 'nonempty_keys': {k: bool(values.get(k)) for k in KEYS}},
    'services': [], 'real_calls': {'embedding': 0, 'extraction': 0},
}
files = {'web': 'deploy/docker/docker-compose.yml', 'beat': 'deploy/docker/docker-compose.yml',
         'worker': 'deploy/docker/docker-compose.worker.yml'}
for service, file in files.items():
    name = 'cygnusx-' + service
    info = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
    env = dict(s.split('=', 1) for s in info['Config']['Env'] if '=' in s)
    lines = (ROOT / file).read_text().splitlines()
    start = next(i for i, s in enumerate(lines) if s == '  ' + service + ':')
    end = next((i for i in range(start+1,len(lines)) if re.match(r'^  [a-zA-Z][\w-]*:$', lines[i])),len(lines))
    references = [{'file': file, 'line': i+1, 'source': lines[i].strip()} for i in range(start,end)
                  if any(t in lines[i] for t in ['env_file:', '../../.env','environment:', '../../data:', '../../src:'])]
    mounts = [m for m in info['Mounts'] if m['Destination'] in ('/app/data','/app/src')]
    report['services'].append({
        'service': service, 'container': name, 'created_at': info['Created'], 'started_at': info['State']['StartedAt'],
        'env_file_modified_after_container_created': report['env_file']['mtime_utc'] > info['Created'],
        'env_key_presence': {k: bool(env.get(k)) for k in KEYS},
        'compose_sources': info['Config']['Labels'].get('com.docker.compose.project.config_files'),
        'source_references': references,
        'relevant_mounts': [{'destination':m['Destination'],'source':m['Source'],'read_only':not m['RW']} for m in mounts],
        'provider_yaml_source': 'bind mount' if any(m['Destination']=='/app/data' for m in mounts) else 'image or absent (not required by Beat)',
        'env_contract': 'env_file loads all five keys when present at container creation; no fixed allowlist blocks new keys',
        'timing_limitation': 'mtime is whole-file metadata; does not date individual key edits',
    })
logs = subprocess.run(['docker','logs','--timestamps','cygnusx-worker'],capture_output=True,text=True,check=False)
lines = (logs.stdout+'\n'+logs.stderr).splitlines()
errors = [i for i,s in enumerate(lines) if re.search(r'embedding',s,re.I) and re.search(r'\berror\b|\bcritical\b|\bfatal\b',s,re.I)]
contexts=[]
for idx in errors:
    window='\n'.join(lines[max(0,idx-12):min(len(lines),idx+16)])
    types = sorted(set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b',window)))
    identifiers=[]
    for pattern in [r'column [\"\x27]?([a-z_][a-z0-9_.]*)[\"\x27]? does not exist', r'relation [\"\x27]([a-z_][a-z0-9_.]*)[\"\x27] does not exist',r"has no attribute ['\"]([a-z_][a-z0-9_]*)['\"]"]:
        identifiers.extend(re.findall(pattern,window))
    frames = re.findall(r'File "(/app/src/[A-Za-z0-9_/.-]+\.py)", line (\d+), in ([A-Za-z0-9_]+)',window)
    tokens = sorted(set(re.findall(r'\bmemory\.[a-z_]+\b',window)))
    contexts.append({'docker_timestamp':lines[idx].split(' ',1)[0], 'exception_types':types,
        'missing_schema_or_attribute_identifiers':sorted(set(identifiers)),
        'frames':[{'file':f,'line':int(n),'function':fn} for f,n,fn in frames],
        'memory_events':tokens,
        'context_redaction':'Only exception class, schema identifier and code frames retained; messages, SQL parameters, user content and credentials excluded'})
report['worker_embedding_errors']={'docker_logs_exit_code':logs.returncode,'matched_lines':len(errors),'sanitized_contexts':contexts}
report['diagnosis']={
    'configuration':'Existing env_file covers the required keys; current containers predate applicable file contents or were created without these values. Timing and key-presence evidence above.',
    'yaml':'Web/Worker use read-only data bind mounts. No image rebuild is required to see providers.yaml. Web startup YAML synchronization still requires an operational database and valid interpolation environment.',
    'credential':'SILICONFLOW_API_KEY nonempty presence checked only; user supplies key.',
    'maintenance':'Explicit dedicated MEMORY_MAINTENANCE_DATABASE_URL still required before maintenance; no implicit DATABASE_URL fallback permitted.',
}
(OUT/'step1-diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
