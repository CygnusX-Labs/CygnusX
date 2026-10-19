import asyncio, json, pathlib
from playwright.async_api import async_playwright
out=pathlib.Path('/home/zj/zj_code_libarary/OmicHub/evidence/iat-r3-final-20261019')
async def main():
 result={'scope':'Chromium launch preflight only; not business E2E','status':'BLOCKED','screenshots':[],'har':None}
 try:
  async with async_playwright() as p:
   browser=await p.chromium.launch(executable_path='/home/zj/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
   await browser.close()
   result['status']='LAUNCH_ONLY_PASS'
 except Exception as e:
  result['error']=str(e)
 (out/'chromium-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
 return int(result['status']=='BLOCKED')
raise SystemExit(asyncio.run(main()))
