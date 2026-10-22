"""Dedicated claim/index runtime. No production .env, database, Worker or compute."""
import asyncio
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
import yaml

OUT=Path(__file__).resolve().parent
WT=Path(json.loads((OUT/'worktree.json').read_text())['implementation_worktree'])
PRIVATE=Path(tempfile.mkdtemp(prefix='cygnusx-run-claims-runtime-'))
os.chmod(PRIVATE,0o700)
suffix=PRIVATE.name.rsplit('-',1)[-1]
PG,CACHE='cygnusx-claims-pg-'+suffix,'cygnusx-claims-redis-'+suffix
password='Q7'+secrets.token_hex(24)
env={key:os.environ[key] for key in ['PATH','HOME','LANG','TZ'] if key in os.environ}
env.update({'PYTHONPATH':str(WT/'src'),'SERVICE_NAME':'web','APP_DEBUG':'false',
 'POSTGRES_HOST':'127.0.0.1','POSTGRES_PORT':'55446','POSTGRES_USER':'claims_test','POSTGRES_PASSWORD':password,'POSTGRES_DB':'run_claim_test_20261022',
 'DATABASE_URL':f'postgresql+asyncpg://claims_test:{password}@127.0.0.1:55446/run_claim_test_20261022',
 'REDIS_HOST':'127.0.0.1','REDIS_PORT':'16393','REDIS_PASSWORD':'',
 'JWT_SECRET_KEY':secrets.token_hex(32),'APP_SECRET_KEY':secrets.token_hex(32),
 'SITE_CONTENT_YAML':str(PRIVATE/'config/CygnusX.yaml'),'STORAGE_PATH':str(PRIVATE/'storage'),
 'CYGNUSX_LOG_DIR':str(PRIVATE/'logs'),'RATE_LIMIT_ENABLED':'false'})
flags=['RESEARCH_PLAN_ENABLED','RESEARCH_DELIVERY_READ_ENABLED','TOOL_GATEWAY_READ_ENABLED','DATASET_DISCOVERY_READONLY',
 'AGENT_ANALYSIS_WRITE_ENABLED','AGENT_DOWNLOAD_WRITE_ENABLED','ANALYSIS_SUBMIT_FROM_DATASET','DATASET_IMPORT_WRITE',
 'RESEARCH_DELIVERY_WRITE_ENABLED','PROJECT_EXPORT_ENABLED','PROJECT_REPORT_WRITE_ENABLED','PROJECT_REPORT_PDF_ENABLED',
 'COUNTS_DEG_FLOW_ENABLED','TREASURE_NATIVE_UI_ENABLED','TREASURE_AGENT_WRITE_TOOLS_ENABLED','AGENT_TASK_CANCEL_ENABLED']
env.update({key:'false' for key in flags})
env['RESEARCH_DELIVERY_READ_ENABLED']=env['DATASET_DISCOVERY_READONLY']='true'
(PRIVATE/'config').mkdir()
config=yaml.safe_load((WT/'data/CygnusX.yaml').read_text());config['storage']['data_root']=str(PRIVATE/'storage')
(PRIVATE/'config/CygnusX.yaml').write_text(yaml.safe_dump(config,allow_unicode=True))
(PRIVATE/'config/ai').symlink_to(WT/'data/ai',target_is_directory=True)
(PRIVATE/'environment.json').write_text(json.dumps(env));os.chmod(PRIVATE/'environment.json',0o600)
pg_env=PRIVATE/'postgres.env';pg_env.write_text(f'POSTGRES_USER=claims_test\nPOSTGRES_DB=run_claim_test_20261022\nPOSTGRES_PASSWORD={password}\n');os.chmod(pg_env,0o600)


