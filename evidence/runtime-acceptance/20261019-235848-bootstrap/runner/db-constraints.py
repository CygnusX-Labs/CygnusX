import sys,json,asyncio
from pathlib import Path
sys.path.insert(0,'/acceptance')
from runtime import configure
configure()
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from cygnusx.core.config import get_settings

async def main():
 engine=create_async_engine(get_settings().database_url,echo=False)
 rows=[]
 async with engine.connect() as c:
  pid=json.loads(Path('/tmp/research-private.json').read_text())['plan']
  for name,sql,expected in [
   ('immutable_digest',"UPDATE research_plans SET digest=repeat('0',64) WHERE id=:id",'P0001'),
   ('immediate_superseded_fk',"UPDATE research_plans SET superseded_by='00000000-0000-0000-0000-000000000001' WHERE id=:id",'23503'),
   ('duplicate_primary_key',"INSERT INTO research_plans SELECT * FROM research_plans WHERE id=:id",'23505'),
  ]:
   trans=await c.begin_nested()
   try:
    await c.execute(text(sql),{'id':pid});rows.append({'name':name,'ok':False,'sql':sql,'sqlstate':None})
   except Exception as e:
    code=getattr(getattr(e,'orig',None),'sqlstate',None)
    rows.append({'name':name,'ok':code==expected,'sql':sql,'sqlstate':code,'error':str(e).split('[SQL:')[0]})
   finally:await trans.rollback()
  tables={}
  for table in ['research_plans','tasks','reports','project_export_jobs','mcp_versions']:
   tables[table]=(await c.execute(text('SELECT count(*) FROM '+table))).scalar()
  plans=(await c.execute(text('SELECT id::text,version,status,digest,reviewed_at::text,superseded_by::text FROM research_plans ORDER BY created_at'))).mappings().all()
  Path('/tmp/research-evidence/db-constraints.json').write_text(json.dumps({'checks':rows,'table_counts':tables,'plans':[dict(p) for p in plans]},ensure_ascii=False,indent=2))
 await engine.dispose()
 print(json.dumps({'checks':len(rows),'failed':[r['name'] for r in rows if not r['ok']]}))
asyncio.run(main())
