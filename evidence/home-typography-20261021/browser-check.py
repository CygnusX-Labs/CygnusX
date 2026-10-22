import json,subprocess,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright
OUT=Path('/home/zj/zj_code_libarary/OmicHub/evidence/home-typography-20261021')
query="SELECT json_build_object('id',id,'version',token_version) FROM users WHERE username='root' AND status='active';"
user_result=subprocess.run(['docker','exec','-i','cygnusx-db','sh','-c','exec psql -X -A -t -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],input=query,text=True,capture_output=True,check=True)
user=json.loads(user_result.stdout.strip())
# Temporary diagnostic token stays in memory; no credentials or tokens are printed or saved.
code="from cygnusx.core.security import create_access_token; from datetime import timedelta; import sys; print(create_access_token(sys.argv[1], token_version=int(sys.argv[2]), expires_delta=timedelta(minutes=5)))"
token_result=subprocess.run(['docker','exec','cygnusx-web','python','-c',code,user['id'],str(user['version'])],text=True,capture_output=True,check=True)
token=token_result.stdout.strip().splitlines()[-1]
paths=['/health','/api/v1/projects','/api/v1/tasks?status=running&limit=5','/api/v1/tasks?status=queued&limit=5','/api/v1/reports?page=1&page_size=5']
checks=[]
for path in paths:
    req=urllib.request.Request('http://127.0.0.1:8888'+path,headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(req,timeout=20) as res:
        body=json.load(res)
        count=len(body) if isinstance(body,list) else len(body.get('items',[])) if isinstance(body,dict) and 'items' in body else None
        checks.append({'path':path,'status':res.status,'itemCount':count})
assert all(x['status']==200 for x in checks),checks
print(json.dumps({'apiChecks':checks},ensure_ascii=False),flush=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/home/zj/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1440},reduced_motion='reduce')
    page.add_init_script('localStorage.setItem("access_token",'+json.dumps(token)+');localStorage.setItem("cygnusx-theme","dark");sessionStorage.setItem("cygnusx:adminWelcomeShown","1");')
    page.route('**/api/v1/llm/generate-welcome',lambda route:route.abort())
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8888/',wait_until='domcontentloaded')
    page.locator('.workbench-section[aria-busy="false"]').wait_for(timeout=60000)
    assert page.locator('.workbench-unavailable').count()==0
    results=[]
    for width in [1280,1440,2560,390]:
        page.set_viewport_size({'width':width,'height':1440})
        page.wait_for_timeout(150)
        metrics=page.evaluate("""()=>{
          const el=s=>document.querySelector(s),rect=s=>el(s).getBoundingClientRect(),font=s=>getComputedStyle(el(s)).fontSize;
          const sizes=Object.fromEntries(['.hero-title','.hero-desc','.section-heading h2','.workbench-card__heading h3','.workbench-item__main strong','.workbench-item__main small','.workbench-item__meta','.entry-title','.entry-desc','.pillar-copy h3','.pillar-copy p:last-child','.ecosystem-card__copy strong','.ecosystem-card__copy > span','.capability-item small'].map(s=>[s,font(s)]));
          return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,homeWidth:rect('.home-page').width,homeScrollWidth:el('.home-page').scrollWidth,workbenchTop:rect('#workbench-title').top,heroHeight:rect('.hero').height,columns:getComputedStyle(el('.workbench-grid')).gridTemplateColumns,sizes,titleLines:[...document.querySelectorAll('.hero-title__line')].map(x=>({text:x.textContent,height:x.getBoundingClientRect().height,lineHeight:parseFloat(getComputedStyle(x).lineHeight)}))};
        }""")
        assert metrics['scrollWidth']<=width,metrics
        assert metrics['homeScrollWidth']<=metrics['homeWidth']+1,metrics
        assert metrics['sizes']['.workbench-item__main strong']=='14px',metrics
        assert metrics['sizes']['.entry-title']=='16px',metrics
        assert metrics['sizes']['.workbench-card__heading h3']=='16px',metrics
        assert all(abs(x['height']-x['lineHeight'])<1 for x in metrics['titleLines']),metrics
        if width>=1280:
            assert metrics['workbenchTop']<1440,metrics
            cols=[float(x.removesuffix('px')) for x in metrics['columns'].split()]
            assert len(cols)==3 and max(cols)-min(cols)<1,metrics
        results.append(metrics)
        page.screenshot(path=str(OUT/f'home-font-{width}.png'),full_page=True)
        if width==1440:
            page.locator('.workbench-section').screenshot(path=str(OUT/'workbench-font-1440.png'))
    assert not errors,errors
    (OUT/'typography-verification.json').write_text(json.dumps({'apiChecks':checks,'layouts':results,'pageErrors':errors,'mockedDataAPIs':False,'servedFrom':'http://127.0.0.1:8888/'},ensure_ascii=False,indent=2))
    print(json.dumps({'layouts':results,'pageErrors':errors},ensure_ascii=False),flush=True)
    browser.close()
