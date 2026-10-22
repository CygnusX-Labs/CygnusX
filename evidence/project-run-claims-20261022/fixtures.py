"""Controlled historical archives in the dedicated storage; no computation or Task."""
import asyncio
import hashlib
import json
import os
from datetime import UTC,datetime
from pathlib import Path
from uuid import UUID,uuid4

OUT=Path(__file__).resolve().parent
HANDLE=json.loads((OUT/'runtime-handle.json').read_text());PRIVATE=Path(HANDLE['private_root'])
ENV=json.loads((PRIVATE/'environment.json').read_text());os.environ.update(ENV)
CTX=json.loads((PRIVATE/'context.json').read_text())


async def seed():
 from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine
 from cygnusx.application.services.project_archive_service import ArchivedFile,ProjectInfo,archive_run
 from cygnusx.infrastructure.database.models.project import ProjectModel
 from cygnusx.infrastructure.database.models.run import RunModel
 from cygnusx.infrastructure.storage import get_path_factory
 from cygnusx.infrastructure.storage.file_registry import FileRegistry
 from cygnusx.domain.file.value_objects import FileSource
 engine=create_async_engine(ENV['DATABASE_URL']);factory=get_path_factory();owner=UUID(CTX['ids']['claims_owner']);project_id=UUID(CTX['ids']['project_id'])
 result={'archives':{},'owner_id':str(owner),'project_id':str(project_id)}
 async with AsyncSession(engine,expire_on_commit=False) as db:
  for kind in ['complete','missing-manifest','tampered','already-claimed']:
   directory=factory.create_project_run_dir(str(owner),'claim-main','legacy-'+kind)
   path=directory/'output/result.tsv';content=b'feature\tcount\ngeneA\t17\n';path.write_bytes(content);sha=hashlib.sha256(content).hexdigest()
   record=await FileRegistry(db).register(owner,path,source=FileSource.UPLOAD,
    checksum=sha,directory=directory.relative_to(factory.user_root(str(owner))).as_posix())
   await archive_run(user_id=str(owner),project=ProjectInfo(name='Claim main',slug='claim-main'),run_dir=directory,
    analysis_type='historical_archive',status='legacy_recorded',summary='Controlled historical metadata fixture; no Task or calculation',
    artifacts=[ArchivedFile(name=path.name,relative_path='output/result.tsv',size=len(content),md5=hashlib.md5(content).hexdigest(),sha256=sha)],factory=factory,db=db)
   if kind=='missing-manifest':(directory/'manifest.json').unlink()
   if kind=='tampered':path.write_bytes(content.replace(b'17',b'91'))
   result['archives'][kind]={'run_dir':directory.name,'file_id':str(record.id),'sha256':sha}
  bench=ProjectModel(id=uuid4(),user_id=owner,name='Overview benchmark',slug='overview-benchmark',status='active');db.add(bench);await db.flush()
  result['benchmark_project_id']=str(bench.id)
  # Existing disk corpus is deliberately unindexed until the explicit backfill.
  for i in range(100):
   directory=factory.create_project_run_dir(str(owner),'overview-benchmark',f'legacy-benchmark-{i:03d}')
   files=[]
   for j in range(96):
    path=directory/'output'/f'part-{j:03d}.txt';content=f'fixture {i}/{j}\n'.encode();path.write_bytes(content)
    files.append({'path':'output/'+path.name,'size':len(content),'sha256':hashlib.sha256(content).hexdigest()})
   (directory/'README.md').write_text('Historical benchmark fixture; no new scientific execution.\n')
   (directory/'environment.json').write_text(json.dumps({'run':{'analysis_type':'historical_archive','status':'legacy_recorded'}}))
   (directory/'manifest.json').write_text(json.dumps({'schema_version':1,'archived_at':datetime.now(UTC).isoformat(),'files':files}))
  for kind in ['missing-directory','missing-link']:
   rid=uuid4();plan={'name':kind,'operation':'controlled-reconciliation-fixture'}
   if kind=='missing-link':plan['dataset_analysis_link_id']=str(uuid4())
   row=RunModel(id=rid,user_id=owner,project_id=project_id,project_slug='claim-main',flow_id='historical_archive',release_id='archive-v1',
    request_key='negative-'+kind,plan_json=plan,plan_digest=hashlib.sha256(json.dumps(plan).encode()).hexdigest(),status='ARCHIVED_UNCLAIMED',
    archive_directory=kind+'-legacy',archive_present=False,archive_metadata={'locations':[kind+'-legacy'],'dirty':True})
   db.add(row);result[kind+'_run_id']=str(rid)
  await db.commit()
 await engine.dispose();return result


if __name__=='__main__':
 path=PRIVATE/'fixtures.json'
 if not path.exists():
  result=asyncio.run(seed());path.write_text(json.dumps(result));os.chmod(path,0o600)
 else:result=json.loads(path.read_text())
 (OUT/'fixtures.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print('Controlled fixtures ready; benchmark files=9600; Tasks created=0')
