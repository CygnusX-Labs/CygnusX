"""Latest-source claim, audit, invalidation and identity checks against isolated services."""
import asyncio
import json
import os
import subprocess
from collections import Counter
from urllib.parse import unquote
from pathlib import Path
from uuid import UUID

import httpx

OUT=Path(__file__).resolve().parent
# Share only the evidence helpers; do not re-execute the earlier HTTP scenario.
prefix=(OUT/'e2e.py').read_text().split('\nwith httpx.Client',1)[0]
exec(compile(prefix,str(OUT/'e2e.py'),'exec'),globals())
BASE='http://127.0.0.1:18026/api/v1'
records=[]


async def fresh_fixture():
 import hashlib
 from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine
 from cygnusx.application.services.project_archive_service import ProjectInfo,ArchivedFile,archive_run
 from cygnusx.infrastructure.storage import get_path_factory
 from cygnusx.infrastructure.storage.file_registry import FileRegistry
 from cygnusx.domain.file.value_objects import FileSource
 saved=PRIVATE/'final-fixture.json'
 if saved.exists():return json.loads(saved.read_text())
 engine=create_async_engine(ENV['DATABASE_URL']);owner=UUID(FIX['owner_id']);factory=get_path_factory()
 async with AsyncSession(engine,expire_on_commit=False) as db:
  directory=factory.create_project_run_dir(str(owner),'claim-main','legacy-final-source')
  file=directory/'output/result.txt';content=b'Final source historical metadata fixture\n';file.write_bytes(content)
  sha=hashlib.sha256(content).hexdigest()
  record=await FileRegistry(db).register(owner,file,source=FileSource.UPLOAD,checksum=sha,directory=directory.relative_to(factory.user_root(str(owner))).as_posix())
  await archive_run(user_id=str(owner),project=ProjectInfo(name='Claim main',slug='claim-main'),run_dir=directory,
   analysis_type='historical_archive',status='legacy_recorded',artifacts=[ArchivedFile(name=file.name,relative_path='output/result.txt',size=len(content),md5='',sha256=sha)],db=db,factory=factory)
  await db.commit();result={'run_dir':directory.name,'file_id':str(record.id)}
 await engine.dispose();saved.write_text(json.dumps(result));return result


async def deletion_fixture():
 from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine
 from cygnusx.infrastructure.storage import get_path_factory
 from cygnusx.infrastructure.storage.file_registry import FileRegistry
 from cygnusx.domain.file.value_objects import FileSource
 saved=PRIVATE/'delete-fixture.json'
 if saved.exists():return json.loads(saved.read_text())
 factory=get_path_factory();owner=UUID(FIX['owner_id'])
 runs=factory.project_dir(str(owner),'overview-benchmark')/'runs'
 directory=sorted(runs.iterdir())[0];file=directory/'output/part-000.txt'
 engine=create_async_engine(ENV['DATABASE_URL'])
 async with AsyncSession(engine,expire_on_commit=False) as db:
  record=await FileRegistry(db).register(owner,file,source=FileSource.UPLOAD,directory=directory.relative_to(factory.user_root(str(owner))).as_posix())
  await db.commit();result={'project_id':FIX['benchmark_project_id'],'run_dir':directory.name,'file_id':str(record.id),'path':str(file)}
 await engine.dispose();saved.write_text(json.dumps(result));return result


async def alter_user(modules):
 from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine
 from cygnusx.infrastructure.database.models.user import UserModel
 engine=create_async_engine(ENV['DATABASE_URL'])
 async with AsyncSession(engine) as db:
  row=await db.get(UserModel,UUID(FIX['owner_id']));row.disabled_modules=modules;await db.commit()
 await engine.dispose()


async def alter_run_status(run_id,status):
 from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine
 from cygnusx.infrastructure.database.models.run import RunModel
 engine=create_async_engine(ENV['DATABASE_URL'])
 async with AsyncSession(engine) as db:
  row=await db.get(RunModel,UUID(run_id));row.status=status;await db.commit()
 await engine.dispose()


