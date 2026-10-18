"""Offline audit probes. No business DB, transport, downloads or execution."""
import ast
import json
import re
from pathlib import Path
from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.schemas.agent_tools import CAPABILITY_MODELS, capability_catalog
from cygnusx.application.services.agent_tool_gateway import WRITE_RUNTIME_ACCEPTED
from cygnusx.core.config import get_settings
root=Path.cwd()
results={}
p=root/'src/cygnusx/infrastructure/celery_app/tasks/download.py'
tree=ast.parse(p.read_text())
f=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_register_downloaded_files')
records=[n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='DataFile']
results['download_registration']={'constructor_fields':sorted(k.arg for n in records for k in n.keywords),'has_task_id_parameter':any(a.arg=='task_id' for a in f.args.kwonlyargs),'reconciler_requires_file_task_id':'FileRecordModel.task_id.in_' in (root/'src/cygnusx/application/services/dataset_import_service.py').read_text()}
assert not results['download_registration']['has_task_id_parameter']
assert 'task_id' not in results['download_registration']['constructor_fields']
assert results['download_registration']['reconciler_requires_file_task_id']
results['download_schema_methods']=DownloadRequest.model_json_schema()['properties']['download_method']['enum']
rust=(root/'pipelines/EBIDownload/crates/ebidownload-core/src/lib.rs').read_text()
methods=re.search(r'pub enum DownloadMethod \{([^}]+)\}',rust).group(1)
results['ebidownload_core_methods']=[v.strip() for v in methods.split(',') if v.strip()]
polar=Path('/home/zj/zj_code_libarary/EBIDownload/crates/polariseq-core/src/lib.rs').read_text()
results['polariseq_sibling_methods']=[v.strip() for v in re.search(r'pub enum DownloadMethod \{([^}]+)\}',polar).group(1).split(',') if v.strip()]
results['cloud_uri_validation']={}
for uri in ['oss://127.0.0.1/x','oss://[::1]/x','oss://example.com/x','oss://bucket/x']:
 try:
  DownloadRequest(source='cloud_storage',cloud_provider='aliyun',object_uri=uri)
  results['cloud_uri_validation'][uri]='ACCEPTED_SCHEMA_ONLY'
 except ValueError:
  results['cloud_uri_validation'][uri]='REJECTED_SCHEMA_ONLY'
results['catalog_all']=list(CAPABILITY_MODELS)
results['catalog_default']=[c.capability_id for c in capability_catalog()]
results['write_runtime_accepted']=WRITE_RUNTIME_ACCEPTED
s=get_settings()
results['local_flags']={k:getattr(s,k,None) for k in ['treasure_native_ui_enabled','tool_gateway_read_enabled','dataset_discovery_readonly','dataset_import_write','analysis_submit_from_dataset','counts_deg_flow_enabled','research_delivery_read_enabled','research_delivery_write_enabled','research_plan_enabled','agent_download_write_enabled','agent_analysis_write_enabled','legacy_pipeline_tools']}

report_tree=ast.parse((root/'src/cygnusx/application/services/report_service.py').read_text())
method=next(n for n in ast.walk(report_tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='build_delivery_package')
assignment=next(n for n in ast.walk(method) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reports' for t in n.targets))
source={'id':'audit-evidence-report','report_kind':'reproducibility'}
roles=eval(compile(ast.Expression(assignment.value),'<audited role expression>','eval'),{'__builtins__':{}},{'source':source,'evidence':source})
results['evidence_entry_report_roles']=[{'assigned_role':role,'actual_kind':report['report_kind'],'same_source_object':report is source} for role,report in roles]

print(json.dumps(results,indent=2))
