import sys, os, json, secrets, asyncio, runpy, time, copy
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, '/acceptance')
from runtime import configure
configure()
import httpx

O=Path('/tmp/research-evidence'); O.mkdir(exist_ok=True)
C=Path('/tmp/research-private.json')
rows=[]
client=httpx.Client(base_url='http://api:8000/api/v1', timeout=45)
def call(name, method, path, expected=(200,), token=None, **kwargs):
    if token: kwargs.setdefault('headers',{})['Authorization']='Bearer '+token
    r=client.request(method,path,**kwargs)
    try: body=r.json()
    except Exception: body=r.text[:800]
    if isinstance(body,dict):
        body={k:v for k,v in body.items() if k not in ('access_token','refresh_token','api_key','key')}
    row=dict(name=name,method=method,path=path,status=r.status_code,ok=r.status_code in expected,body=body)
    rows.append(row)
    (O/(sys.argv[1]+'.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    return r
def login(username,password):
    r=call('login.'+username,'POST','/auth/login',data={'username':username,'password':password})
    return r.json()['access_token']
if sys.argv[1]=='plan':
    suffix=secrets.token_hex(3)
    pw='A1!'+secrets.token_hex(16)
    os.environ.update(OMICHBUB_INIT_ADMIN_USERNAME='admin_'+suffix,OMICHBUB_INIT_ADMIN_EMAIL='admin_'+suffix+'@example.invalid',OMICHBUB_INIT_ADMIN_PASSWORD=pw)
    asyncio.run(runpy.run_path('/app/scripts/init_admin.py')['main']())
    admin=login('admin_'+suffix,pw)
    ctx={'admin':admin,'admin_password':pw}
    for name in ['owner','other']:
        password='A1!'+secrets.token_hex(16)
        r=call('register.'+name,'POST','/auth/register',(201,),json={'username':'accept_'+name+'_'+suffix,'email':'accept_'+name+'_'+suffix+'@example.invalid','password':password})
        uid=r.json()['id']
        call('approve.'+name,'PUT',f'/admin/users/{uid}/approve',token=admin)
        call('modules.'+name,'PUT',f'/admin/users/{uid}/modules',token=admin,json={'disabled_modules':[]})
        ctx[name]=login('accept_'+name+'_'+suffix,password);ctx[name+'_password']=password;ctx[name+'_id']=uid
    C.write_text(json.dumps(ctx));C.chmod(0o600)
    owner=ctx['owner'];other=ctx['other']
    r=call('project.create','POST','/projects',(201,),token=owner,json={'name':'Bootstrap acceptance — no scientific corpus'})
    p=r.json()['id'];ctx['project']=p;base=f'/projects/{p}/research-plans'
    draft={'research_question':'验收计划版本与人工审阅，不运行计算或发布报告','steps':[{'step_id':'publish','kind':'REPORT_PUBLISH','goal':'保持发布阻断'}]}
    payload={'request_key':str(uuid4()),'draft':draft}
    r=call('RP.create','POST',base,token=owner,json=payload);plan=r.json();pid=plan['plan_id'];ctx['plan']=pid;C.write_text(json.dumps(ctx))
    call('RP.idempotent','POST',base,token=owner,json=payload)
    changed=copy.deepcopy(payload);changed['draft']['research_question']='conflicting retry'
    call('RP.key_conflict','POST',base,(409,),token=owner,json=changed)
    call('RP.list','GET',base,token=owner)
    call('RP.cross_owner','GET',base+'/'+pid,(404,),token=other)
    call('RP.unauthenticated','GET',base+'/'+pid,(401,))
    r=call('key.create','POST','/auth/api-keys',(201,),token=owner,json={'name':'acceptance-jwt-boundary'})
    key=r.json().get('key') or r.json().get('api_key');ctx['api_key']=key
    call('RP.api_key_review_denied','POST',base+'/'+pid+'/review',(401,),headers={'X-API-Key':key},json={'expected_digest':plan['digest']})
    call('RP.stale_review','POST',base+'/'+pid+'/review',(409,),token=owner,json={'expected_digest':'0'*64})
    r=call('RP.review','POST',base+'/'+pid+'/review',token=owner,json={'expected_digest':plan['digest']})
    call('RP.review_idempotent','POST',base+'/'+pid+'/review',token=owner,json={'expected_digest':plan['digest']})
    revision={'request_key':str(uuid4()),'expected_digest':plan['digest'],'draft':copy.deepcopy(draft)}
    revision['draft']['research_question']+='；修订后需重新审阅'
    r=call('RP.revise','POST',base+'/'+pid+'/versions',token=owner,json=revision)
    v=r.json();ctx['plan_v2']=v['plan_id'];ctx['digest_v2']=v['digest']
    call('RP.superseded_review','POST',base+'/'+pid+'/review',(409,),token=owner,json={'expected_digest':plan['digest']})
    call('RP.refresh_v2','GET',base+'/'+v['plan_id'],token=owner)
    bad={'request_key':str(uuid4()),'draft':copy.deepcopy(draft)};bad['draft']['steps'][0]['arguments']={'shell':'echo forbidden'}
    call('RP.forbidden_input','POST',base,(422,),token=owner,json=bad)
    call('RE.project_empty','GET',f'/projects/{p}/research-delivery',token=owner)
    call('RE.cross_owner','GET',f'/projects/{p}/research-delivery',(404,),token=other)
    call('RE.unknown_task','GET',f'/tasks/{uuid4()}/provenance',(404,),token=owner)
    call('RE.unknown_report','GET',f'/reports/{uuid4()}/provenance',(404,),token=owner)
    call('PE.inventory_empty','GET',f'/projects/{p}/delivery-inventory',token=owner)
    call('PE.prepare_writes_closed','POST',f'/projects/{p}/exports/prepare',(403,),token=owner,json={'kind':'evidence'})
    C.write_text(json.dumps(ctx));C.chmod(0o600)
print(json.dumps({'checks':len(rows),'passed':sum(r['ok'] for r in rows),'failed':[r['name'] for r in rows if not r['ok']]}))
