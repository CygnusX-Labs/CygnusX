import sys,json
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,'/acceptance')
from runtime import configure
configure()
import httpx
c=json.loads(Path('/tmp/research-private.json').read_text());h={'Authorization':'Bearer '+c['owner']};client=httpx.Client(base_url='http://api:8000/api/v1')
base=f"/projects/{c['project']}/research-plans/{c['plan_v2']}"
old=client.get(base,headers=h).json();draft=old['draft'];draft['research_question']+='；浏览器重验代理修正'
r=client.post(base+'/versions',headers=h,json={'request_key':str(uuid4()),'expected_digest':old['digest'],'draft':draft})
Path('/tmp/research-evidence/browser-new-version.json').write_text(json.dumps({'status':r.status_code,'body':r.json()},ensure_ascii=False,indent=2))
r.raise_for_status();c['previous_browser_plan']=c['plan_v2'];c['plan_v2']=r.json()['plan_id'];c['digest_v2']=r.json()['digest'];Path('/tmp/research-private.json').write_text(json.dumps(c));print('revision',r.status_code,r.json()['version'])
