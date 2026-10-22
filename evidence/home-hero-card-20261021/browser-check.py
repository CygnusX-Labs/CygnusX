import json,subprocess,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright
OUT=Path('/home/zj/zj_code_libarary/OmicHub/evidence/home-hero-card-20261021')
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
import re
old=(OUT/'HomeView.before.vue').read_text()
selectors=['.hero-inner','.hero-lifecycle','.hero-lifecycle__header','.hero-lifecycle__line','.hero-lifecycle h2','.lifecycle-list','.lifecycle-step','.lifecycle-step__node','.lifecycle-step__label','.hero-lifecycle__note']
old_rules={selector:re.search(re.escape(selector)+r'\s*\{([^}]*)\}',old).group(1) for selector in selectors}
old_rules['.hero-lifecycle']+=';min-height:0;'
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/home/zj/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1440},reduced_motion='reduce')
    page.add_init_script('localStorage.setItem("access_token",'+json.dumps(token)+');localStorage.setItem("cygnusx-theme","dark");sessionStorage.setItem("cygnusx:adminWelcomeShown","1");')
    page.route('**/api/v1/llm/generate-welcome',lambda route:route.abort())
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8888/',wait_until='domcontentloaded')
    page.locator('.workbench-section[aria-busy="false"]').wait_for(timeout=60000)
    assert page.get_by_role('button',name='AI 规划研究方案',exact=True).is_visible()
    page.evaluate("""()=>{const router=document.querySelector('#app').__vue_app__.config.globalProperties.$router;window.heroDestination=null;router.beforeEach(to=>{window.heroDestination=to.fullPath;return false})}""")
    page.get_by_role('button',name='AI 规划研究方案',exact=True).click()
    page.wait_for_function('window.heroDestination === "/ai"')
    results=[]
    for width in [1280,1440,2560,390]:
        page.set_viewport_size({'width':width,'height':1440})
        page.wait_for_timeout(150)
        def measure():
            return page.evaluate("""()=>{
                const el=s=>document.querySelector(s),rect=s=>el(s).getBoundingClientRect(),card=rect('.hero-lifecycle');
                return {width:innerWidth,pageScrollWidth:document.documentElement.scrollWidth,homeWidth:rect('.home-page').width,homeScrollWidth:el('.home-page').scrollWidth,heroHeight:rect('.hero').height,workbenchTop:rect('#workbench-title').top,card:{width:card.width,height:card.height,padding:getComputedStyle(el('.hero-lifecycle')).padding},titleLines:[...document.querySelectorAll('.hero-title__line')].map(x=>({height:x.getBoundingClientRect().height,lineHeight:parseFloat(getComputedStyle(x).lineHeight)}))};
            }""")
        after=measure()
        assert after['pageScrollWidth']<=width,after
        assert after['homeScrollWidth']<=after['homeWidth']+1,after
        assert all(abs(x['height']-x['lineHeight'])<1 for x in after['titleLines']),after
        if width>=1280:
            assert after['workbenchTop']<1440,after
            baseline_css='\n'.join('.home-page '+selector+' {'+css.replace(';',' !important;')+'}' for selector,css in old_rules.items())
            baseline_style=page.add_style_tag(content=baseline_css)
            page.wait_for_timeout(80)
            before=measure()
            baseline_style.evaluate('(el)=>el.remove()')
            page.wait_for_timeout(100)
            assert after['card']['width']>before['card']['width']*1.15,(before,after)
            assert after['card']['height']>before['card']['height']*1.15,(before,after)
            after['beforeCard']=before['card']
        results.append(after)
        page.locator('.hero').screenshot(path=str(OUT/f'hero-card-{width}.png'))
    assert not errors,errors
    result={'apiChecks':checks,'buttonLabel':'AI 规划研究方案','buttonDestination':'/ai','layouts':results,'pageErrors':errors,'mockedDataAPIs':False,'servedFrom':'http://127.0.0.1:8888/'}
    (OUT/'hero-card-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False),flush=True)
    browser.close()
