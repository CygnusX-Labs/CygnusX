"""Real HTTP + PostgreSQL/Redis claim acceptance, including explicit human JWT decisions."""
import asyncio
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from uuid import UUID

import httpx

OUT=Path(__file__).resolve().parent
PRIVATE=Path(json.loads((OUT/'runtime-handle.json').read_text())['private_root'])
ENV=json.loads((PRIVATE/'environment.json').read_text());os.environ.update(ENV)
CTX=json.loads((PRIVATE/'context.json').read_text());FIX=json.loads((PRIVATE/'fixtures.json').read_text())
WT=Path(json.loads((OUT/'worktree.json').read_text())['implementation_worktree'])
records=[]


def save(name,data):
 (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n')


async def snapshot():
 from sqlalchemy import text
 from sqlalchemy.ext.asyncio import create_async_engine
 engine=create_async_engine(ENV['DATABASE_URL']);queries={
 'lineage':'''SELECT d.id AS dataset_id,d.user_id,d.project_id,d.status AS dataset_status,
 v.id AS version_id,v.status AS version_status,v.source_snapshot,v.review_annotations,v.handoff,
 l.id AS link_id,l.state AS link_state,l.task_id,l.handoff_hash,l.normalized_request,
 r.id AS run_id,r.project_id AS run_project_id,r.status AS run_status,r.request_key,r.attempt_number,
 r.archive_directory,r.archive_identity,r.archive_manifest_sha256,r.archive_metadata,r.plan_json
 FROM datasets d JOIN dataset_versions v ON v.dataset_id=d.id
 JOIN dataset_analysis_links l ON l.version_id=v.id
 JOIN platform_runs r ON r.plan_json->>'dataset_analysis_link_id'=l.id::text ORDER BY d.created_at''',
 'run_index':'''SELECT id,user_id,project_id,project_slug,status,task_id,archive_directory,archive_present,
 archive_file_count,archive_total_bytes,archive_last_activity,archive_indexed_at,archive_metadata
 FROM platform_runs ORDER BY id''',
 'claim_audit':'''SELECT id,user_id,method,path,status_code,detail,created_at FROM audit_logs
 WHERE resource_type='project_run_claim' ORDER BY created_at,id'''}
 result={}
 async with engine.connect() as db:
  for name,sql in queries.items():result[name]={'sql':sql,'rows':[dict(row) for row in (await db.execute(text(sql))).mappings()]}
  result['counts']={table:await db.scalar(text('SELECT count(*) FROM '+table)) for table in ['datasets','dataset_versions','dataset_analysis_links','platform_runs','tasks','reports','project_export_jobs','audit_logs']}
 await engine.dispose();return result


async def prove_append_only():
 from sqlalchemy import text
 from sqlalchemy.exc import DBAPIError
 from sqlalchemy.ext.asyncio import create_async_engine
 engine=create_async_engine(ENV['DATABASE_URL']);proof=[]
 async with engine.connect() as db:
  rid=await db.scalar(text("SELECT id FROM audit_logs WHERE resource_type='project_run_claim' LIMIT 1"))
  await db.rollback()
  assert rid is not None
  for statement in ["UPDATE audit_logs SET detail=json_build_object('forged',TRUE) WHERE id=:id",'DELETE FROM audit_logs WHERE id=:id']:
   try:
    await db.execute(text(statement),{'id':rid});await db.commit()
   except DBAPIError as exc:
    await db.rollback();assert 'append-only' in str(exc)
    proof.append({'statement':statement,'id':str(rid),'blocked':True,'reason':'project run claim audit is append-only'})
   else:raise AssertionError('Claim audit was mutable')
 await engine.dispose();save('append-only-proof.json',proof)


with httpx.Client(base_url=CTX['base_url'],timeout=90) as api:
 def token(name):
  response=api.post('/auth/login',data={'username':name,'password':CTX['owner_password']});response.raise_for_status();return 'Bearer '+response.json()['access_token']
 owner_auth,other_auth=token('claims_owner'),token('claims_other')
 api.headers['Authorization']=owner_auth
 def call(method,path,status,**kwargs):
  response=api.request(method,path,**kwargs)
  row={'method':method,'path':path,'status':response.status_code,'expected':status,'response':response.json()}
  records.append(row);save('http-evidence.json',records)
  assert response.status_code==status,row
  return response.json()
 project=FIX['project_id'];archives=FIX['archives']
 def endpoint(kind):return f"/projects/{project}/runs/{archives[kind]['run_dir']}/claim"
 purpose={'purpose':'Preserve explicit historical archive references; no new computation.'}
 initial=asyncio.run(snapshot())
 if not (OUT/'db-before-claims.json').exists():save('db-before-claims.json',initial)
 with httpx.Client(base_url=CTX['base_url']) as anonymous:
  r=anonymous.post(endpoint('complete'),json=purpose);assert r.status_code==401
  records.append({'method':'POST','path':endpoint('complete'),'actor':'anonymous','status':r.status_code,'expected':401,'response':r.json()})
 call('POST',endpoint('complete'),403,json=purpose,headers={'Authorization':other_auth})
 call('POST',f"/projects/{project}/runs/..%5Cother-only/claim",422,json=purpose)
 call('POST',f"/projects/{project}/runs/..%2Fother-only/claim",404,json=purpose)
 call('POST',endpoint('complete'),422,json={**purpose,'project_id':CTX['ids']['other_project_id']})
 call('POST',endpoint('missing-manifest'),422,json=purpose)
 call('POST',endpoint('tampered'),409,json=purpose)
 negative=asyncio.run(snapshot());assert negative['counts']['datasets']==initial['counts']['datasets']
 save('db-after-rejections.json',negative)

 def claim(kind):
  path=endpoint(kind);preview=call('POST',path,200,json=purpose)
  if preview['state']=='HISTORICAL_CLAIMED':return preview
  before=asyncio.run(snapshot())
  assert before['counts']['datasets']==initial['counts']['datasets']+(1 if kind=='complete' else 0)
  call('POST',path,409,json={**purpose,'action':'commit','confirmation_id':preview['confirmation_id']})
  call('POST',path+'/approve',200,json={'confirmation_id':preview['confirmation_id']})
  result=call('POST',path,200,json={**purpose,'action':'commit','confirmation_id':preview['confirmation_id']})
  assert result['state']=='HISTORICAL_CLAIMED' and result['task_id'] is None
  repeated=call('POST',path,200,json=purpose)
  for key in ['run_id','dataset_id','dataset_version_id','analysis_link_id']:assert repeated[key]==result[key]
  return result

 already=claim('already-claimed');complete=claim('complete')
 save('claim-replay-results.json' if (OUT/'claim-results.json').exists() else 'claim-results.json',{'complete':complete,'already_claimed':already})
 state=asyncio.run(snapshot());assert state['counts']['datasets']==2 and state['counts']['dataset_analysis_links']==2
 assert not any(state['counts'][key] for key in ['tasks','reports','project_export_jobs'])
 for row in state['lineage']['rows']:
  assert row['dataset_status']==row['version_status']==row['link_state']==row['run_status']=='HISTORICAL_CLAIMED'
  assert str(row['project_id'])==str(row['run_project_id'])==project
  assert row['task_id'] is None and row['handoff']['validation']['worker_paths_verified'] is False
  assert row['handoff']['validation']['dataset_ready'] is False
 save('db-after-claims.json',state)
 # Move both within the filesystem and by copy+delete (new inode), with no duplicate lineage.
 from cygnusx.infrastructure.storage import get_path_factory
 factory=get_path_factory();runs=factory.project_dir(FIX['owner_id'],'claim-main')/'runs'
 path=runs/archives['complete']['run_dir']
 renamed=runs/'renamed-historical-archive';moved=runs/'moved-historical-archive'
 if path.exists():path.rename(renamed)
 if renamed.exists():
  replay=call('POST',f'/projects/{project}/runs/{renamed.name}/claim',200,json=purpose);assert replay['run_id']==complete['run_id']
  shutil.copytree(renamed,moved);shutil.rmtree(renamed)
 replay=call('POST',f'/projects/{project}/runs/{moved.name}/claim',200,json=purpose)
 assert replay['run_id']==complete['run_id'] and replay['dataset_id']==complete['dataset_id']
 FIX['archives']['complete']['run_dir']=moved.name
 (PRIVATE/'fixtures.json').write_text(json.dumps(FIX))
 # The already-claimed archive still rejects changed bytes.
 artifact=moved/'output/result.tsv';original=artifact.read_bytes();artifact.write_bytes(original.replace(b'17',b'81'))
 try:call('POST',f'/projects/{project}/runs/{moved.name}/claim',409,json=purpose)
 finally:artifact.write_bytes(original)
 view=call('GET',f'/projects/{project}/delivery-inventory',200)
 historical=[a for d in view['datasets'] for a in d['analyses'] if a.get('record_kind')=='HISTORICAL_CLAIM']
 assert len(historical)==2 and all(a['compute_state']=='NOT_OBSERVED' and a['task_id'] is None and a['delivery_state']=='HISTORICAL_REFERENCE' for a in historical)
 save('historical-inventory.json',view)
 # Explicit maintenance backfill is separate from GET and from claim approval.
 with (OUT/'backfill.log').open('w') as log:
  subprocess.run([str(WT/'.venv/bin/python'),'scripts/backfill_project_run_index.py','--expected-database','run_claim_test_20261022','--confirm-isolated','--output',str(OUT/'backfill-project-results.json')],cwd=WT,env=ENV,stdout=log,stderr=subprocess.STDOUT,check=True)
 before=asyncio.run(snapshot());reconciliation=call('GET',f'/projects/{project}/reconciliation',200);after=asyncio.run(snapshot())
 assert all(reconciliation[key] for key in ['unclaimed_archives','missing_archives','binding_conflicts'])
 assert reconciliation['automatic_repairs']==0 and before==after
 save('reconciliation.json',reconciliation);save('reconciliation-readonly-proof.json',{'before_counts':before['counts'],'after_counts':after['counts'],'full_query_results_unchanged':before==after})
 # Same-project HTTP timing, same 100 archive rows, old recursive endpoint vs full indexed page.
 bench=FIX['benchmark_project_id'];url=f'/projects/{bench}/overview'
 with httpx.Client(base_url=CTX['baseline_url'],headers={'Authorization':owner_auth},timeout=90) as old:
  samples={}
  for label,client in [('recursive_baseline',old),('indexed',api)]:
   for _ in range(3):response=client.get(url,params={'run_limit':200});response.raise_for_status()
   elapsed=[]
   for _ in range(25):
    start=time.perf_counter();response=client.get(url,params={'run_limit':200});elapsed.append((time.perf_counter()-start)*1000)
    response.raise_for_status();assert len(response.json()['runs'])==100
   samples[label]={'samples_ms':elapsed,'median_ms':statistics.median(elapsed),'p95_ms':sorted(elapsed)[23],'run_count':100}
  save('overview-latency.json',{'project_id':bench,'physical_files':9900,'method':'3 warmups + 25 HTTP requests each; both return all 100 rows; same PG/storage; no artificial delay',**samples})
 page1=call('GET',url+'?run_limit=7&run_offset=0',200);page2=call('GET',url+'?run_limit=7&run_offset=7',200)
 assert page1['runs_total']==page2['runs_total']==100 and len(page1['runs'])==len(page2['runs'])==7
 assert not {r['id'] for r in page1['runs']} & {r['id'] for r in page2['runs']}
 asyncio.run(prove_append_only())
 final=asyncio.run(snapshot());assert final['counts']['datasets']==2 and final['counts']['dataset_versions']==2 and final['counts']['dataset_analysis_links']==2
 assert all(final['counts'][name]==0 for name in ['tasks','reports','project_export_jobs'])
 assert any(row['status_code']==401 for row in final['claim_audit']['rows'])
 assert any(row['status_code']==403 for row in final['claim_audit']['rows'])
 assert any(row['detail'].get('code')=='ARCHIVE_FILE_CHANGED' for row in final['claim_audit']['rows'])
 save('db-final.json',final);save('http-evidence.json',records)
 print('Real HTTP checks:',len(records),'; lineage counts:',{k:final['counts'][k] for k in ['datasets','dataset_versions','dataset_analysis_links','tasks']})