def save(name,data):
 (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n')


def run(cmd,**kwargs):
 return subprocess.run(cmd,check=True,text=True,**kwargs)


def image(tag):
 return subprocess.check_output(['docker','image','inspect',tag,'--format','{{.Id}}'],text=True).strip()


async def seed():
 from sqlalchemy import text
 from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine
 from cygnusx.infrastructure.database.models.user import UserModel
 from cygnusx.infrastructure.database.models.project import ProjectModel
 from cygnusx.core.security import hash_password
 engine=create_async_engine(env['DATABASE_URL']);ids={}
 async with AsyncSession(engine) as db:
  for username in ['claims_owner','claims_other']:
   uid=uuid4();ids[username]=str(uid)
   db.add(UserModel(id=uid,username=username,email=username+'@invalid.test',hashed_password=hash_password(password),role='user',status='active',token_version=0,disabled_modules=[]))
  await db.flush()
  owner_project=ProjectModel(id=uuid4(),user_id=ids['claims_owner'],name='Claim main',slug='claim-main',status='active')
  other_project=ProjectModel(id=uuid4(),user_id=ids['claims_other'],name='Other only',slug='other-only',status='active')
  db.add(owner_project);db.add(other_project);await db.flush()
  ids.update({'project_id':str(owner_project.id),'other_project_id':str(other_project.id)})
  for label,owner,slug in [('matched',ids['claims_owner'],'claim-main'),('unmatched',ids['claims_owner'],'unknown-slug'),('wrong-owner',ids['claims_owner'],'other-only')]:
   rid=uuid4();ids[label]=str(rid)
   await db.execute(text("""INSERT INTO platform_runs (id,user_id,project_slug,flow_id,release_id,request_key,plan_json,plan_digest,status)
     VALUES (:id,:owner,:slug,'rna_seq','2.3.0',:key,'{}',:digest,'plan_pending')"""),{'id':rid,'owner':owner,'slug':slug,'key':'migration-'+label,'digest':'0'*64})
  await db.commit()
 await engine.dispose();return ids


async def migration_rows():
 from sqlalchemy import text
 from sqlalchemy.ext.asyncio import create_async_engine
 engine=create_async_engine(env['DATABASE_URL'])
 async with engine.connect() as db:
  rows=[dict(r) for r in (await db.execute(text('SELECT id,user_id,project_slug,project_id,attempt_number FROM platform_runs ORDER BY request_key'))).mappings()]
 await engine.dispose();return rows


def migrate(target,filename):
 with (OUT/filename).open('w') as log:run([str(WT/'.venv/bin/alembic'),'upgrade' if target!='downgrade' else 'downgrade',target if target!='downgrade' else 'project_lifecycle01'],env=env,cwd=WT,stdout=log,stderr=subprocess.STDOUT)


def start_api(source,port,name):
 actual={**env,'PYTHONPATH':str(source/'src')}
 log=(PRIVATE/(name+'.log')).open('w')
 process=subprocess.Popen([str(WT/'.venv/bin/uvicorn'),'cygnusx.main:app','--lifespan','off','--host','127.0.0.1','--port',str(port)],cwd=source,env=actual,stdout=log,stderr=subprocess.STDOUT)
 for _ in range(120):
  if process.poll() is not None:raise RuntimeError('Isolated API exited; private log '+name)
  try:httpx.get(f'http://127.0.0.1:{port}/health',timeout=1);break
  except httpx.ConnectError:time.sleep(.2)
 else:raise RuntimeError('API readiness timeout')
 return process


api=baseline=None
try:
 for port in [55446,16393,18022,18024]:
  with socket.socket() as s:
   assert s.connect_ex(('127.0.0.1',port))!=0, f'Reserved port already occupied: {port}'
 run(['docker','run','-d','--name',PG,'--label','cygnusx.task=run-claims','--env-file',str(pg_env),'-p','127.0.0.1:55446:5432',image('pgvector/pgvector:pg14')],capture_output=True)
 run(['docker','run','-d','--name',CACHE,'--label','cygnusx.task=run-claims','-p','127.0.0.1:16393:6379',image('redis:7-alpine')],capture_output=True)
 for _ in range(90):
  if subprocess.run(['docker','exec',PG,'pg_isready','-h','127.0.0.1','-U','claims_test'],capture_output=True).returncode==0:break
  time.sleep(.2)
 migrate('project_lifecycle01','migration-baseline.log')
 os.environ.update(env)
 ids=asyncio.run(seed());save('migration-fixture-identities.json',ids)
 migrate('head','migration-upgrade.log')
 rows=asyncio.run(migration_rows());save('migration-backfill.json',rows)
 assert next(r for r in rows if str(r['id'])==ids['matched'])['project_id'] is not None
 assert all(r['project_id'] is None for r in rows if str(r['id']) in {ids['unmatched'],ids['wrong-owner']})
 assert all(r['attempt_number']==0 for r in rows)
 migrate('downgrade','migration-downgrade-empty.log');migrate('head','migration-reupgrade.log')
 api=start_api(WT,18022,'api-current')
 baseline=start_api(Path(json.loads((OUT/'worktree.json').read_text())['accepted_base_worktree']),18024,'api-scan-baseline')
 save('runtime-handle.json',{'private_root':str(PRIVATE),'worktree':str(WT),'api_pid':api.pid,'baseline_pid':baseline.pid,'postgres':PG,'redis':CACHE})
 save('flags.json',{key:env[key] for key in flags})
 with httpx.Client(base_url='http://127.0.0.1:18022/api/v1',timeout=30) as client:
  response=client.post('/auth/setup',json={'username':'claims_admin','email':'claims_admin@invalid.test','password':password});assert response.status_code==201,response.text
 context={'ids':ids,'owner_username':'claims_owner','owner_password':password,'base_url':'http://127.0.0.1:18022/api/v1','baseline_url':'http://127.0.0.1:18024/api/v1'}
 (PRIVATE/'context.json').write_text(json.dumps(context));os.chmod(PRIVATE/'context.json',0o600)
 print('Dedicated runtime ready; metadata gates only. Handle:',PRIVATE,flush=True)
 while not (PRIVATE/'stop').exists():
  assert api.poll() is None and baseline.poll() is None,'Owned runtime stopped unexpectedly'
  time.sleep(1)
finally:
 for process in [api,baseline]:
  if process is not None and process.poll() is None:process.terminate();process.wait(timeout=20)
 for name in [PG,CACHE]:subprocess.run(['docker','stop',name],capture_output=True)
 save('closure.json',{'dedicated_services_stopped':True,'containers_and_data_retained':True,'production_modified':False})