async def verify_audit_and_gates():
 from sqlalchemy import text
 from sqlalchemy.exc import DBAPIError
 from sqlalchemy.ext.asyncio import create_async_engine
 from cygnusx.application.services.agent_tool_gateway import WRITE_RUNTIME_ACCEPTED,digest
 engine=create_async_engine(ENV['DATABASE_URL']);proof=[]
 async with engine.connect() as db:
  aid=await db.scalar(text("SELECT id FROM audit_logs WHERE resource_type='project_run_claim' LIMIT 1"))
  nonclaim=await db.scalar(text("SELECT id FROM audit_logs WHERE resource_type<>'project_run_claim' LIMIT 1"));await db.rollback()
  statements=[('UPDATE claim',"UPDATE audit_logs SET detail=json_build_object('forged',TRUE) WHERE id=:id",aid),
   ('DELETE claim','DELETE FROM audit_logs WHERE id=:id',aid),
   ('relabel nonclaim',"UPDATE audit_logs SET resource_type='project_run_claim' WHERE id=:id",nonclaim),
   ('TRUNCATE','TRUNCATE audit_logs',aid)]
  for name,sql,identifier in statements:
   try:await db.execute(text(sql),{'id':identifier});await db.commit()
   except DBAPIError as exc:
    await db.rollback();assert 'append-only' in str(exc);proof.append({'operation':name,'sql':sql,'blocked':True})
   else:raise AssertionError(name+' was allowed')
  await db.execute(text("UPDATE audit_logs SET detail=json_build_object('temporary',TRUE) WHERE id=:id"),{'id':nonclaim});await db.rollback()
  version=await db.scalar(text('SELECT version_num FROM alembic_version'))
 await engine.dispose()
 data=await snapshot()
 assert WRITE_RUNTIME_ACCEPTED is False
 for row in data['lineage']['rows']:
  handoff=row['handoff'];assert handoff['validation']['worker_paths_verified'] is False
  assert handoff['validation']['dataset_ready'] is False
  assert digest({**handoff,'manifest_hash':None})==row['handoff_hash']
 assert data['counts']['datasets']==data['counts']['dataset_versions']==data['counts']['dataset_analysis_links']==3
 assert data['counts']['tasks']==data['counts']['reports']==data['counts']['project_export_jobs']==0
 save('audit-hardening-proof.json',{'operations':proof,'unrelated_audit_update_allowed_and_rolled_back':True,'alembic_head':version})
 save('final-gate-proof.json',{'WRITE_RUNTIME_ACCEPTED':WRITE_RUNTIME_ACCEPTED,'worker_paths_verified':False,
  'dataset_ready':False,'historical_link_count':3,'Task_count':0,'Report_count':0,'ExportJob_count':0,
  'flags':json.loads((OUT/'flags.json').read_text())})
 return data


