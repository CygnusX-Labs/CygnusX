from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json
OUT=Path('/home/zj/zj_code_libarary/OmicHub/evidence/home-visual-20261021')
announcement={'id':'rna-atac-ready','title':'RNA-seq / ATAC-seq 分析已就绪','description':'标准分析流程已就绪，选择流程开始研究。','type':'feature','button_text':'开始分析','link':'/flows','dismiss_behavior':'daily','priority':1,'is_enabled':True,'start_time':'2026-10-01T00:00:00Z','created_at':'2026-10-01T00:00:00Z','updated_at':'2026-10-01T00:00:00Z'}
project={'id':'project-1','name':'番茄耐盐转录组科研项目','description':'盐胁迫响应分析','slug':'tomato','created_at':'2026-10-20T00:00:00Z'}
report=lambda status: {'id':'report-'+status,'title':'GO/KEGG 富集分析分析报告 2026-10-02 #031 '+status,'flow_name':'RNA-seq','status':status,'created_at':'2026-10-20T00:00:00Z'}
requests=[]
def api(route):
    path=urlparse(route.request.url).path.removeprefix('/api/v1')
    requests.append(path)
    data={}
    if path=='/auth/setup-required': data={'setup_required':False}
    elif path=='/auth/me': data={'id':'user-1','username':'root','nickname':'JIAN','role':'admin','disabled_modules':[],'preferences':{}}
    elif path=='/modules/registry': data={'modules':[]}
    elif path=='/announcements/active': data=[announcement]
    elif path=='/cookies/account': data={'balance':'26732.3','available_balance':'26732.3','frozen_balance':'0','total_earned':'30000','total_spent':'3267.7','total_adjusted':'0'}
    elif path=='/festival/today': data={'hasFestival':False}
    elif path=='/projects': data=[project]
    elif path=='/tasks':
        status=parse_qs(urlparse(route.request.url).query).get('status',['running'])[0]
        data={'items':[{'id':'task-'+status,'name':'RNA-seq 差异表达分析 - 长任务名称不应撑开网格','flow_id':'rna_seq','status':status,'created_at':'2026-10-03T00:00:00Z'}],'total':1}
    elif path=='/reports': data={'items':[report('completed'),report('expired'),report('generating')],'total':3}
    elif 'notifications' in path: data=[]
    elif path=='/flows': data=[]
    route.fulfill(json=data)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/home/zj/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1440},reduced_motion='reduce')
    page.add_init_script("localStorage.setItem('access_token','visual-test-token')")
    page.route('**/api/v1/**',api)
    page.goto('http://127.0.0.1:5179/',wait_until='domcontentloaded')
    page.locator('.status-badge').first.wait_for()
    results=[]
    for theme in ['dark','light']:
        page.evaluate("""async theme=>{const {useThemeStore}=await import('/src/stores/theme.ts');useThemeStore().setTheme(theme)}""",theme)
        page.wait_for_timeout(350)
        rows=page.locator('.status-badge').evaluate_all("""xs=>{
          const rgba=s=>s.match(/[\d.]+/g).map(Number);
          const lum=rgb=>rgb.slice(0,3).map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);
          return xs.map(x=>{
            const c=getComputedStyle(x),fg=rgba(c.color),bg=rgba(c.backgroundColor),parent=rgba(getComputedStyle(x.closest('.workbench-card')).backgroundColor);
            const blended=bg.slice(0,3).map((v,i)=>v*(bg[3]??1)+parent[i]*(1-(bg[3]??1)));
            const a=lum(fg),b=lum(blended);
            return {text:x.textContent.trim(),foreground:c.color,background:c.backgroundColor,parentBackground:parent,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
          });
        }""")
        print(theme,json.dumps(rows,ensure_ascii=False),flush=True)
        assert all(r['contrast']>=4.5 for r in rows),rows
        results.append({'theme':theme,'badges':rows})
    (OUT/'badge-contrast.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False))
    browser.close()
