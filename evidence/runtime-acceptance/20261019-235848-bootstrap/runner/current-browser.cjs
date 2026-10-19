const {chromium}=require('playwright');
const fs=require('fs');
const ctx=JSON.parse(fs.readFileSync(0,'utf8'));
const OUT='/tmp/browser-evidence';fs.mkdirSync(OUT,{recursive:true});
let page, browser;
const rows=[], consoleLog=[], network=[], responses=[];
const rec=(step,ok,detail={})=>{rows.push({step,ok,...detail});fs.writeFileSync(OUT+'/results.json',JSON.stringify(rows,null,2));};
(async()=>{
 browser=await chromium.launch({headless:true,chromiumSandbox:true});
 rec('sandboxed_chromium',true,{version:browser.version()});
 const context=await browser.newContext({viewport:{width:1920,height:1080}});
 page=await context.newPage();
 page.on('console',m=>consoleLog.push({type:m.type(),text:m.text()}));
 page.on('pageerror',e=>consoleLog.push({type:'pageerror',text:e.message}));
 await page.goto('http://frontend:8080/login',{waitUntil:'networkidle'});
 await page.fill('input[placeholder="请输入用户名"]','accept_owner_d48ea1');
 await page.fill('input[placeholder="请输入密码"]',ctx.owner_password);
 await page.getByRole('button',{name:/登\s*录/}).first().click();
 await page.waitForURL(u=>!u.pathname.includes('/login'));
 rec('real_ui_login',true);
 const storage=await context.storageState();fs.writeFileSync('/tmp/browser-private-state.json',JSON.stringify(storage),{mode:0o600});
 await context.tracing.start({screenshots:true,snapshots:true,sources:true});
 page.on('response',async r=>{
  if(!r.url().includes('/api/'))return;
  network.push({method:r.request().method(),url:r.url(),status:r.status()});
  if(r.url().includes('research-plans')||r.url().includes('research-delivery')||r.url().includes('delivery-inventory')||r.url().includes('exports/prepare')){
   try{responses.push({url:r.url(),status:r.status(),body:await r.json()});}catch{}
  }
 });
 const url=`http://frontend:8080/projects/${ctx.project}?planId=${ctx.plan_v2}`;
 await page.goto(url,{waitUntil:'networkidle'});
 await page.getByText('科研计划与审阅',{exact:true}).waitFor();
 await page.getByRole('button',{name:'确认已审阅计划（不批准执行）',exact:true}).click();
 await page.getByRole('button',{name:'暂停后续调度',exact:true}).waitFor();
 rec('plan_review_ui',true);
 await page.screenshot({path:OUT+'/1920-plan-reviewed.png',fullPage:true});
 await page.getByRole('button',{name:'暂停后续调度',exact:true}).click();
 await page.getByRole('button',{name:'恢复计划',exact:true}).waitFor();rec('plan_pause_ui',true);
 await page.reload({waitUntil:'networkidle'});
 await page.getByRole('button',{name:'恢复计划',exact:true}).waitFor();rec('plan_refresh_persisted',true);
 await page.getByRole('button',{name:'恢复计划',exact:true}).click();
 await page.getByRole('button',{name:'暂停后续调度',exact:true}).waitFor();rec('plan_resume_ui',true);
 await page.getByRole('button',{name:'刷新交付记录',exact:true}).click();
 await page.getByText('项目科研成果与可追溯导出',{exact:true}).waitFor();
 await page.getByRole('button',{name:'刷新科研成果',exact:true}).click();
 await page.getByRole('button',{name:'导出科研成果：预览范围',exact:true}).click();
 const create=page.getByRole('button',{name:'确认范围并后台生成',exact:true});
 await create.waitFor();rec('export_preview_with_write_gate_closed',await create.isDisabled());
 rec('empty_delivery_api',responses.some(r=>r.url.endsWith('/research-delivery')&&r.status===200&&r.body.datasets.length===0));
 for(const width of [1920,768,390]){
  await page.setViewportSize({width,height:1080});await page.screenshot({path:OUT+`/${width}-plan-delivery-preview.png`,fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  rec(`width_${width}_overflow`,overflow<=2,{overflow});
 }
 await page.getByRole('button',{name:'查看审阅与工具轨迹',exact:true}).click();
 rec('audit_trace_ui',true);await page.screenshot({path:OUT+'/audit-events.png',fullPage:true});
 await context.tracing.stop({path:OUT+'/trace-private.zip'});
 fs.writeFileSync(OUT+'/console.json',JSON.stringify(consoleLog,null,2));
 fs.writeFileSync(OUT+'/network.json',JSON.stringify(network,null,2));
 fs.writeFileSync(OUT+'/api-responses.json',JSON.stringify(responses,null,2));
 rec('no_pageerror',!consoleLog.some(x=>x.type==='pageerror'));
 await browser.close();
 console.log(JSON.stringify({checks:rows.length,failed:rows.filter(x=>!x.ok).map(x=>x.step)}));
})().catch(async e=>{rec('browser_error',false,{error:e.message});if(page){await page.screenshot({path:OUT+'/failure.png',fullPage:true});fs.writeFileSync(OUT+'/failure-body.txt',await page.locator('body').innerText());}console.error(e.message);if(browser)await browser.close();process.exitCode=1;});