final_fixture=asyncio.run(fresh_fixture())
with httpx.Client(base_url=BASE,timeout=45) as api:
 login=api.post('/auth/login',data={'username':CTX['owner_username'],'password':CTX['owner_password']});login.raise_for_status()
 api.headers['Authorization']='Bearer '+login.json()['access_token']
 def call(method,path,status,**kwargs):
  response=api.request(method,path,**kwargs)
  result=response.json() if response.content else None
  item={'method':method,'path':path,'status':response.status_code,'expected':status,'response':result,'claim_audit_id':response.headers.get('x-claim-audit-id')}
  records.append(item);save('final-http-evidence.json',records);assert response.status_code==status,item
  return result
 project=FIX['project_id'];purpose={'purpose':'Latest-source explicit historical claim; not computation.'}
 endpoint=f"/projects/{project}/runs/{final_fixture['run_dir']}/claim"
 with httpx.Client(base_url=BASE,timeout=30) as anonymous:
  response=anonymous.post(endpoint,json=purpose)
  assert response.status_code==401
  records.append({'method':'POST','path':endpoint,'status':response.status_code,'expected':401,'response':response.json(),'claim_audit_id':response.headers.get('x-claim-audit-id')})
 login_other=api.post('/auth/login',data={'username':'claims_other','password':CTX['owner_password']});login_other.raise_for_status()
 call('POST',endpoint,403,json=purpose,headers={'Authorization':'Bearer '+login_other.json()['access_token']})
 call('POST',f'/projects/{project}/runs/..%5Cother-only/claim',422,json=purpose)
 call('POST',f'/projects/{project}/runs/..%2Fother-only/claim',404,json=purpose)
 before=asyncio.run(snapshot());preview=call('POST',endpoint,200,json=purpose)
 if preview['state']=='PREVIEW':
  assert asyncio.run(snapshot())['counts']['datasets']==before['counts']['datasets']
  call('POST',endpoint+'/approve',200,json={'confirmation_id':preview['confirmation_id']})
  claimed=call('POST',endpoint,200,json={**purpose,'action':'commit','confirmation_id':preview['confirmation_id']})
 else:claimed=preview
 save('final-source-claim.json',claimed)
 assert claimed['state']=='HISTORICAL_CLAIMED' and claimed['task_id'] is None
 for module in ['files','tasks','reports']:
  try:
   asyncio.run(alter_user([module]));call('POST',endpoint,403,json=purpose)
   call('GET',f'/projects/{project}/reconciliation',403)
  finally:asyncio.run(alter_user([]))
 # Existing Stage2-style linkage is never replaced by a historical claim.
 try:
  asyncio.run(alter_run_status(claimed['run_id'],'plan_pending'))
  call('POST',endpoint,409,json=purpose)
 finally:asyncio.run(alter_run_status(claimed['run_id'],'HISTORICAL_CLAIMED'))
 # Registry and manifest are independently checked.
 from cygnusx.infrastructure.storage import get_path_factory
 factory=get_path_factory();runs=factory.project_dir(FIX['owner_id'],'claim-main')/'runs'
 tamper=runs/FIX['archives']['tampered']['run_dir'];manifest=tamper/'manifest.json';original_manifest=manifest.read_bytes()
 content=(tamper/'output/result.tsv').read_bytes()
 parsed=json.loads(original_manifest);parsed['files'][0]['sha256']=__import__('hashlib').sha256(content).hexdigest()
 manifest.write_text(json.dumps(parsed))
 try:call('POST',f"/projects/{project}/runs/{tamper.name}/claim",409,json=purpose)
 finally:manifest.write_bytes(original_manifest)
 # Approval cannot authorize bytes changed after review.
 file=tamper/'output/result.tsv';tampered=file.read_bytes();valid=tampered.replace(b'91',b'17');file.write_bytes(valid)
 pre=call('POST',f'/projects/{project}/runs/{tamper.name}/claim',200,json=purpose)
 call('POST',f'/projects/{project}/runs/{tamper.name}/claim/approve',200,json={'confirmation_id':pre['confirmation_id']})
 file.write_bytes(tampered)
 call('POST',f'/projects/{project}/runs/{tamper.name}/claim',409,json={**purpose,'action':'commit','confirmation_id':pre['confirmation_id']})
 # Explicit deletion recalculates metadata, while claimed references remain protected.
 delete=asyncio.run(deletion_fixture());delete_project=delete['project_id']
 overview=call('GET',f'/projects/{delete_project}/overview?run_limit=200',200)
 row=next(r for r in overview['runs'] if r['name']==delete['run_dir'])
 previous=PRIVATE/'delete-before.json'
 if previous.exists():row=json.loads(previous.read_text())
 else:previous.write_text(json.dumps(row))
 if Path(delete['path']).exists():call('DELETE','/files/'+delete['file_id'],200)
 after=call('GET',f'/projects/{delete_project}/overview?run_limit=200',200)
 updated=next(r for r in after['runs'] if r['id']==row['id'])
 assert updated['file_count']==row['file_count']-1
 save('delete-invalidation-proof.json',{'before':row,'after':updated,'same_run_id':row['id']==updated['id']})
 call('DELETE','/files/'+final_fixture['file_id'],409)
 assert (runs/final_fixture['run_dir']/'output/result.txt').is_file()
 owned=call('GET',f'/runs?project_id={project}',200)
 assert all(run['project_id']==project and run['attempt_number']==0 for run in owned)
 call('GET',f"/runs?project_id={CTX['ids']['other_project_id']}",403)
 proposal=f"/projects/{project}/datasets/{claimed['dataset_id']}/versions/{claimed['dataset_version_id']}/analysis-proposals/{claimed['analysis_link_id']}"
 call('POST',proposal+'/execute',403)
 ledger=asyncio.run(snapshot());row=next(r for r in ledger['lineage']['rows'] if str(r['run_id'])==claimed['run_id'])
 cid=row['source_snapshot']['historical_claim']['confirmation_id']
 call('POST','/runs/'+claimed['run_id']+'/confirm',403,json={'confirmation_id':cid,'user_confirmed':True})
 call('POST','/tasks',409,json={'flow_id':'rna_seq','name':'blocked alias','parameters':{},'idempotency_key':'run:'+claimed['run_id']})
 inventory=call('GET',f'/projects/{project}/delivery-inventory',200);save('final-inventory.json',inventory)
 historical=[a for d in inventory['datasets'] for a in d['analyses']]
 assert len(historical)==3 and all(a['record_kind']=='HISTORICAL_CLAIM' and a['compute_state']=='NOT_OBSERVED' and a['task_id'] is None for a in historical)
 before=asyncio.run(snapshot());reconciliation=call('GET',f'/projects/{project}/reconciliation',200);after=asyncio.run(snapshot())
 assert before==after and all(reconciliation[k] for k in ['unclaimed_archives','missing_archives','binding_conflicts'])
 save('final-reconciliation.json',reconciliation)
 save('final-reconciliation-readonly-proof.json',{'full_query_results_unchanged':before==after,'counts':after['counts']})
