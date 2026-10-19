import concurrent.futures, datetime, json, os, pathlib, subprocess, sys, time
root=pathlib.Path('/home/zj/zj_code_libarary/OmicHub')
evidence=root/'evidence/iat-r3-final-20261019'
jobs=[
('backend-isolated',root,['.venv/bin/python','-m','pytest','tests/unit/test_deterministic_test_provider.py','tests/unit/test_download_s5b_consumption.py','tests/unit/test_agent_tools_phase2.py','tests/unit/test_dataset_gateway_phase3.py','tests/unit/test_dataset_import_handoff.py','tests/unit/test_research_treasure_phase1.py','tests/unit/test_treasure_native_access.py','-q','-m','not quarantine']),
('node-isolated',root/'pipelines/Treasure-Seeking_Mouse',['npm','test']),
('react-typecheck',root/'pipelines/Treasure-Seeking_Mouse',['npm','run','typecheck']),
('frontend-isolated',root/'frontend',['npm','test','--','src/components/research','src/utils/__tests__/researchAgentSse.test.ts']),
('frontend-build',root/'frontend',['npm','run','build']),
]
def run(job):
 name,cwd,command=job; start=time.monotonic()
 with (evidence/(name+'.log')).open('w') as f:
  result=subprocess.run(command,cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
 data={'name':name,'command':command,'cwd':str(cwd.relative_to(root)) or '.','exit_code':result.returncode,'duration_seconds':round(time.monotonic()-start,2),'log':name+'.log'}
 (evidence/(name+'.command.json')).write_text(json.dumps(data,indent=2)+'\n')
 print(json.dumps(data),flush=True)
 return data
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 results=list(pool.map(run,jobs))
(evidence/'commands.json').write_text(json.dumps(results,indent=2)+'\n')
sys.exit(int(any(x['exit_code'] for x in results)))
