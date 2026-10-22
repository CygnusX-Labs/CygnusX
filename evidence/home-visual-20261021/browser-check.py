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
    page.add_init_script("localStorage.setItem('access_token','visual-test-token');localStorage.setItem('cygnusx-theme','dark');")
    page.route('**/api/v1/**',api)
    errors=[]
    page.on('pageerror',lambda e:(errors.append(str(e)),print('PAGE ERROR',str(e),flush=True)))
    page.goto('http://127.0.0.1:5179/',wait_until='domcontentloaded');print('LOADED',requests,flush=True)
    page.locator('.workbench-item').first.wait_for(timeout=60000)
    page.locator('.n-notification__close').first.click() if page.locator('.n-notification__close').count() else None
    page.screenshot(path=str(OUT/'initial.png'),full_page=True)
    print(json.dumps({'title':page.title(),'url':page.url,'errors':errors,'requests':requests,'body':page.locator('body').inner_text()[:1800]},ensure_ascii=False),flush=True)
    results=[]
    for width in [1280,1440,2560,1279,1024,390]:
        page.set_viewport_size({'width':width,'height':1440})
        page.wait_for_timeout(250)
        layout=page.evaluate('''() => {
          const rect=s=>document.querySelector(s).getBoundingClientRect();
          return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,homeScrollWidth:document.querySelector('.home-page').scrollWidth,homeWidth:rect('.home-page').width,heroHeight:rect('.hero').height,workbenchTop:rect('#workbench-title').top,columns:getComputedStyle(document.querySelector('.workbench-grid')).gridTemplateColumns,titleLines:[...document.querySelectorAll('.hero-title__line')].map(x=>({text:x.textContent,height:x.getBoundingClientRect().height,lineHeight:parseFloat(getComputedStyle(x).lineHeight),width:x.getBoundingClientRect().width})),badgeColors:[...document.querySelectorAll('.status-badge')].map(x=>({text:x.textContent.trim(),color:getComputedStyle(x).color,bg:getComputedStyle(x).backgroundColor})),capsule:{text:document.querySelector('.cookie-badge').textContent.trim(),width:rect('.cookie-badge').width},reportEllipsis:[...document.querySelectorAll('[aria-labelledby="recent-reports-title"] strong')].map(x=>({client:x.clientWidth,scroll:x.scrollWidth,overflow:getComputedStyle(x).textOverflow}))};
        }''')
        page.screenshot(path=str(OUT/f'home-{width}.png'),full_page=True)
        results.append(layout)
    (OUT/'browser-initial.json').write_text(json.dumps({'layouts':results,'errors':errors},ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False),flush=True)
    for layout in results:
        assert layout['scrollWidth'] <= layout['width'],layout
        assert layout['homeScrollWidth'] <= layout['homeWidth'] + 1,layout
        assert all(abs(x['height']-x['lineHeight'])<1 for x in layout['titleLines']),layout
        cols=[float(x.removesuffix('px')) for x in layout['columns'].split()]
        assert len(cols)==(3 if layout['width']>=1280 else 1),layout
        assert max(cols)-min(cols)<1,layout
        if layout['width'] in [1280,1440,2560]: assert layout['workbenchTop']<1440,layout
    page.set_viewport_size({'width':1440,'height':1440})
    page.get_by_role('button',name='关闭',exact=True).click()
    page.wait_for_timeout(350)
    page.reload(wait_until='domcontentloaded')
    page.locator('.workbench-item').first.wait_for()
    assert page.locator('.announcement-banner').count()==0
    announcement['description']='内容已更新，公告应重新出现'
    page.reload(wait_until='domcontentloaded')
    page.locator('.announcement-banner').wait_for()
    assert page.locator('.banner-desc').inner_text()==announcement['description']
    before=requests.count('/tasks')
    page.get_by_role('button',name='刷新',exact=True).click()
    page.wait_for_timeout(250)
    assert requests.count('/tasks')==before+2
    page.evaluate("""async () => {
        const {default: router}=await import('/src/router/index.ts');
        window.homeDestinations=[];
        router.beforeEach(to=>{window.homeDestinations.push(to.fullPath);return false});
    }""")
    destinations=[]
    for selector in ['.hero-btn-primary','.hero-btn-secondary']+['.entry-card >> nth='+str(i) for i in range(6)]+['.admin-cta']:
        page.locator(selector).click()
        page.wait_for_timeout(100)
        destinations.append(page.evaluate('window.homeDestinations.at(-1)'))
    assert destinations==['/flows','/ai','/treasure-mouse','/files','/flows','/ai','/tasks','/reports','/admin/users'],destinations
    more=page.locator('.workbench-card__more').evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))')
    assert more==['/projects','/tasks','/reports'],more
    # Hover movement, static showcase, and reduced motion.
    motions=[]
    for mode in ['no-preference','reduce']:
        page.emulate_media(reduced_motion=mode)
        for selector in ['.entry-card','.workbench-card','.pillar-card','.ecosystem-card']:
            page.locator(selector).first.hover()
            page.wait_for_timeout(230)
            transform=page.locator(selector).first.evaluate('(x)=>getComputedStyle(x).transform')
            motions.append({'mode':mode,'selector':selector,'transform':transform})
            assert transform==('matrix(1, 0, 0, 1, 0, -2)' if mode=='no-preference' and selector in ['.entry-card','.workbench-card'] else 'none'),motions[-1]
    page.emulate_media(reduced_motion='reduce')
    # Measure contrast against rendered backgrounds with text temporarily hidden.
    page.locator('.hero-lifecycle').scroll_into_view_if_needed()
    rect=page.locator('.hero-lifecycle__note--desktop').bounding_box()
    style=page.add_style_tag(content='.hero-lifecycle__note--desktop { color: transparent !important; }')
    page.screenshot(path=str(OUT/'lifecycle-background.png'),clip=rect)
    style.evaluate('(x)=>x.remove()')
    import base64
    def png_contrast(data):
        png=base64.b64encode(data).decode()
        return page.evaluate("""async png=>{
        const img=new Image();img.src='data:image/png;base64,'+png;await img.decode();
        const canvas=document.createElement('canvas');canvas.width=img.width;canvas.height=img.height;
        const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
        const data=ctx.getImageData(0,0,img.width,img.height).data;
        const lum=rgb=>rgb.map(x=>x/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
        let min=Infinity;
        for(let i=0;i<data.length;i+=4){const bg=[data[i],data[i+1],data[i+2]], fg=bg.map(x=>.85*255+.15*x);min=Math.min(min,(lum(fg)+.05)/(lum(bg)+.05));}
        return min;
    }""",png)
    contrast=png_contrast((OUT/'lifecycle-background.png').read_bytes())
    lifecycle_checks=[]
    for width in [1280,1440,2560]:
        page.set_viewport_size({'width':width,'height':1440})
        page.locator('.hero-lifecycle').scroll_into_view_if_needed()
        hidden=page.add_style_tag(content='.hero-lifecycle p,.hero-lifecycle h2,.lifecycle-step__label {color:transparent !important;}')
        values=[]
        for item in page.locator('.hero-lifecycle__eyebrow,.hero-lifecycle h2,.lifecycle-step__label,.hero-lifecycle__note--desktop').all():
            values.append(png_contrast(page.screenshot(clip=item.bounding_box())))
        hidden.evaluate('(x)=>x.remove()')
        lifecycle_checks.append({'width':width,'minContrast':min(values)})
        assert min(values)>=4.5,lifecycle_checks[-1]
    page.set_viewport_size({'width':1440,'height':1440})
    assert contrast>=4.5,contrast
    capsule=page.locator('.cookie-badge').evaluate("""x=>{const t=x.querySelector('.n-tag'), b=x.getBoundingClientRect(), r=x.nextElementSibling.getBoundingClientRect();return {padding:getComputedStyle(t).padding,gap:r.left-b.right,text:x.textContent.trim(),width:t.clientWidth,scroll:t.scrollWidth}}""")
    assert capsule['gap']>=12 and capsule['scroll']<=capsule['width'],capsule
    assert capsule['padding']=='4px 12px',capsule
    assert not errors,errors
    result={'layouts':results,'dismissRefresh':True,'contentUpdate':True,'refreshRequests':True,'destinations':destinations,'moreLinks':more,'hover':motions,'lifecycleContrastMin':contrast,'lifecycleAllTextChecks':lifecycle_checks,'capsule':capsule,'errors':errors}
    (OUT/'browser-verified.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('VERIFIED',json.dumps(result,ensure_ascii=False),flush=True)
    browser.close()