with (OUT/'migration-retention-block.log').open('w') as log:
 failure=subprocess.run([str(WT/'.venv/bin/alembic'),'downgrade','project_run_identity01'],cwd=WT,env=ENV,stdout=log,stderr=subprocess.STDOUT)
assert failure.returncode!=0 and 'Retained claim audits' in (OUT/'migration-retention-block.log').read_text()
data=asyncio.run(verify_audit_and_gates());save('final-db-evidence.json',data)
expect=Counter()
for filename in ['attempt1-http-evidence.json','http-evidence.json','final-http-evidence.json']:
 for row in json.loads((OUT/filename).read_text()):
  if '/claim' in row['path']:expect[(row['method'],unquote('/api/v1'+row['path']),row['status'])]+=1
actual=Counter((r['method'],r['path'],r['status_code']) for r in data['claim_audit']['rows'] if r['detail'].get('source')!='claim_transaction')
assert all(actual[key]>=value for key,value in expect.items()),(expect-actual)
request_rows={str(row['id']):row for row in data['claim_audit']['rows']}
for record in records:
 if '/claim' in record['path']:
  assert record['claim_audit_id'] in request_rows
  row=request_rows[record['claim_audit_id']]
  assert row['status_code']==record['status'] and row['path']==unquote('/api/v1'+record['path'])
save('claim-audit-receipts.json',[{'audit_id':r['claim_audit_id'],'path':r['path'],'status':r['status']} for r in records if '/claim' in r['path']])
save('claim-audit-coverage.json',{'recorded_http_claim_requests':sum(expect.values()),'matching_request_audits':sum(actual.values()),'every_recorded_outcome_has_durable_request_audit':True,'path_comparison':'URL-decoded ASGI request paths'})
print('Latest-source HTTP checks:',len(records),'; historical chains=3; Tasks=0; append-only and invalidation verified.')
