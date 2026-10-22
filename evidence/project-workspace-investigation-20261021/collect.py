"""Read-only deployment snapshot; output only allowlisted config and aggregate data."""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
KEYS = [
    "research_plan_enabled", "research_delivery_read_enabled",
    "research_delivery_write_enabled", "project_export_enabled",
    "project_report_write_enabled", "project_report_pdf_enabled",
    "agent_analysis_write_enabled", "agent_download_write_enabled",
    "tool_gateway_read_enabled",
]


def run(args, input=None):
    result = subprocess.run(args, input=input, text=True, capture_output=True, check=True)
    return result.stdout


probe = '''
import os,json
from pathlib import Path
from cygnusx.core.config import get_settings
keys=KEYS
s=get_settings()
processes=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit(): continue
 try:
  cmd=(proc/'cmdline').read_bytes()
  if not any(x in cmd for x in [b'uvicorn',b'celery']): continue
  if b'python -' in cmd or b'keys=KEYS' in cmd: continue
  raw=(proc/'environ').read_bytes().split(b'\\0')
  env={}
  for pair in raw:
   key,sep,value=pair.partition(b'=')
   if sep and key.decode() in [k.upper() for k in keys]:
    env[key.decode()]=value.decode()
  processes.append({'pid':int(proc.name),'allowlisted_environment':env})
 except (PermissionError,FileNotFoundError): pass
print(json.dumps({'settings_in_fresh_container_process':{k:getattr(s,k) for k in keys},
 'allowlisted_container_environment':{k.upper():os.environ.get(k.upper(),'<unset>') for k in keys},
 'service_processes':processes,
 'database_host':getattr(s,'postgres_host',None),
 'database_name':getattr(s,'postgres_db',None)},ensure_ascii=False))
'''.replace("keys=KEYS", "keys=" + repr(KEYS), 1)
snapshot = {
    "collected_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
    "git_head": run(["git", "rev-parse", "HEAD"]).strip(),
    "scope": "Existing deployment read-only inspection; no feature enable, migration, job or login",
    "containers": {},
}
for name in ["cygnusx-web", "cygnusx-worker", "cygnusx-beat"]:
    inspected = json.loads(run(["docker", "inspect", name]))[0]
    snapshot["containers"][name] = {
        "running": inspected["State"]["Running"],
        "started_at": inspected["State"]["StartedAt"],
        "image_id": inspected["Image"],
        "compose_files": inspected["Config"]["Labels"].get("com.docker.compose.project.config_files"),
        "probe": json.loads(run(["docker", "exec", "-i", name, "python", "-"], probe)),
    }

gate_probe = '''
import json
from cygnusx.application.services.research_plan_service import require_plan_enabled
from cygnusx.application.services.research_provenance_service import require_research_read
from cygnusx.application.services.project_delivery_service import export_enabled
from cygnusx.application.services.agent_tool_gateway import WRITE_RUNTIME_ACCEPTED
out={'WRITE_RUNTIME_ACCEPTED':WRITE_RUNTIME_ACCEPTED,'checks':[]}
for fn in [require_plan_enabled,require_research_read,export_enabled]:
 try:
  fn();out['checks'].append({'name':fn.__name__,'allowed':True})
 except Exception as e:
  out['checks'].append({'name':fn.__name__,'allowed':False,'type':type(e).__name__,
   'message':str(e),'code':getattr(e,'code',None),'status_code':getattr(e,'status_code',None)})
print(json.dumps(out,ensure_ascii=False))
'''
snapshot["gate_reproduction_in_web_container"] = json.loads(
    run(["docker", "exec", "-i", "cygnusx-web", "python", "-"], gate_probe)
)

from dotenv import dotenv_values

values = dotenv_values(ROOT / ".env")
snapshot["root_dotenv_allowlisted_flags"] = {
    k.upper(): values.get(k.upper(), "<unset>") for k in KEYS
}

sql = """
BEGIN READ ONLY;
SELECT json_build_object('database',current_database(),'role',current_user,
 'alembic_revision',(SELECT version_num FROM alembic_version),
 'projects',(SELECT count(*) FROM projects),
 'research_plans',(SELECT count(*) FROM research_plans),
 'datasets',(SELECT count(*) FROM datasets),
 'dataset_analysis_links',(SELECT count(*) FROM dataset_analysis_links),
 'project_export_jobs',(SELECT count(*) FROM project_export_jobs),
 'project_report_jobs',(SELECT count(*) FROM project_report_jobs),
 'tasks',(SELECT count(*) FROM tasks),
 'reports',(SELECT count(*) FROM reports),
 'chat_sessions',(SELECT count(*) FROM chat_sessions),
 'project_bound_sessions',(SELECT count(*) FROM chat_sessions WHERE project_id IS NOT NULL),
 'project_members_table',to_regclass('public.project_members'));
COMMIT;
"""
snapshot["database_aggregate_read_only"] = json.loads(run([
    "docker", "exec", "-i", "cygnusx-db", "sh", "-c",
    'psql -X -qAt -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f -',
], sql))

import urllib.error
import urllib.request

snapshot["anonymous_http_probes"] = []
for suffix in ["research-plans", "research-delivery", "delivery-inventory"]:
    url = "http://127.0.0.1:8888/api/v1/projects/00000000-0000-0000-0000-000000000000/" + suffix
    try:
        response = urllib.request.urlopen(url, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    snapshot["anonymous_http_probes"].append({
        "endpoint_kind": suffix, "status": response.code,
        "body": response.read(2048).decode(),
    })
snapshot["limitations"] = [
    "Settings probe is a fresh process in each existing container, not direct inspection of the web process cache.",
    "Anonymous HTTP probes stop at 401 authentication; no authenticated browser or HTTP feature-gate assertion.",
    "Counts are a database-wide point-in-time snapshot, not identification of the screenshot user/project.",
    "No scientific execution, export generation, worker task delivery or production enablement was tested.",
]
paths = [
    "src/cygnusx/core/config.py", "src/cygnusx/api/v1/projects.py",
    "src/cygnusx/api/v1/research_plans.py", "src/cygnusx/api/v1/research_delivery.py",
    "src/cygnusx/application/services/project_service.py",
    "src/cygnusx/application/services/project_overview_service.py",
    "src/cygnusx/application/services/research_plan_service.py",
    "src/cygnusx/application/services/research_provenance_service.py",
    "src/cygnusx/application/services/project_delivery_service.py",
    "frontend/src/views/ProjectDetailView.vue",
    "frontend/src/components/ResearchPlanWorkbench.vue",
    "frontend/src/components/ResearchDeliveryChain.vue",
    "frontend/src/components/ProjectResearchDelivery.vue",
    "ARCHITECTURE_DESIGN/CygnusX_Research_Feature_Runtime_Acceptance.md",
]
snapshot["source_sha256"] = {
    p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths
}
(OUT / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"snapshot": str(OUT / "snapshot.json"),
                  "containers": list(snapshot["containers"]),
                  "database": snapshot["database_aggregate_read_only"]}, ensure_ascii=False))
