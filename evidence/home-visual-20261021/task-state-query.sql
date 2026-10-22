BEGIN READ ONLY;
SELECT json_build_object('running',count(*),'seed_demo_running',count(*) FILTER (WHERE idempotency_key LIKE 'seed-demo-%' AND parameters->>'seed'='demo-v1'),'empty_workdir',count(*) FILTER (WHERE work_dir=''),'unfinished',count(*) FILTER (WHERE finished_at IS NULL)) FROM tasks WHERE status='running';
SELECT id,name,status,created_at AT TIME ZONE 'Asia/Shanghai' AS created_at_shanghai,idempotency_key,parameters,work_dir FROM tasks WHERE status='running' ORDER BY created_at DESC LIMIT 5;
COMMIT;
