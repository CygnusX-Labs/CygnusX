"""Smoke-test real container settings and SDK with host-ledger acknowledgement per HTTP attempt."""
import json
import subprocess
import budget

CODE=r'''
import asyncio,json,sys,time,logging
from loguru import logger
logger.remove();logging.disable(logging.CRITICAL)
import httpx
original=httpx.AsyncClient.send
async def send(self,request,*args,**kwargs):
 if not request.url.path.rstrip('/').endswith('/embeddings'):return await original(self,request,*args,**kwargs)
 print('AUDIT:'+json.dumps({'event':'reserve'}),flush=True)
 identity=int(sys.stdin.readline().strip())
 start=time.perf_counter()
 try:
  response=await original(self,request,*args,**kwargs)
  print('AUDIT:'+json.dumps({'event':'finish','id':identity,'status':'received','http_status':response.status_code,'duration_ms':round((time.perf_counter()-start)*1000,2)}),flush=True)
  return response
 except Exception as e:
  print('AUDIT:'+json.dumps({'event':'finish','id':identity,'status':'error','error_type':type(e).__name__}),flush=True)
  raise
httpx.AsyncClient.send=send
from cygnusx.core.config import get_settings
from cygnusx.infrastructure.ai_provider.litellm_provider import LiteLLMProvider
async def main():
 try:
  settings=get_settings()
  values=await LiteLLMProvider().embeddings('合成运行时 embedding 验收探针',model=settings.agent_memory_embedding_model)
  r={'status':'passed' if len(values)==1024 else 'failed','dimensions':len(values),'model':settings.agent_memory_embedding_model}
 except Exception as e:r={'status':'failed','error_type':type(e).__name__}
 print('AUDIT:'+json.dumps({'event':'result',**r}),flush=True)
asyncio.run(main())
'''
p=subprocess.Popen(['docker','exec','-i','cygnusx-web','python','-c',CODE],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
result=None
for line in p.stdout:
    if not line.startswith('AUDIT:'):continue
    event=json.loads(line.split(':',1)[1])
    if event['event']=='reserve':
        identity=budget.reserve('embedding','live_web_container_smoke')
        p.stdin.write(str(identity)+'\n');p.stdin.flush()
    elif event['event']=='finish':
        identity=event.pop('id');event.pop('event');budget.finish(identity,**event)
    elif event['event']=='result':result=event
code=p.wait(timeout=30)
assert code==0 and result and result['status']=='passed'
result.pop('event');(budget.OUT/'runtime-embedding-smoke.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
