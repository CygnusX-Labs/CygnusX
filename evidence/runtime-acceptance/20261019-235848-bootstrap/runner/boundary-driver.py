import sys,json,asyncio
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,'/acceptance')
from runtime import configure
configure()
import httpx
from cygnusx.core.config import get_settings
from cygnusx.application.services.agent_tool_gateway import WRITE_RUNTIME_ACCEPTED

c=httpx.Client(base_url='http://api:8000/api/v1',timeout=30)
ctx=json.loads(Path('/tmp/research-private.json').read_text());p=ctx['project'];pid=ctx['plan_v2'];owner=ctx['owner'];admin=ctx['admin']
rows=[]
def req(name,method,path,expected=(200,),token=owner,**kw):
 r=c.request(method,path,headers={'Authorization':'Bearer '+token} if token else {},**kw)
 rows.append({'name':name,'method':method,'path':path,'status':r.status_code,'ok':r.status_code in expected,'body':r.json()});Path('/tmp/research-evidence/boundary-progress.json').write_text(json.dumps(rows,ensure_ascii=False));return r
base=f'/projects/{p}/research-plans/{pid}'
req('RP.review_state_after_browser','GET',base)
models=req('RP.session_models','GET','/chat/models').json()
session=req('RP.real_session','POST','/chat/sessions',json={'project_id':p,'model_id':models[0]['id'],'title':'PLAN_ONLY boundary; no LLM call'}).json()
r=req('RP.advance_no_publish','POST',base+'/advance',json={'session_id':session['session_id']})
rows[-1]['ok'] = rows[-1]['ok'] and r.json()['steps'][0]['status']=='WAITING_APPROVAL'

req('RP.events','GET',base+'/events')
req('RP.reconcile_no_rerun','POST',base+'/reconcile')
req('RP.module_revoke','PUT',f"/admin/users/{ctx['owner_id']}/modules",token=admin,json={'disabled_modules':['reports']})
req('RP.revoked_read','GET',base,(403,))
req('RE.revoked_read','GET',f'/projects/{p}/research-delivery',(403,))
req('RP.module_restore','PUT',f"/admin/users/{ctx['owner_id']}/modules",token=admin,json={'disabled_modules':[]})
req('RE.unauthenticated','GET',f'/projects/{p}/research-delivery',(401,),token=None)
req('RE.cross_project','GET',f'/projects/{uuid4()}/research-delivery',(404,))
r=req('PE.prepare_is_readonly','POST',f'/projects/{p}/exports/prepare',json={'kind':'evidence'})
req('PE.create_gate_closed','POST',f'/projects/{p}/exports',(403,),json={'selection':{'kind':'evidence'},'manifest_digest':r.json()['manifest_digest'],'request_key':str(uuid4())})
req('PE.inventory_cross_owner','GET',f'/projects/{p}/delivery-inventory',(404,),token=ctx['other'])
req('PE.unknown_job','GET',f'/projects/{p}/exports/{uuid4()}',(403,))
req('RP.cancel','POST',base+'/control',json={'action':'cancel'})
req('RP.cancel_refresh','GET',base)
s=get_settings()
payload={'checks':rows,'effective_flags':{name:getattr(s,name) for name in ['research_plan_enabled','research_delivery_read_enabled','research_delivery_write_enabled','project_export_enabled','project_report_write_enabled','project_report_pdf_enabled','agent_analysis_write_enabled','agent_download_write_enabled','tool_gateway_read_enabled']},'WRITE_RUNTIME_ACCEPTED':WRITE_RUNTIME_ACCEPTED}
Path('/tmp/research-evidence/boundaries.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
print(json.dumps({'checks':len(rows),'failed':[r['name'] for r in rows if not r['ok']]}))
