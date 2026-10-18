import hashlib,json,re,subprocess
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone
from cygnusx.application.schemas.execution_definition import ExecutionDefinition
from cygnusx.application.schemas.execution_evidence import ExecutionDefinitionV2,ExecutionEvidence
from cygnusx.application.services import agent_tool_gateway
from cygnusx.infrastructure.download.policy import DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED
from cygnusx.core.config import get_settings
p=Path('evidence/lifecycle-stabilization-ri13')

def errors(name):
 return Counter(re.sub(r':\d+: error:', ': error:',line) for line in (p/name).read_text().splitlines() if ': error:' in line)
base,now=errors('mypy-baseline.log'),errors('mypy-current.log')
new=now-base
assert not new,new
assert 'All checks passed!' in (p/'ruff.log').read_text()
assert 'Success:' in (p/'mypy-new.log').read_text()
assert '151 passed' in (p/'targeted-tests.log').read_text()
assert '341 passed' in (p/'regression-tests.log').read_text()
for name,model in [('cygnusx-execution-definition-v1',ExecutionDefinition),('cygnusx-execution-definition-v2',ExecutionDefinitionV2),('cygnusx-execution-evidence-v1',ExecutionEvidence)]:
 assert json.loads(Path('docs/contracts/'+name+'.schema.json').read_text())==model.model_json_schema(),name
baseline=json.loads((p/'baseline.json').read_text())
v1='src/cygnusx/application/schemas/execution_definition.py'
assert hashlib.sha256(Path(v1).read_bytes()).hexdigest()==baseline['files'][v1]
assert agent_tool_gateway.WRITE_RUNTIME_ACCEPTED is False
assert DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED is False
settings=get_settings()
flag_names=['tool_gateway_read_enabled','dataset_import_write','analysis_submit_from_dataset','counts_deg_flow_enabled','research_delivery_write_enabled','agent_download_write_enabled','agent_analysis_write_enabled']
flags={key:getattr(settings,key) for key in flag_names}
(p/'flags.json').write_text(json.dumps({'observed_flags':flags,'WRITE_RUNTIME_ACCEPTED':False,'DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED':False},indent=2)+'\n')
quality={'mypy_baseline_errors':sum(base.values()),'mypy_current_errors':sum(now.values()),'new_diagnostics':list(new.elements()),'incremental_status':'PASS_NO_NEW_DIAGNOSTICS','raw_current_mypy':'FAIL_INHERITED_ERRORS','ruff_selected':'PASS','new_evidence_boundary_mypy':'PASS_3_SOURCE_FILES','full_repository':'NOT_CLAIMED'}
(p/'quality-baseline.json').write_text(json.dumps(quality,indent=2)+'\n')
deliverables=[('download admission','docs/implementation/cygnusx-download-runtime-admission.md'),('incremental quality baseline',str(p/'quality-baseline.json')),('RI12 contract and code','docs/contracts/cygnusx-execution-evidence-v1.md'),('RI13 minimum wiring and tests','src/cygnusx/application/services/execution_evidence_service.py'),('RI05 isolated environment plan','docs/implementation/cygnusx-ri05-isolated-runtime-acceptance-plan.md'),('RI06-RI09 proposed interfaces','docs/implementation/cygnusx-ri06-ri09-project-export-interface-proposal.md'),('test and gate matrix',str(p/'checks.json')),('limitations and rollback','docs/implementation/cygnusx-lifecycle-stabilization-ri13-implementation.md')]
checks={'generated_at':datetime.now(timezone.utc).isoformat(),'scope':'stabilization + RI12 revision + RI13 minimum code wiring + RI05 preparation + RI06-RI09 design','deliverables':[{'item':i+1,'name':name,'path':file,'status':'DELIVERED_CODE_ISOLATION_OR_PLAN'} for i,(name,file) in enumerate(deliverables)],'quality':quality,'tests':{'targeted':{'passed':151,'files':10,'junit':'targeted.xml'},'related_regression':{'passed':341,'files':22,'junit':'regression.xml'},'warning_notes':['existing Pydantic deprecation','existing asyncio marker','OTel background export may encounter closed test capture stream after exit']},'gates':{'dirty_baseline':'CAPTURED_AND_PRESERVED','v1_protocol_unchanged':'PASS_SOURCE_HASH_AND_SCHEMA','v2_and_evidence_schema_parity':'PASS','manual_agent_worker_download':'FAIL_CLOSED_SOURCE_UNCHANGED','server_capability_shared':'PASS_REAL_REST_AND_GATEWAY_OFFLINE','manifest_v1_v1_1':'PASS_CONTRACT_AND_SERVICE_TESTS','submission_task_persistence':'PASS_REAL_SQLITE_AND_BUILDER_QUEUE_FAKE','worker_input_checks':'PASS_ORIGINAL_WORKER_FUNCTION_AND_REAL_FILES_EXECUTOR_FAKE','worker_redelivery':'PASS_ISOLATED_TERMINAL_AND_RUNNING_REFUSAL','provenance_snapshot_projection':'PASS_ISOLATED','postgres_lock_recovery':'RUNTIME_BLOCKED','redis_cas':'RUNTIME_BLOCKED','workflow_release_attestation':'NOT_OBSERVED','worker_image_tool_reference_attestation':'NOT_OBSERVED','real_download_analysis_bioreport':'NOT_RUN_NO_AUTHORIZED_TEST_ENV','pasilla_case':'SELECTED_LICENSE_SOURCE_REFERENCED_ACTUAL_SIZE_SHA_NOT_YET_ACQUIRED','full_project_export_reproduction':'NOT_IMPLEMENTED_PER_SCOPE'},'rollback':'baseline hunk rollback only; retain all persisted task/evidence/snapshots/files; no runtime gates enabled'}
(p/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
for _,file in deliverables:assert Path(file).is_file(),file
files=list(baseline['files'])+['src/cygnusx/application/schemas/execution_evidence.py','src/cygnusx/application/services/execution_evidence_service.py','tests/unit/test_execution_evidence_ri13.py','tests/unit/test_execution_evidence_projection.py','tests/unit/test_lifecycle_stabilization.py']
final={'status':'MINIMUM_CODE_AND_PLANS_DELIVERED_RUNTIME_NOT_ACCEPTED','source_sha256':{f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in files},'no_production_actions':['commit','push','deploy','migration','download','analysis','gate_enable'],'quality':quality,'runtime':'BLOCKED','implementation_report':'docs/implementation/cygnusx-lifecycle-stabilization-ri13-implementation.md'}
(p/'final-verification.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(quality,ensure_ascii=False))
print('Schema parity, old v1 unchanged, selected tests, closed source gates and 8 deliverables: verified')
