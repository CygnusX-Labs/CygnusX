import json,subprocess,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from playwright.sync_api import sync_playwright
OUT=Path('/home/zj/zj_code_libarary/OmicHub/evidence/brand-logo-20261021')
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
import hashlib
source=Path('/home/zj/zj_code_libarary/OmicHub/docs/青蓝渐变天鹅轨道徽标.png')
public=Path('/home/zj/zj_code_libarary/OmicHub/frontend/public/cygnusx-logo.png')
assert source.read_bytes()==public.read_bytes()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/home/zj/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':900},reduced_motion='reduce')
    page.add_init_script('localStorage.setItem("access_token",'+json.dumps(token)+');localStorage.setItem("cygnusx-theme","dark");sessionStorage.setItem("cygnusx:adminWelcomeShown","1");')
    page.route('**/api/v1/llm/generate-welcome',lambda route:route.abort())
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8888/',wait_until='domcontentloaded')
    page.locator('.logo-image').wait_for()
    page.wait_for_function('document.querySelector(".logo-image").complete && document.querySelector(".logo-image").naturalWidth > 0')
    favicon=page.locator('link[rel="icon"]').evaluate('(el)=>({href:el.href,type:el.type})')
    response=page.request.get(favicon['href'])
    assert response.status==200 and 'image/png' in response.headers.get('content-type',''),response.status
    assert response.body()==source.read_bytes()
    assert favicon['href'].endswith('/cygnusx-logo.png') and favicon['type']=='image/png',favicon
    header=page.locator('.logo-image').evaluate('(el)=>({src:el.currentSrc,naturalWidth:el.naturalWidth,naturalHeight:el.naturalHeight,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height,fit:getComputedStyle(el).objectFit,alt:el.alt,background:getComputedStyle(el.parentElement).backgroundColor})')
    assert header['src']==favicon['href'],header
    assert header['naturalWidth']==1254 and header['width']==40 and header['height']==40,header
    assert header['fit']=='contain' and header['background']=='rgba(0, 0, 0, 0)',header
    page.locator('.top-nav').screenshot(path=str(OUT/'header-logo-dark.png'))
    page.evaluate('document.documentElement.setAttribute("data-theme","light")')
    page.wait_for_timeout(200)
    page.locator('.top-nav').screenshot(path=str(OUT/'header-logo-light.png'))
    page.evaluate('document.documentElement.setAttribute("data-theme","dark")')
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(200)
    page.locator('.hamburger-btn').click()
    page.locator('.mobile-logo-icon').wait_for()
    page.wait_for_function('document.querySelector(".mobile-logo-icon").complete && document.querySelector(".mobile-logo-icon").naturalWidth > 0')
    mobile=page.locator('.mobile-logo-icon').evaluate('(el)=>({src:el.currentSrc,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height,naturalWidth:el.naturalWidth})')
    assert mobile['src']==favicon['href'] and mobile['width']==40 and mobile['naturalWidth']==1254,mobile
    page.locator('.mobile-logo').screenshot(path=str(OUT/'mobile-drawer-logo.png'))
    assert not errors,errors
    result={'originalBytesPreserved':True,'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'assetBytes':source.stat().st_size,'favicon':favicon,'faviconStatus':response.status,'header':header,'mobileDrawer':mobile,'pageErrors':errors}
    (OUT/'brand-logo-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False),flush=True)
    browser.close()
