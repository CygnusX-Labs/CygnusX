"""Persistently account for real HTTP attempts; never store prompts, keys or vectors."""
import fcntl
import json
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
LEDGER = OUT / 'call-ledger.json'
STEP = 'unspecified'


def change(callback):
    with (OUT/'call-ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data=json.loads(LEDGER.read_text())
        result=callback(data)
        data['captured_at_utc']=datetime.now(timezone.utc).isoformat()
        data['status']='real_acceptance_in_progress'
        data['reason']='Real HTTP attempts are counted before sending, including retries and controlled-failure calls; no prompts, secrets or vectors retained'
        data['cost_this_run']=None
        data['cost_status']='Billing amount not queried; token usage retained when returned by the provider'
        data['remaining']={k:data['limits'][k]-data['total'][k] for k in data['limits']}
        tmp=LEDGER.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
        tmp.replace(LEDGER)
        return result


def reserve(kind, step=None):
    def apply(data):
        if data['total'][kind] >= data['limits'][kind]:
            raise RuntimeError('Real model call budget exhausted')
        data['total'][kind]+=1
        identity=len(data['calls'])+1
        data['calls'].append({'id':identity,'kind':kind,'step':step or STEP,
            'started_at_utc':datetime.now(timezone.utc).isoformat(),'status':'in_flight_counted'})
        return identity
    return change(apply)


def finish(identity, **fields):
    def apply(data):
        row=next(x for x in data['calls'] if x['id']==identity)
        row.update(fields)
    change(apply)


def install_http_accounting():
    import httpx
    original=httpx.AsyncClient.send
    async def send(self, request, *args, **kwargs):
        path=request.url.path.rstrip('/')
        kind='embedding' if path.endswith('/embeddings') else ('extraction' if path.endswith('/chat/completions') else None)
        if kind is None:
            return await original(self,request,*args,**kwargs)
        identity=reserve(kind)
        try:
            request_model=json.loads(request.content).get('model')
            if isinstance(request_model,str): finish(identity,request_model=request_model)
        except (ValueError,TypeError,AttributeError): pass
        start=time.perf_counter()
        try:
            response=await original(self,request,*args,**kwargs)
            fields={'http_status':response.status_code,'duration_ms':round((time.perf_counter()-start)*1000,2),'status':'received'}
            if 'application/json' in response.headers.get('content-type',''):
                try:
                    await response.aread()
                    data=response.json()
                    usage=data.get('usage') or {}
                    fields['usage']={k:v for k,v in usage.items() if isinstance(v,(int,float))}
                except (ValueError,TypeError): pass
            finish(identity,**fields)
            return response
        except Exception as exc:
            finish(identity,status='error',error_type=type(exc).__name__,duration_ms=round((time.perf_counter()-start)*1000,2))
            raise
    httpx.AsyncClient.send=send
