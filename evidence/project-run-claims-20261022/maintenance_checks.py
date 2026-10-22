"""Final migration, schema and full-corpus index checks inside dedicated services."""
import asyncio
import json
import os
import statistics
import subprocess
import time
from pathlib import Path

import httpx

OUT=Path(__file__).resolve().parent
HANDLE=json.loads((OUT/'runtime-handle.json').read_text());PRIVATE=Path(HANDLE['private_root'])
ENV=json.loads((PRIVATE/'environment.json').read_text());os.environ.update(ENV)
CTX=json.loads((PRIVATE/'context.json').read_text());FIX=json.loads((PRIVATE/'fixtures.json').read_text())
WT=Path(HANDLE['worktree'])


async def empty_database():
 from sqlalchemy import text
 from sqlalchemy.ext.asyncio import create_async_engine
 name='claims_migration_empty_'+PRIVATE.name.rsplit('-',1)[-1].replace('_','')
 engine=create_async_engine(ENV['DATABASE_URL'],isolation_level='AUTOCOMMIT')
 assert engine.url.host=='127.0.0.1' and engine.url.port==55446
 async with engine.connect() as db:
  if not await db.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'),{'name':name}):
   await db.execute(text('CREATE DATABASE "'+name+'"'))
 await engine.dispose();return name


def command(args,name,env):
 with (OUT/name).open('w') as log:
  subprocess.run([str(WT/'.venv/bin/python'),*args],cwd=WT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)


name=asyncio.run(empty_database());empty_env={**ENV,'POSTGRES_DB':name,'DATABASE_URL':ENV['DATABASE_URL'].rsplit('/',1)[0]+'/'+name}
for args,log in [(['-m','alembic','upgrade','head'],'migration-empty-all-up.log'),(['-m','alembic','downgrade','project_lifecycle01'],'migration-empty-all-down.log'),(['-m','alembic','upgrade','head'],'migration-empty-all-reup.log')]:
 command(args,log,empty_env)
command(['scripts/backfill_project_run_index.py','--expected-database','run_claim_test_20261022','--confirm-isolated','--output',str(OUT/'backfill-project-results-final.json')],'backfill-final.log',ENV)
with (OUT/'schema-drift.log').open('w') as log:
 drift=subprocess.run([str(WT/'.venv/bin/python'),'scripts/check_schema_drift.py'],cwd=WT,env=ENV,stdout=log,stderr=subprocess.STDOUT)
(OUT/'schema-check-status.json').write_text(json.dumps({'exit_code':drift.returncode,'empty_migration_database':name,'production_database_touched':False},indent=2))
with httpx.Client(base_url='http://127.0.0.1:18026/api/v1',timeout=60) as api:
 login=api.post('/auth/login',data={'username':CTX['owner_username'],'password':CTX['owner_password']});login.raise_for_status()
 header={'Authorization':'Bearer '+login.json()['access_token']};api.headers.update(header)
 with httpx.Client(base_url=CTX['baseline_url'],headers=header,timeout=60) as baseline:
  result={};project=FIX['benchmark_project_id'];path=f'/projects/{project}/overview'
  populations={}
  for label,client in [('recursive_baseline',baseline),('indexed_final_source',api)]:
   for _ in range(3):response=client.get(path,params={'run_limit':200});response.raise_for_status()
   samples=[]
   for _ in range(25):
    started=time.perf_counter();response=client.get(path,params={'run_limit':200});elapsed=(time.perf_counter()-started)*1000
    response.raise_for_status();payload=response.json();assert len(payload['runs'])==100
    samples.append(elapsed)
   populations[label]={r['name']:(r['file_count'],r['total_size_bytes']) for r in payload['runs']}
   result[label]={'samples_ms':samples,'median_ms':statistics.median(samples),'p95_ms':sorted(samples)[23],'run_count':len(payload['runs']),
    'file_count':sum(r['file_count'] for r in payload['runs']),'total_bytes':sum(r['total_size_bytes'] for r in payload['runs'])}
  assert populations['recursive_baseline']==populations['indexed_final_source']
  (OUT/'overview-latency-final.json').write_text(json.dumps({'project_id':project,'method':'Same project, same PG/storage and 100 complete rows; 3 warmups + 25 HTTP requests per endpoint; file-count/byte totals also compared',
    'populations_and_totals_equal':True,**result},indent=2)+'\n')
print('Both migrations upgraded/downgraded/re-upgraded in empty dedicated DB; final full-source metadata totals match recursive baseline. Schema exit:',drift.returncode)
